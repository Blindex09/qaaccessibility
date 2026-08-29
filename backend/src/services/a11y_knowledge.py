"""Local accessibility knowledge base with hybrid retrieval (BM25 + embeddings).

Before this module the whole `resources/a11y_reference.md` file (~12.5 KB) was
concatenated into the chat system prompt on every single turn, whatever the user
asked. That burned context budget on sections that were almost never relevant and
gave no way to ground an answer on a specific passage.

Retrieval design (2026 mainstream pattern for a small local corpus):
  1. Chunk the markdown reference by heading, so each chunk is a self-contained
     topic ("Modal / Dialogo", "PDF/UA", "APCA"...).
  2. Keyword leg: SQLite FTS5, whose `bm25()` ranking function is the standard
     Okapi BM25. sqlite3 is stdlib, so this needs no dependency at all.
  3. Semantic leg: embeddings from the provider client the project already
     configures, stored next to the chunks, compared with plain cosine
     similarity (the corpus is a couple dozen chunks -- a vector database, or
     even numpy, would be pure overhead here).
  4. Fusion: Reciprocal Rank Fusion. RRF works on ranks, not scores, so the
     incompatible scales of BM25 and cosine never have to be normalised.
  5. Rerank: an LLM scores each fused candidate against the question and the
     top-K survivors become the prompt block.

The semantic leg is optional by design: with no API key, an offline machine, or a
provider without an embeddings endpoint, retrieval degrades to keyword-only
(logged, never silent) instead of failing the turn.
"""

import contextlib
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Reference corpus. Every markdown file listed here is chunked into the index.
_RESOURCES_DIR = os.path.join(os.path.dirname(__file__), "..", "resources")
_CORPUS_FILES = ("a11y_reference.md", "agent_knowledge.md")

# Embedding models per provider family. Both are the current small/cheap tier,
# which is the right pick for a corpus this size.
# `gemini-embedding-001` foi desligado e substituído por `gemini-embedding-2`
# (docs Gemini API, Embeddings/Deprecations). Os dois espaços vetoriais são
# incompatíveis entre si, então índices antigos precisam ser reconstruídos --
# ver `_EMBEDDING_SPACE_VERSION`.
_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
_GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"

# Identidade do espaço vetorial usado pelo índice. Entra no fingerprint do
# corpus para que trocar de modelo de embedding invalide o índice em disco:
# comparar vetores de modelos diferentes não gera erro, só resultados errados
# em silêncio.
_EMBEDDING_SPACE_VERSION = f"{_OPENAI_EMBEDDING_MODEL}|{_GEMINI_EMBEDDING_MODEL}"

# Retrieval budget. `_CANDIDATE_K` per leg -> fused -> reranked down to `_TOP_K`.
_CANDIDATE_K = 8
_TOP_K = 4
_RRF_K = 60

# Tokens shorter than this carry no signal for the keyword leg (de, do, a, o...).
_MIN_TOKEN_LEN = 3
_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÿ]+")


@dataclass(frozen=True)
class KnowledgeChunk:
    """One retrievable section of the reference corpus."""

    chunk_id: str
    source: str
    title: str
    text: str

    def as_context(self) -> str:
        return f"#### {self.title}\n{self.text}"


def chunk_markdown(content: str, source: str) -> list[KnowledgeChunk]:
    """Split a markdown document into one chunk per heading section.

    The heading path is kept in the title ("2. Padroes de Teclado > A. Modal"),
    so a chunk retrieved in isolation still says what it is about.
    """
    if not content.strip():
        return []

    chunks: list[KnowledgeChunk] = []
    parent_title = ""
    current_title = ""
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if not body or not current_title:
            return
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"{source}#{len(chunks)}",
                source=source,
                title=current_title,
                text=body,
            )
        )

    for line in content.splitlines():
        heading = re.match(r"^(#{2,3})\s+(.*)$", line)
        if heading is None:
            buffer.append(line)
            continue
        flush()
        buffer = []
        level, text = len(heading.group(1)), heading.group(2).strip()
        if level == 2:
            parent_title = text
            current_title = text
        else:
            current_title = f"{parent_title} > {text}" if parent_title else text
    flush()
    return chunks


def load_corpus() -> list[KnowledgeChunk]:
    """Read and chunk every reference document of the corpus."""
    chunks: list[KnowledgeChunk] = []
    for filename in _CORPUS_FILES:
        path = os.path.join(_RESOURCES_DIR, filename)
        try:
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
        except OSError as exc:
            logger.error("[a11y_knowledge] Falha ao ler o documento de referência %s: %s", filename, exc)
            continue
        chunks.extend(chunk_markdown(content, filename))
    return chunks


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #

# Providers testados ao vivo (2026-08-27, chaves reais) sem nenhum endpoint de
# embeddings funcional hoje:
# - "ollama"/"ollama-cloud": POST /v1/embeddings e /api/embeddings devolvem 404
#   ("path not found") em todos os modelos da conta; POST /api/embed (nativo)
#   devolve 401 mesmo para nomes de modelo de embedding reais que nem existem
#   no catalogo da conta -- nao e questao de modelo, a rota inteira recusa
#   essa chave. A doc oficial (docs.ollama.com/capabilities/embeddings) e uma
#   issue aberta (github.com/ollama/ollama/issues/14496, 2026-02-27) confirmam:
#   "/v1/embeddings ... (Coming soon)" -- ainda nao lancado pro Cloud.
# - "xai": nunca publicou endpoint de embeddings (nem /v1/embeddings nem
#   equivalente); documentado por integracoes terceiras (ex.: promptfoo).
# Tentar mesmo assim nao quebra nada (o try/except abaixo cobria isso), mas
# desperdicava uma chamada de rede fadada ao erro a cada turno de chat sempre
# que o provider configurado era um destes. Tratado como conhecido-nao-suportado
# ANTES de tentar, sem esperar a rede confirmar o oculo.
_EMBEDDINGS_UNSUPPORTED_PROVIDERS = frozenset({"xai", "ollama", "ollama-cloud"})


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed `texts` with the provider already configured for the chat.

    Returns None (and logs why) when embeddings are unavailable, so the caller
    can fall back to keyword-only retrieval instead of failing the turn.
    """
    if not texts:
        return []

    from backend.src.config.settings import get_settings

    cfg = get_settings().chat_model_config()
    provider = str(cfg.get("provider") or "").strip().lower()
    api_key = cfg.get("api_key")
    base_url = cfg.get("base_url") or None

    if not api_key:
        logger.info("[a11y_knowledge] Sem API key configurada; busca semântica desativada.")
        return None

    if provider in _EMBEDDINGS_UNSUPPORTED_PROVIDERS:
        logger.info(
            "[a11y_knowledge] Provider '%s' não oferece embeddings hoje (verificado ao vivo "
            "2026-08-27, sem endpoint funcional); busca semântica desativada.",
            provider,
        )
        return None

    try:
        if provider == "gemini":
            return _embed_gemini(texts, api_key)
        if provider in ("openai", ""):
            return _embed_openai_compatible(texts, api_key, base_url)
    except Exception as exc:
        logger.error("[a11y_knowledge] Provider '%s' falhou ao gerar embeddings: %s", provider, exc)
        return None

    logger.info(
        "[a11y_knowledge] Provider '%s' não expõe endpoint de embeddings; busca semântica desativada.",
        provider,
    )
    return None


def _embed_openai_compatible(texts: list[str], api_key: str, base_url: str | None) -> list[list[float]]:
    """So chamada para "openai"/"" (ver `_EMBEDDINGS_UNSUPPORTED_PROVIDERS` em
    `embed_texts` -- xai/ollama/ollama-cloud sao descartados antes de chegar
    aqui), entao `base_url` so precisa do override explicito ja resolvido pelo
    chamador, sem resolucao por-provider como o restante do projeto faz para chat."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.embeddings.create(model=_OPENAI_EMBEDDING_MODEL, input=texts)
    return [list(item.embedding) for item in response.data]


def _embed_gemini(texts: list[str], api_key: str) -> list[list[float]]:
    from google import genai

    client = genai.Client(api_key=api_key)
    # Uma chamada por texto, e isso é obrigatório no `gemini-embedding-2`: com
    # vários `contents` ele devolve UM único embedding agregado, não um por
    # texto (docs Gemini API, Embeddings). O custo fica só na construção do
    # índice (uma vez por versão do corpus, depois em disco); a consulta embute
    # um único texto de qualquer forma.
    vectors: list[list[float]] = []
    for text in texts:
        response = client.models.embed_content(model=_GEMINI_EMBEDDING_MODEL, contents=text)
        vectors.extend(list(item.values or []) for item in (response.embeddings or []))
    return vectors


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity between two dense vectors (0.0 when either is null)."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


# --------------------------------------------------------------------------- #
# Index
# --------------------------------------------------------------------------- #


def _corpus_fingerprint(chunks: list[KnowledgeChunk]) -> str:
    digest = hashlib.sha256()
    # O espaço vetorial faz parte da identidade do índice: trocar o modelo de
    # embedding torna os vetores gravados incomparáveis com os novos.
    digest.update(_EMBEDDING_SPACE_VERSION.encode("utf-8"))
    for chunk in chunks:
        digest.update(chunk.chunk_id.encode("utf-8"))
        digest.update(chunk.text.encode("utf-8"))
    return digest.hexdigest()[:16]


def index_path(fingerprint: str) -> str:
    """Path of the on-disk index for a given corpus fingerprint.

    The fingerprint is part of the filename, so editing the reference markdown
    naturally produces a new index instead of serving stale chunks.
    """
    return os.path.join(tempfile.gettempdir(), f"qa_accessibility_a11y_kb_{fingerprint}.sqlite3")


def build_index(chunks: list[KnowledgeChunk] | None = None) -> sqlite3.Connection:
    """Build (or reopen) the SQLite index holding the chunks, FTS5 and embeddings."""
    corpus = load_corpus() if chunks is None else chunks
    fingerprint = _corpus_fingerprint(corpus)
    path = index_path(fingerprint)
    already_built = os.path.exists(path)

    connection = sqlite3.connect(path)
    if already_built:
        return connection

    connection.executescript(
        """
        CREATE TABLE chunks (
            chunk_id  TEXT PRIMARY KEY,
            source    TEXT NOT NULL,
            title     TEXT NOT NULL,
            text      TEXT NOT NULL,
            embedding TEXT
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id UNINDEXED, title, text);
        """
    )

    embeddings = embed_texts([f"{chunk.title}\n{chunk.text}" for chunk in corpus])
    if embeddings is not None and len(embeddings) != len(corpus):
        logger.error(
            "[a11y_knowledge] Provider devolveu %d embeddings para %d chunks; busca semântica desativada.",
            len(embeddings),
            len(corpus),
        )
        embeddings = None

    for position, chunk in enumerate(corpus):
        vector = json.dumps(embeddings[position]) if embeddings is not None else None
        connection.execute(
            "INSERT INTO chunks (chunk_id, source, title, text, embedding) VALUES (?, ?, ?, ?, ?)",
            (chunk.chunk_id, chunk.source, chunk.title, chunk.text, vector),
        )
        connection.execute(
            "INSERT INTO chunks_fts (chunk_id, title, text) VALUES (?, ?, ?)",
            (chunk.chunk_id, chunk.title, chunk.text),
        )
    connection.commit()
    logger.info(
        "[a11y_knowledge] Índice construído com %d chunks (embeddings: %s) em %s",
        len(corpus),
        "sim" if embeddings is not None else "não",
        path,
    )
    return connection


@contextlib.contextmanager
def _index_connection(chunks: list[KnowledgeChunk] | None = None) -> Iterator[sqlite3.Connection]:
    """Build (or reopen) the SQLite index and guarantee it is closed on exit."""
    connection = build_index(chunks)
    try:
        yield connection
    finally:
        connection.close()


def _fts_query(question: str) -> str:
    """Turn free-form user text into a safe FTS5 OR-query.

    User messages carry quotes, asterisks and parentheses, all of which are FTS5
    operators -- passing them raw raises `sqlite3.OperationalError`.
    """
    tokens = [token.lower() for token in _TOKEN_RE.findall(question) if len(token) >= _MIN_TOKEN_LEN]
    return " OR ".join(f'"{token}"' for token in dict.fromkeys(tokens))


def search_keyword(connection: sqlite3.Connection, question: str, limit: int = _CANDIDATE_K) -> list[str]:
    """BM25 ranking over the FTS5 index. Best match first."""
    query = _fts_query(question)
    if not query:
        return []
    rows = connection.execute(
        "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?",
        (query, limit),
    ).fetchall()
    return [str(row[0]) for row in rows]


def search_semantic(connection: sqlite3.Connection, question: str, limit: int = _CANDIDATE_K) -> list[str]:
    """Cosine ranking over the stored embeddings. Empty when unavailable."""
    rows = connection.execute("SELECT chunk_id, embedding FROM chunks WHERE embedding IS NOT NULL").fetchall()
    if not rows:
        return []

    query_embedding = embed_texts([question])
    if not query_embedding:
        return []

    scored: list[tuple[float, str]] = []
    for chunk_id, raw_vector in rows:
        try:
            vector = [float(value) for value in json.loads(raw_vector)]
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.error("[a11y_knowledge] Embedding inválido no chunk %s: %s", chunk_id, exc)
            continue
        scored.append((cosine_similarity(query_embedding[0], vector), str(chunk_id)))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk_id for _score, chunk_id in scored[:limit]]


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = _RRF_K) -> list[str]:
    """Fuse ranked id lists with RRF: score(d) = sum(1 / (k + rank(d))).

    Ranks are 1-based. Working on ranks instead of raw scores is precisely what
    lets a BM25 list and a cosine list be merged without normalisation.
    """
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + position)
            first_seen.setdefault(chunk_id, len(first_seen))
    # Ties broken by first appearance, so fusion is deterministic.
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], first_seen[chunk_id]))


def _load_chunks(connection: sqlite3.Connection, chunk_ids: list[str]) -> list[KnowledgeChunk]:
    if not chunk_ids:
        return []
    placeholders = ",".join("?" for _ in chunk_ids)
    rows = connection.execute(
        f"SELECT chunk_id, source, title, text FROM chunks WHERE chunk_id IN ({placeholders})",
        chunk_ids,
    ).fetchall()
    by_id = {
        str(row[0]): KnowledgeChunk(chunk_id=str(row[0]), source=str(row[1]), title=str(row[2]), text=str(row[3]))
        for row in rows
    }
    return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]


def retrieve(
    question: str,
    connection: sqlite3.Connection | None = None,
    candidate_k: int = _CANDIDATE_K,
) -> list[KnowledgeChunk]:
    """Hybrid retrieval: BM25 + embeddings, fused with RRF.

    If no connection is provided, a temporary index connection is opened and
    closed automatically before returning.
    """
    if connection is not None:
        keyword_ids = search_keyword(connection, question, candidate_k)
        semantic_ids = search_semantic(connection, question, candidate_k)
        fused = reciprocal_rank_fusion([keyword_ids, semantic_ids])
        return _load_chunks(connection, fused[:candidate_k])

    with _index_connection() as raw_conn:
        conn: sqlite3.Connection = raw_conn
        keyword_ids = search_keyword(conn, question, candidate_k)
        semantic_ids = search_semantic(conn, question, candidate_k)
        fused = reciprocal_rank_fusion([keyword_ids, semantic_ids])
        return _load_chunks(conn, fused[:candidate_k])


# --------------------------------------------------------------------------- #
# Rerank
# --------------------------------------------------------------------------- #

_RERANK_SYSTEM_PROMPT = (
    "You rank accessibility reference passages by how useful they are to answer a question. "
    "You receive a question and numbered candidate passages. "
    "Return ONLY a JSON array of objects, most useful first, each with the keys "
    '"index" (the integer label of the candidate) and "score" (0-10 relevance). '
    "Include every candidate exactly once. No prose, no markdown fences."
)


def _parse_rerank_order(raw: str, candidate_count: int) -> list[int]:
    """Extract the reranked candidate order. Raises ValueError on unusable output."""
    from backend.src.services.llm_client import extract_json_array

    decisions = extract_json_array(raw)
    ordered: list[int] = []
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        try:
            index = int(decision["index"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= index < candidate_count and index not in ordered:
            ordered.append(index)
    if not ordered:
        raise ValueError(f"Rerank devolveu nenhuma posição utilizável: {raw[:200]!r}")
    # Candidates the model dropped keep their fused order, at the back.
    ordered.extend(index for index in range(candidate_count) if index not in ordered)
    return ordered


async def rerank_chunks(question: str, candidates: list[KnowledgeChunk], top_k: int = _TOP_K) -> list[KnowledgeChunk]:
    """Reorder fused candidates by LLM-judged relevance, then cut to `top_k`.

    Mirrors the structured-decision pattern already used by `evaluate_research`.
    A rerank failure is not worth losing the turn over, so it degrades to the
    fused order (logged).
    """
    if len(candidates) <= 1:
        return candidates[:top_k]

    from backend.src.services.llm_client import call_llm

    listing = "\n\n".join(f"[{index}] {chunk.title}\n{chunk.text[:600]}" for index, chunk in enumerate(candidates))
    try:
        raw = await call_llm(
            system_prompt=_RERANK_SYSTEM_PROMPT,
            user_prompt=f"Question:\n{question}\n\nCandidates:\n{listing}",
            temperature=0.0,
            max_tokens=1024,
            agent_label="kb-rerank",
        )
        order = _parse_rerank_order(raw, len(candidates))
    except Exception as exc:
        logger.error("[a11y_knowledge] Rerank falhou (%s); mantendo a ordem da fusão RRF.", exc)
        return candidates[:top_k]

    return [candidates[index] for index in order][:top_k]


async def build_reference_block(question: str, top_k: int = _TOP_K) -> str:
    """Return the reference passages to inject in the system prompt for `question`.

    Empty string when nothing is relevant -- the prompt then simply carries no
    reference section, instead of the whole file.
    """
    if not question.strip():
        return ""
    try:
        with _index_connection() as raw_conn:
            conn: sqlite3.Connection = raw_conn
            candidates = retrieve(question, connection=conn)
            if not candidates:
                return ""
            selected = await rerank_chunks(question, candidates, top_k=top_k)
            return "\n\n".join(chunk.as_context() for chunk in selected)
    except (sqlite3.Error, OSError) as exc:
        logger.error("[a11y_knowledge] Recuperação falhou: %s", exc)
        return ""
