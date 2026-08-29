"""
preview.py
Endpoint FastAPI para servir o Live Preview Acessível (estilo Replit)
das páginas auditadas e corrigidas pela IA.
"""

import base64
import contextlib
import hashlib
import logging
import posixpath
from typing import Any

from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from starlette.requests import Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preview", tags=["preview"])

# Armazenamento em memória dos previews ativos (em produção usaria Redis/DB)
_preview_store: dict[str, dict[str, Any]] = {}

# Script que NÓS injetamos (não vem do HTML de terceiros) só pra avisar o
# LivePreviewModal, via postMessage, qual página/modo carregou -- assim a
# barra de chips consegue se sincronizar quando o usuário navega clicando
# num <a>/<area> reescrito, sem precisar ler window.location entre origens
# diferentes (o preview roda numa porta própria do backend).
_PREVIEW_SYNC_SCRIPT = (
    "(function(){"
    "try{"
    "var m=window.location.pathname.match(/\\/preview\\/render\\/([^/]+)\\/(\\d+)/);"
    "if(!m)return;"
    "window.parent.postMessage({"
    "source:'a11y-live-preview',"
    "sessionId:m[1],"
    "pageIndex:parseInt(m[2],10),"
    "mode:new URLSearchParams(window.location.search).get('mode')||'fixed'"
    "},'*');"
    "}catch(e){}"
    "})();"
)


def _preview_sync_script_hash() -> str:
    """CSP hash-source do script acima -- calculado a partir do próprio texto pra
    nunca ficar dessincronizado se o script mudar."""
    digest = hashlib.sha256(_PREVIEW_SYNC_SCRIPT.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


# Esta rota renderiza HTML de terceiros (não confiável, vindo de análise de URL ou
# upload do usuário) no mesmo domínio da aplicação. O propósito do preview é
# puramente visual (mostrar a correção de acessibilidade) -- por isso o conteúdo
# é higienizado (remove <script>/<iframe>/<object>/<embed>, atributos on*, e URLs
# javascript:/data:text/html) e a resposta recebe uma CSP própria, mais restritiva
# que o default global do app. script-src só libera, por hash exato, o ÚNICO
# script que nós mesmos injetamos (_PREVIEW_SYNC_SCRIPT) -- qualquer script vindo
# do HTML auditado já foi removido antes e, mesmo que escapasse da sanitização,
# não bateria o hash e seria bloqueado pelo navegador.
_PREVIEW_CSP = (
    "default-src 'self'; "
    f"script-src '{_preview_sync_script_hash()}'; "
    "object-src 'none'; "
    "frame-src 'none'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "base-uri 'none'; "
    # 'self' em vez de 'none': _rewrite_internal_links reescreve <form action>
    # que apontam pra outra página da sessão pro próprio endpoint de preview
    # (mesma origem) -- formulários que continuarem apontando pra fora
    # (externos) já foram neutralizados (action="#") antes de chegar aqui.
    "form-action 'self'"
)

# Origens de desenvolvimento onde o frontend pode incorporar o preview em um
# iframe. Em produção o header Origin/Referer da requisição ao preview é usado
# para permitir dinamicamente a origem que fez a requisição.
_DEFAULT_FRONTEND_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:8081",
    "http://localhost:19006",
)


def _preview_csp_with_frame_ancestors(request: Request | None) -> str:
    """Retorna a CSP do preview com frame-ancestors permitindo o frontend.

    O preview é servido na origem do backend e incorporado via iframe pelo frontend.
    Para evitar clickjacking genérico, mantemos o resto da CSP restrita e
    permitimos apenas a origem que requisitou o preview (ou as origens locais
    padrão quando nenhum header confiável está presente).
    """
    origins: list[str] = []
    if request is not None:
        origin = request.headers.get("origin")
        if origin:
            origins.append(origin)
        referer = request.headers.get("referer")
        if referer:
            with contextlib.suppress(IndexError):
                origins.append(f"{referer.split('://')[0]}://{referer.split('://')[1].split('/')[0]}")
    if not origins:
        origins = list(_DEFAULT_FRONTEND_ORIGINS)

    # 'self' garante que, se frontend e backend compartilharem origem, ainda funcione.
    ancestors = " ".join(["'self'"] + origins)
    return f"{_PREVIEW_CSP}; frame-ancestors {ancestors}"


def _build_page_index(pages: list[dict[str, Any]]) -> dict[str, int]:
    """Mapeia o caminho normalizado (title) de cada página da sessão ao seu índice,
    pra que links internos do HTML original (<a href="sobre.html">) consigam
    resolver pra outra página *dentro* do preview."""
    index_map: dict[str, int] = {}
    for i, page in enumerate(pages):
        title = (page.get("title") or "").strip()
        if not title:
            continue
        normalized = posixpath.normpath(title).lstrip("./")
        index_map[normalized] = i
    return index_map


_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "javascript:", "data:")
_OUT_OF_SCOPE_NOTE = "(fora do preview — página sem correções de acessibilidade)"


def _resolve_relative_link(current_path: str, href: str) -> str:
    """Resolve um href relativo contra o diretório da página atual, mesma lógica
    usada para resolver <img src> em chat_tools._run_fixes_and_generate_zip."""
    html_dir = posixpath.dirname(current_path)
    resolved = posixpath.normpath(posixpath.join(html_dir, href))
    return resolved.lstrip("./").lstrip("/")


def _resolve_internal_target(current_path: str, target: str, page_index: dict[str, int]) -> int | None:
    """Resolve um href/action relativo (ignorando #hash e ?query) pro índice da
    página correspondente na sessão de preview, ou None se apontar pra fora dela."""
    path_part = target.split("#", 1)[0].split("?", 1)[0]
    if not path_part:
        return None
    resolved = _resolve_relative_link(current_path, path_part)
    target_index = page_index.get(resolved)
    if target_index is None:
        base = posixpath.basename(resolved)
        for key, idx in page_index.items():
            if posixpath.basename(key) == base:
                target_index = idx
                break
    return target_index


def _mark_out_of_scope(tag: Any, attr: str) -> None:
    """Deixa <a>/<area>/<form> inertes quando o alvo é uma página real do site
    que não passou pelo fixer (sem issues) -- fora do escopo da sessão de
    preview -- em vez de deixar um href/action quebrado (404) dentro do iframe."""
    tag[attr] = "#"
    if tag.name == "form":
        # aria-disabled não tem semântica em <form>; o que trava a navegação
        # de fato pro usuário é desabilitar os controles de envio.
        for control in tag.find_all(["button", "input"]):
            control_type = str(control.get("type") or "").lower()
            is_submit = (control.name == "button" and control_type in ("", "submit")) or (
                control.name == "input" and control_type in ("submit", "image")
            )
            if is_submit:
                control["disabled"] = "disabled"
                control["title"] = _OUT_OF_SCOPE_NOTE
    else:
        tag["aria-disabled"] = "true"
        existing_title = tag.get("title", "")
        tag["title"] = (existing_title + " " if existing_title else "") + _OUT_OF_SCOPE_NOTE


def _rewrite_internal_links(
    soup: BeautifulSoup,
    *,
    current_path: str,
    page_index: dict[str, int],
    session_id: str,
    mode: str,
) -> None:
    """Reescreve <a href>, <area href> (mapas de imagem) e <form action> que
    apontam pra outras páginas da sessão de preview, pra virarem navegação real
    dentro do iframe (troca pra /preview/render/{session_id}/{index}?mode=...).
    Alvos fora do escopo do preview (páginas sem correção, âncoras, mailto,
    externos) ficam inertes em vez de quebrados. Atributos on* continuam
    removidos pela sanitização -- reviver navegação por eles anularia a
    proteção contra XSS que existe porque esse HTML vem de terceiros."""
    for tag in soup.find_all(["a", "area"], href=True):
        href = str(tag["href"]).strip()
        if not href or href.startswith("#") or href.lower().startswith(_EXTERNAL_SCHEMES):
            continue

        target_index = _resolve_internal_target(current_path, href, page_index)
        if target_index is not None:
            tag["href"] = f"/preview/render/{session_id}/{target_index}?mode={mode}"
        else:
            _mark_out_of_scope(tag, "href")

    for tag in soup.find_all("form", action=True):
        action = str(tag["action"]).strip()
        if not action or action.startswith("#") or action.lower().startswith(_EXTERNAL_SCHEMES):
            continue

        target_index = _resolve_internal_target(current_path, action, page_index)
        if target_index is not None:
            tag["action"] = f"/preview/render/{session_id}/{target_index}?mode={mode}"
            # O preview não roda o backend do site auditado -- reescrever o
            # action só demonstra a navegação entre páginas corrigidas, então
            # força GET em vez de depender de uma rota POST que não processaria
            # os dados enviados de verdade.
            tag["method"] = "get"
        else:
            _mark_out_of_scope(tag, "action")


def _sanitize_preview_html(
    html_content: str,
    *,
    link_ctx: dict[str, Any] | None = None,
) -> str:
    """Remove vetores de execução de script antes de servir HTML não confiável.
    Se `link_ctx` for passado, também reescreve links internos entre páginas
    da sessão de preview (ver `_rewrite_internal_links`)."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup.find_all(["script", "iframe", "object", "embed"]):
        tag.decompose()
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            attr_lower = attr.lower()
            value = tag.attrs.get(attr)
            value_str = value if isinstance(value, str) else " ".join(value or [])
            if attr_lower.startswith("on") or attr_lower in ("href", "src", "action") and value_str.strip().lower().startswith(
                ("javascript:", "data:text/html")
            ):
                del tag.attrs[attr]

    if link_ctx is not None:
        _rewrite_internal_links(
            soup,
            current_path=link_ctx["current_path"],
            page_index=link_ctx["page_index"],
            session_id=link_ctx["session_id"],
            mode=link_ctx["mode"],
        )

    return str(soup)


class PreviewSessionRequest(BaseModel):
    pages: list[dict[str, str]]  # list of {"title": str, "original_html": str, "fixed_html": str}


def register_preview_session(pages: list[dict[str, Any]]) -> str:
    """Creates a Live Preview session and returns its id. Shared by the HTTP route and
    the `open_live_preview` chat tool (backend.src.services.chat_tools) -- both write
    into the same in-process _preview_store, so a session opened by either path is
    renderable by GET /preview/render/{session_id}/{page_index}."""
    import uuid
    session_id = str(uuid.uuid4())[:8]
    _preview_store[session_id] = {"pages": pages}
    logger.info("[Preview] Sessão de Live Preview criada: id=%s (total de %d páginas)", session_id, len(pages))
    return session_id


@router.post("/create")
async def create_preview_session(body: PreviewSessionRequest) -> dict[str, str]:
    session_id = register_preview_session(body.pages)
    return {"session_id": session_id}


@router.get("/render/{session_id}/{page_index}")
async def render_preview_page(
    request: Request,
    session_id: str,
    page_index: int,
    mode: str = "fixed",
) -> Response:
    session = _preview_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão de preview não encontrada ou expirada.")

    pages = session.get("pages", [])
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(status_code=400, detail="Índice de página inválido.")

    page = pages[page_index]
    raw_html = page.get("fixed_html") if mode == "fixed" else page.get("original_html")
    link_ctx = {
        "current_path": page.get("title") or "",
        "page_index": _build_page_index(pages),
        "session_id": session_id,
        "mode": mode,
    }
    html_content = _sanitize_preview_html(raw_html or "", link_ctx=link_ctx)

    # Injeta estilos acessíveis do Live Preview (Destaques WAI-ARIA)
    injected_style = """
    <style id="a11y-preview-style">
        [data-a11y-fixed="true"] {
            outline: 3px solid #10b981 !important;
            outline-offset: 2px !important;
            position: relative;
        }
        [data-a11y-fixed="true"]::before {
            content: "✓ Acessível (IA)";
            position: absolute;
            top: -22px;
            left: 0;
            background: #10b981;
            color: #ffffff;
            font-size: 11px;
            font-family: sans-serif;
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 4px;
            z-index: 99999;
        }
    </style>
    """
    if html_content and "</head>" in html_content:
        final_html = html_content.replace("</head>", f"{injected_style}</head>")
    else:
        final_html = f"{injected_style}{html_content or ''}"

    injected_script = f"<script>{_PREVIEW_SYNC_SCRIPT}</script>"
    if "</body>" in final_html:
        final_html = final_html.replace("</body>", f"{injected_script}</body>")
    else:
        final_html = f"{final_html}{injected_script}"

    return Response(
        content=final_html,
        media_type="text/html",
        headers={"Content-Security-Policy": _preview_csp_with_frame_ancestors(request)},
    )
