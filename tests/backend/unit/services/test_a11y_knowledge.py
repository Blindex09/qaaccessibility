"""Testes da base de conhecimento local com recuperação híbrida (BM25 + embeddings).

Feature real: antes disto NÃO existia base de conhecimento nenhuma. O
`chat_runtime` colava o `a11y_reference.md` inteiro (~12.5 KB) no system prompt
a cada turno, relevante ou não, e a única "recuperação" era busca web de
terceiros. Agora o documento é fatiado por seção, indexado em SQLite FTS5
(BM25) + embeddings do provider já configurado, fundido por Reciprocal Rank
Fusion e reordenado por um rerank LLM antes de virar contexto.
"""

import json
import sqlite3
from contextlib import closing

import pytest

from backend.src.services import a11y_knowledge as kb


@pytest.fixture
def temp_index_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    return tmp_path


def _chunks() -> list[kb.KnowledgeChunk]:
    return [
        kb.KnowledgeChunk(
            chunk_id="doc#0",
            source="doc.md",
            title="Modal / Diálogo",
            text="O foco deve ser movido para dentro do modal e a tecla Escape fecha o diálogo.",
        ),
        kb.KnowledgeChunk(
            chunk_id="doc#1",
            source="doc.md",
            title="Contraste Visual e APCA",
            text="Relação de contraste mínima de 4.5:1 para texto normal segundo o critério 1.4.3.",
        ),
        kb.KnowledgeChunk(
            chunk_id="doc#2",
            source="doc.md",
            title="Tabelas em documentos",
            text="Tabelas precisam de linha de cabeçalho marcada para leitores de tela.",
        ),
    ]


def _index_with_embeddings(vectors: dict[str, list[float]], monkeypatch) -> sqlite3.Connection:
    chunks = _chunks()
    order = [f"{c.title}\n{c.text}" for c in chunks]
    monkeypatch.setattr(kb, "embed_texts", lambda texts: [vectors[t] for t in texts] if texts == order else None)
    connection = kb.build_index(chunks)
    monkeypatch.setattr(kb, "embed_texts", lambda texts: [vectors[t] for t in texts])
    return connection


class TestReciprocalRankFusion:
    def test_fusion_weights_by_rank_position_not_by_number_of_hits(self):
        """RRF soma 1/(k+rank): a POSIÇÃO na lista pesa, não só aparecer nela.

        "b" e "c" aparecem nas duas listas, então uma fusão que apenas contasse
        ocorrências os empataria e o desempate por ordem de chegada colocaria
        "b" na frente. Com 1/(k+rank), "c" (ranks 3 e 1) vence "b" (ranks 2 e 3).
        """
        keyword = ["a", "b", "c"]
        semantic = ["c", "d", "b"]

        fused = kb.reciprocal_rank_fusion([keyword, semantic], k=1)

        # c = 1/4 + 1/2 = 0.750 ; b = 1/3 + 1/4 = 0.583 ; a = 1/2 = 0.500 ; d = 1/3
        assert fused == ["c", "b", "a", "d"]

    def test_fusion_is_rank_based_so_scores_never_need_normalising(self):
        """Com o k padrão (60) as diferenças achatam, mas a ordem segue os ranks."""
        fused = kb.reciprocal_rank_fusion([["a", "b", "c"], ["c", "a", "d"]], k=60)

        # a = 1/61+1/62 ; c = 1/63+1/61 ; b = 1/62 ; d = 1/63
        assert fused[:2] == ["a", "c"]
        assert set(fused) == {"a", "b", "c", "d"}

    def test_item_ranked_high_in_only_one_list_still_survives(self):
        fused = kb.reciprocal_rank_fusion([["x"], ["y", "z"]], k=60)
        assert fused[0] == "x"
        assert "z" in fused

    def test_empty_rankings_produce_no_results(self):
        assert kb.reciprocal_rank_fusion([[], []]) == []


class TestChunking:
    def test_splits_markdown_by_heading_and_keeps_the_heading_path(self):
        content = (
            "# Título\nintro\n\n"
            "## 2. Padrões de Teclado\nregra geral\n\n"
            "### A. Modal\nfoco vai para dentro\n\n"
            "## 3. Linter\nregras jsx\n"
        )

        chunks = kb.chunk_markdown(content, "doc.md")

        titles = [c.title for c in chunks]
        assert titles == ["2. Padrões de Teclado", "2. Padrões de Teclado > A. Modal", "3. Linter"]
        assert "foco vai para dentro" in chunks[1].text

    def test_chunks_are_materially_smaller_than_the_whole_document(self):
        corpus = kb.load_corpus()
        assert len(corpus) > 5
        assert all(len(c.text) < 6000 for c in corpus)


class TestKeywordLeg:
    def test_bm25_finds_the_chunk_that_shares_the_query_terms(self, temp_index_dir, monkeypatch):
        monkeypatch.setattr(kb, "embed_texts", lambda texts: None)
        with closing(kb.build_index(_chunks())) as connection:
            assert kb.search_keyword(connection, "contraste mínimo de texto")[0] == "doc#1"

    def test_query_with_fts5_operators_does_not_raise(self, temp_index_dir, monkeypatch):
        """Mensagens reais trazem aspas/asteriscos, que são operadores do FTS5."""
        monkeypatch.setattr(kb, "embed_texts", lambda texts: None)
        with closing(kb.build_index(_chunks())) as connection:
            assert kb.search_keyword(connection, 'o que é "modal" (dialogo)? * ') == ["doc#0"]


class TestHybridRetrieval:
    def test_semantically_relevant_chunk_without_keyword_overlap_is_retrieved(
        self, temp_index_dir, monkeypatch
    ):
        """O ganho central do híbrido: recuperar por significado, não por palavra.

        A pergunta não repete NENHUM termo do chunk de contraste (que fala em
        "contraste"/"1.4.3"), então o BM25 sozinho nunca o traria -- só a perna
        densa o encontra, e a fusão RRF tem de preservá-lo.
        """
        chunks = _chunks()
        vectors = {
            f"{chunks[0].title}\n{chunks[0].text}": [1.0, 0.0, 0.0],
            f"{chunks[1].title}\n{chunks[1].text}": [0.0, 1.0, 0.0],
            f"{chunks[2].title}\n{chunks[2].text}": [0.0, 0.0, 1.0],
        }
        with closing(_index_with_embeddings(vectors, monkeypatch)) as connection:
            question = "estão as cores legíveis por quem enxerga mal?"
            vectors[question] = [0.0, 1.0, 0.0]

            assert kb.search_keyword(connection, question) == []
            retrieved = [c.chunk_id for c in kb.retrieve(question, connection=connection)]

            assert "doc#1" in retrieved

    def test_retrieval_degrades_to_keyword_only_without_embeddings(self, temp_index_dir, monkeypatch):
        monkeypatch.setattr(kb, "embed_texts", lambda texts: None)
        with closing(kb.build_index(_chunks())) as connection:
            retrieved = [c.chunk_id for c in kb.retrieve("tabelas com cabeçalho", connection=connection)]
            assert retrieved == ["doc#2"]

    def test_invalid_stored_embedding_is_reported_and_skipped(self, temp_index_dir, monkeypatch, caplog):
        monkeypatch.setattr(kb, "embed_texts", lambda texts: None)
        with closing(kb.build_index(_chunks())) as connection:
            connection.execute("UPDATE chunks SET embedding = ? WHERE chunk_id = ?", ("not-json", "doc#0"))
            connection.execute(
                "UPDATE chunks SET embedding = ? WHERE chunk_id = ?", (json.dumps([0.0, 1.0]), "doc#1")
            )
            monkeypatch.setattr(kb, "embed_texts", lambda texts: [[0.0, 1.0]])

            with caplog.at_level("ERROR"):
                assert kb.search_semantic(connection, "qualquer coisa") == ["doc#1"]
            assert "Embedding inválido" in caplog.text


class TestRerank:
    async def test_rerank_reorders_candidates_by_judged_relevance(self, monkeypatch):
        """O rerank tem de mudar a ordem, não só repassar a fusão."""
        candidates = _chunks()

        async def fake_call_llm(**kwargs):
            assert "Question:" in kwargs["user_prompt"]
            return json.dumps([{"index": 2, "score": 9}, {"index": 0, "score": 4}, {"index": 1, "score": 1}])

        monkeypatch.setattr("backend.src.services.llm_client.call_llm", fake_call_llm)

        reranked = await kb.rerank_chunks("como marcar cabeçalho de tabela?", candidates, top_k=2)

        assert [c.chunk_id for c in reranked] == ["doc#2", "doc#0"]

    async def test_rerank_failure_keeps_the_fused_order(self, monkeypatch, caplog):
        candidates = _chunks()

        async def broken_call_llm(**kwargs):
            raise RuntimeError("provider fora do ar")

        monkeypatch.setattr("backend.src.services.llm_client.call_llm", broken_call_llm)

        with caplog.at_level("ERROR"):
            reranked = await kb.rerank_chunks("qualquer", candidates, top_k=2)

        assert [c.chunk_id for c in reranked] == ["doc#0", "doc#1"]
        assert "Rerank falhou" in caplog.text

    async def test_candidates_dropped_by_the_model_are_kept_at_the_back(self, monkeypatch):
        candidates = _chunks()

        async def partial_call_llm(**kwargs):
            return json.dumps([{"index": 1, "score": 9}])

        monkeypatch.setattr("backend.src.services.llm_client.call_llm", partial_call_llm)

        reranked = await kb.rerank_chunks("qualquer", candidates, top_k=3)
        assert [c.chunk_id for c in reranked] == ["doc#1", "doc#0", "doc#2"]


class _CapturingAgent:
    """Captura o system prompt efetivamente montado pelo chat_runtime."""

    last_kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs

    def run_conversation(self, user_message, **_k):
        return {"final_response": "ok", "failed": False}


class TestSystemPromptInjection:
    async def test_prompt_carries_retrieved_chunks_not_the_whole_file(self, temp_index_dir, monkeypatch):
        """Antes: o arquivo inteiro ia no prompt todo turno. Agora: só o recuperado."""
        from unittest.mock import patch

        from backend.src.services.chat_runtime import stream_chat

        reference_path = kb.os.path.join(kb._RESOURCES_DIR, "a11y_reference.md")
        with open(reference_path, encoding="utf-8") as handle:
            whole_file = handle.read()

        # Sem embeddings e sem rerank de rede: exercita a perna BM25 real.
        monkeypatch.setattr(kb, "embed_texts", lambda texts: None)

        async def no_network_rerank(question, candidates, top_k=4):
            return candidates[:top_k]

        monkeypatch.setattr(kb, "rerank_chunks", no_network_rerank)

        question = "qual o contraste mínimo exigido para texto normal?"
        with patch("backend.src.services.chat_runtime.AIAgent", new=_CapturingAgent):
            _ = [event async for event in stream_chat(question, history=[])]

        prompt = _CapturingAgent.last_kwargs["ephemeral_system_prompt"]

        # A seção de referência existe e fala do assunto perguntado...
        assert "AUTHORITATIVE ACCESSIBILITY REFERENCE" in prompt
        assert "contraste" in prompt.lower()
        # ...mas o documento inteiro não está mais lá.
        assert whole_file not in prompt
        # Orçamento real: o que foi recuperado é uma fração do despejo anterior.
        reference_block = prompt.split("AUTHORITATIVE ACCESSIBILITY REFERENCE", 1)[1]
        assert len(reference_block) < len(whole_file) * 0.5

    async def test_empty_question_injects_no_reference_at_all(self):
        assert await kb.build_reference_block("   ") == ""


class TestGeminiEmbeddingModel:
    """
    `gemini-embedding-001` foi desligado pelo Google e substituído por
    `gemini-embedding-2`. Enquanto o id antigo ficou no código, a perna densa
    do retrieval híbrido caía em silêncio para keyword-only em todo usuário
    Gemini (sem crash, só recuperação pior).
    """

    def test_gemini_branch_targets_the_current_model(self, monkeypatch):
        captured: dict = {}

        class _FakeEmbedding:
            values = [0.1, 0.2, 0.3]

        class _FakeModels:
            def embed_content(self, *, model, contents):
                captured["model"] = model
                captured.setdefault("calls", []).append(contents)
                return type("_R", (), {"embeddings": [_FakeEmbedding()]})()

        class _FakeClient:
            def __init__(self, *, api_key):
                self.models = _FakeModels()

        fake_genai = type("_G", (), {"Client": _FakeClient})
        monkeypatch.setitem(
            __import__("sys").modules, "google", type("_P", (), {"genai": fake_genai})
        )
        monkeypatch.setitem(__import__("sys").modules, "google.genai", fake_genai)

        vectors = kb._embed_gemini(["primeiro", "segundo"], "fake-key")

        assert captured["model"] == "gemini-embedding-2"
        assert captured["model"] != "gemini-embedding-001"
        # Um embedding por texto: com vários `contents` o modelo devolveria um
        # único vetor agregado, quebrando o alinhamento com os chunks.
        assert captured["calls"] == ["primeiro", "segundo"]
        assert vectors == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]

    def test_changing_the_embedding_model_invalidates_the_on_disk_index(self, monkeypatch):
        """
        Os espaços vetoriais dos dois modelos são incompatíveis: reaproveitar o
        índice antigo não gera erro, só similaridade sem sentido.
        """
        chunks = _chunks()
        before = kb._corpus_fingerprint(chunks)
        monkeypatch.setattr(kb, "_EMBEDDING_SPACE_VERSION", "text-embedding-3-small|outro-modelo")
        after = kb._corpus_fingerprint(chunks)

        assert before != after
        assert kb.index_path(before) != kb.index_path(after)


class TestEmbedTextsProviderDispatch:
    """Achado real (2026-08-27, testado ao vivo com chaves reais da conta):
    nenhum dos dois -- Ollama Cloud (POST /v1/embeddings e /api/embeddings
    devolvem 404 "not found"; /api/embed nativo devolve 401 mesmo para nomes
    de modelo de embedding reais que nao existem na conta -- nao e questao de
    modelo, a rota inteira recusa a chave) nem xAI (nunca publicou endpoint de
    embeddings) -- oferece embeddings hoje. Antes desta correcao, `embed_texts`
    tentava mesmo assim para os tres (ollama/ollama-cloud/xai), sempre falhando
    depois de uma chamada de rede real -- desperdicio garantido a cada turno de
    chat quando o provider ativo era um desses. Agora e tratado como
    conhecido-nao-suportado ANTES de tentar a rede."""

    def _settings_for(self, provider, monkeypatch):
        cfg = {"provider": provider, "model": "alto", "api_key": "sk-test", "base_url": None}
        settings = type("S", (), {"chat_model_config": lambda self: cfg})()
        monkeypatch.setattr(
            "backend.src.config.settings.get_settings", lambda: settings
        )

    @pytest.mark.parametrize("provider", ["xai", "ollama", "ollama-cloud"])
    def test_known_unsupported_providers_never_hit_the_network(self, monkeypatch, provider):
        self._settings_for(provider, monkeypatch)
        monkeypatch.setattr(
            kb, "_embed_openai_compatible",
            lambda *a, **kw: pytest.fail("nao deveria tentar a rede para provider sem embeddings"),
        )
        monkeypatch.setattr(
            kb, "_embed_gemini",
            lambda *a, **kw: pytest.fail("nao deveria tentar a rede para provider sem embeddings"),
        )

        result = kb.embed_texts(["texto de teste"])

        assert result is None

    def test_openai_still_calls_the_openai_compatible_client(self, monkeypatch):
        self._settings_for("openai", monkeypatch)
        captured = {}

        def _fake_embed(texts, api_key, base_url):
            captured["texts"] = texts
            captured["api_key"] = api_key
            return [[0.1, 0.2]]

        monkeypatch.setattr(kb, "_embed_openai_compatible", _fake_embed)

        result = kb.embed_texts(["texto de teste"])

        assert result == [[0.1, 0.2]]
        assert captured["texts"] == ["texto de teste"]

    def test_gemini_still_calls_the_gemini_client(self, monkeypatch):
        self._settings_for("gemini", monkeypatch)
        monkeypatch.setattr(kb, "_embed_gemini", lambda texts, api_key: [[0.3, 0.4]])

        result = kb.embed_texts(["texto de teste"])

        assert result == [[0.3, 0.4]]
