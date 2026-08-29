"""
context_compressor.py
Compressor de contexto HTML para agentes de acessibilidade.

Tenta usar a biblioteca headroom para compressão estrutural.
Caso headroom não esteja instalada, executa compressão baseada em BeautifulSoup:
- Remove comentários HTML.
- Esvazia o conteúdo das tags <script> e <style> volumosas, mas preserva a estrutura.
- Simplifica elementos <svg> removendo caminhos/polígonos de desenho complexos (path, polygon, circle) se eles não tiverem atributos de acessibilidade (como aria-label, aria-labelledby, ou title), reduzindo consideravelmente o tamanho, mas mantendo a presença semântica do SVG.
- Substitui strings longas de dados embutidos (base64) por placeholders.
- Compacta espaços em branco.
"""

import logging
import re
import time

logger = logging.getLogger(__name__)


def compress(html_content: str, max_chars: int = 32000) -> str:
    """
    Comprime o HTML para otimizar o contexto dos agentes de auditoria.
    """
    if not html_content or len(html_content) <= max_chars:
        return html_content

    start_time = time.time()
    original_len = len(html_content)

    # 1. Tenta usar headroom prioritariamente
    try:
        from headroom import compress as _headroom_compress

        # headroom estima tokens; usamos uma heurística de 0.25 tokens por caractere
        max_tokens = int(max_chars * 0.25)
        compressed = _headroom_compress(html_content, max_tokens=max_tokens)
        elapsed = int((time.time() - start_time) * 1000)
        logger.info("[context_compressor:headroom] %d -> %d chars (%dms)", original_len, len(compressed), elapsed)
        return compressed
    except ImportError:
        pass

    # 2. Fallback local usando BeautifulSoup
    try:
        from bs4 import BeautifulSoup, Comment

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove todos os comentários HTML
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Esvazia o conteúdo de tags script e style, mas mantém as tags para que os agentes de framework/CSS saibam que existem
        for tag in soup.find_all(["script", "style"]):
            if tag.string and len(tag.string) > 100:
                tag.string = "/* [conteúdo omitido para compressao] */"

        # Simplifica tags SVG (remove tags internas de desenho como path, polygon, g, circle se não tiverem tags de acessibilidade)
        _SVG_CRITICAL_TAGS = ("form", "input", "select", "textarea", "button", "label")
        for svg in soup.find_all("svg"):
            has_a11y_attributes = any(svg.has_attr(attr) for attr in ["aria-label", "aria-labelledby", "title", "role"])
            # SVG pode legalmente conter <foreignObject><form>...</form></foreignObject> (widgets
            # interativos). Achado real: um <svg> de 33KB sem atributos a11y continha um <form>
            # de busca inteiro; svg.clear() apagava o form silenciosamente antes de qualquer
            # logica de priorizacao rio abaixo sequer rodar. Nunca limpa um svg com descendente critico.
            if svg.find(list(_SVG_CRITICAL_TAGS)) is not None:
                continue
            # Se não houver atributos de acessibilidade no próprio SVG, removemos seus desenhos internos volumosos
            if not has_a11y_attributes:
                # Mantém a tag svg mas limpa os filhos volumosos
                svg.clear()
                svg.append("<!-- SVG desenho omitido -->")
            else:
                # Se tem atributos de acessibilidade, limpa apenas os filhos que não contêm texto ou títulos
                for child in list(svg.children):
                    # Se o elemento de desenho não tiver id/classe ou tags de a11y em si, remove
                    if child.name in [
                        "path",
                        "polygon",
                        "rect",
                        "circle",
                        "line",
                        "ellipse",
                        "polyline",
                        "g",
                    ] and not any(child.has_attr(a) for a in ["id", "aria-label", "role"]):
                        child.extract()

        # Remove imagens embutidas em base64 gigantes
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src.startswith("data:") and len(src) > 120:
                img["src"] = "data:image/placeholder;base64,[dados_omitidos]"

        # Se ainda estourar o orcamento, remove elementos de baixa prioridade
        # (maiores primeiro) ANTES de qualquer corte por posicao bruta. Achado
        # real: um corte por `[:max_chars]` cru caiu no meio de um bloco de CSS
        # de terceiros (SDK do Facebook) e apagou 100% dos <form>/<input> reais
        # de uma pagina -- um falso-negativo silencioso numa ferramenta de
        # auditoria de acessibilidade.
        #
        # Duas camadas de prioridade, nao uma so: tratar TODO <a>/<img>/heading
        # como "importante" (tentativa inicial) protege demais numa pagina real
        # -- a maioria dos elementos de qualquer site vira <a>/<img>, entao quase
        # nada e removido e o corte final ainda atropela os forms por azar
        # posicional (achado real: 366 de 426 elementos "importantes", so 60
        # removiveis, forms continuaram sumindo). CRITICAL nunca e removido;
        # SECONDARY so e removido se sobrar orcamento negativo mesmo apos
        # remover tudo que nao e nem CRITICAL nem SECONDARY.
        if len(str(soup)) > max_chars:
            critical = {
                "form",
                "fieldset",
                "legend",
                "label",
                "input",
                "select",
                "textarea",
                "button",
            }
            secondary = {
                "img",
                "svg",
                "a",
                "nav",
                "main",
                "header",
                "footer",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "table",
                "th",
                "caption",
            }
            important_attrs = ("role", "aria-label", "aria-labelledby", "aria-describedby")

            def _tier(el) -> int:
                """0 = nunca remover, 1 = so remover se 0-only nao bastar, 2 = remover primeiro."""
                if el.name in critical or el.find(list(critical)) is not None:
                    return 0
                if el.name in secondary or any(el.has_attr(a) for a in important_attrs):
                    return 1
                return 2

            for tier in (2, 1):
                if len(str(soup)) <= max_chars:
                    break
                candidates = [el for el in soup.find_all(True) if not el.decomposed and _tier(el) == tier]
                candidates.sort(key=lambda el: len(str(el)), reverse=True)
                for el in candidates:
                    if len(str(soup)) <= max_chars:
                        break
                    if el.decomposed:
                        continue
                    el.decompose()

        compressed_html = str(soup)

        # Remove espaços em branco redundantes e quebras de linha múltiplas
        compressed_html = re.sub(r"[ \t]+", " ", compressed_html)
        compressed_html = re.sub(r"[\r\n]+", "\n", compressed_html)

        elapsed = int((time.time() - start_time) * 1000)
        ratio = len(compressed_html) / original_len if original_len else 1.0
        logger.info(
            "[context_compressor:BS4] %d -> %d chars (%.1f%%, %dms)",
            original_len,
            len(compressed_html),
            ratio * 100,
            elapsed,
        )

        # Ultimo recurso: se mesmo removendo TODO elemento de baixa prioridade o
        # conteudo importante sozinho ainda estourar o limite (paginas muito
        # densas -- ex.: 993 elementos, ~50KB so de conteudo interativo/estrutural
        # observado em teste real), trunca por posicao. So alcanca este ponto
        # depois de proteger o quanto for possivel; ainda assim pode cortar
        # elemento interativo real, entao avisa alto (WARNING, nao INFO) em vez
        # de mascarar como uma compressao normal e bem-sucedida.
        if len(compressed_html) > max_chars:
            logger.warning(
                "[context_compressor] Conteudo importante (%d chars) excede max_chars=%d mesmo apos "
                "remover todo elemento de baixa prioridade -- corte final por posicao pode eliminar "
                "form/input/button reais. Pagina muito densa para o orcamento de contexto atual.",
                len(compressed_html),
                max_chars,
            )
            compressed_html = compressed_html[:max_chars] + "\n<!-- [HTML truncado para limite de contexto] -->"

        return compressed_html

    except Exception as exc:
        logger.error("[context_compressor] Falha no fallback BS4: %s. Utilizando truncamento bruto.", exc)
        return html_content[:max_chars]
