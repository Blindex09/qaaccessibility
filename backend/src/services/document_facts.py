"""Fatos objetivos da estrutura de documentos (Word, PowerPoint, PDF, EPUB), sem nenhum julgamento.

A extração de texto de um documento joga fora justamente o que decide sua acessibilidade: se há título e idioma, se as
imagens têm texto alternativo, se a tabela marca a linha de cabeçalho, se o PDF é marcado (tagged). Sem esses fatos o
modelo não tem como julgar e só enxerga o texto. Aqui o sistema apenas LÊ a estrutura e relata o que está lá (ou não
está); decidir o que isso significa para a pessoa continua sendo da IA (regra 2 do CLAUDE.md).

Cada função devolve linhas de texto. Quando algo não pode ser lido, a linha diz isso: nunca se omite em silêncio,
porque ausência de dado não é ausência de problema (regra 11).
"""

import io
import logging
import re
import zipfile
from typing import Any

logger = logging.getLogger(__name__)

_HEADER = "[Fatos observados na estrutura do arquivo (leitura objetiva, sem julgamento)]"
_MAX_LISTED = 25  # só limita o tamanho da lista no texto; a contagem total sempre vem inteira
_MAX_STRUCT_NODES = 50000  # proteção contra PDF gigante ou malformado; se atingido, a leitura diz que é parcial


def _block(lines: list[str]) -> str:
    return _HEADER + "\n" + "\n".join(f"- {line}" for line in lines) + "\n\n"


def _listed(items: list[str]) -> str:
    shown = items[:_MAX_LISTED]
    more = len(items) - len(shown)
    return "; ".join(shown) + (f"; e mais {more}" if more > 0 else "")


# ---------------------------------------------------------------------------------------------------- DOCX
def docx_facts(data: bytes) -> str:
    try:
        import docx
        from docx.oxml.ns import qn

        document = docx.Document(io.BytesIO(data))
        body = document.element.body
        lines: list[str] = []

        props = document.core_properties
        lines.append(f"Título nas propriedades do documento: {props.title!r}" if props.title else "Título nas propriedades do documento: nenhum")
        default_lang = document.styles.element.xpath(".//w:docDefaults//w:lang/@w:val")
        lang = props.language or (default_lang[0] if default_lang else "")
        lines.append(f"Idioma declarado: {lang}" if lang else "Idioma declarado: nenhum")

        headings: list[str] = []
        normal_looks_like_heading = 0
        empty_run = 0
        empty_paragraph_runs = 0
        for paragraph in document.paragraphs:
            style = paragraph.style.name if paragraph.style is not None else ""
            text = paragraph.text.strip()
            if style.startswith("Heading") or style == "Title":
                headings.append(f"{style}: {text[:60]}")
            elif text and len(text) <= 80 and paragraph.runs and all(
                (run.bold or (run.font.size is not None and run.font.size.pt >= 16)) for run in paragraph.runs if run.text.strip()
            ):
                normal_looks_like_heading += 1
            if not text and not paragraph._p.xpath(".//w:drawing"):
                empty_run += 1
                if empty_run == 2:
                    empty_paragraph_runs += 1
            else:
                empty_run = 0
        lines.append(f"Parágrafos com estilo de título (Heading/Title): {len(headings)}" + (f" ({_listed(headings)})" if headings else ""))
        lines.append(
            f"Parágrafos curtos, todo em negrito ou fonte de 16 pontos ou mais, mas sem estilo de título: {normal_looks_like_heading}"
        )
        lines.append(f"Sequências de 2 ou mais parágrafos vazios seguidos (espaçamento por enter): {empty_paragraph_runs}")

        drawings = body.xpath(".//wp:docPr")
        described = [d for d in drawings if (d.get("descr") or "").strip()]
        lines.append(
            f"Imagens e desenhos: {len(drawings)}; com texto alternativo: {len(described)}; sem texto alternativo: {len(drawings) - len(described)}"
        )
        for index, shape in enumerate(drawings, 1):
            lines.append(f"  imagem {index}: texto alternativo = {(shape.get('descr') or '').strip()!r}")

        for number, table in enumerate(document.tables, 1):
            first = table.rows[0]._tr if table.rows else None
            header_flag = bool(first is not None and first.xpath("./w:trPr/w:tblHeader"))
            merged = len(table._tbl.xpath(".//w:gridSpan")) + len(table._tbl.xpath(".//w:vMerge"))
            lines.append(
                f"Tabela {number}: {len(table.rows)} linhas x {len(table.columns)} colunas; primeira linha marcada como cabeçalho: "
                f"{'sim' if header_flag else 'não'}; células mescladas: {merged}"
            )

        links = [("".join(t.text or "" for t in h.xpath(".//w:t")).strip()) for h in body.xpath(".//w:hyperlink")]
        lines.append(f"Hiperlinks: {len(links)}" + (f" (textos: {_listed([repr(t) for t in links])})" if links else ""))
        lines.append(f"Seções: {len(document.sections)}; cabeçalho de página com conteúdo: {any(s.header.paragraphs and any(p.text.strip() for p in s.header.paragraphs) for s in document.sections)}")
        _ = qn  # mantém a importação explícita do namespace usado pelas expressões acima
        lines.append("Limites: ordem de leitura real, contraste e o que um leitor de tela anuncia não são verificados por esta leitura.")
        return _block(lines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[document_facts] DOCX: %s", exc)
        return _block([f"Não foi possível ler a estrutura do DOCX ({type(exc).__name__}); nada se pode afirmar sobre título, idioma, imagens ou tabelas."])


# ---------------------------------------------------------------------------------------------------- PPTX
def pptx_facts(data: bytes) -> str:
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        prs = Presentation(io.BytesIO(data))
        props = prs.core_properties
        lines = [
            f"Título nas propriedades: {props.title!r}" if props.title else "Título nas propriedades: nenhum",
            f"Idioma declarado nas propriedades: {props.language}" if props.language else "Idioma declarado nas propriedades: nenhum",
            f"Slides: {len(prs.slides)}",
        ]
        for number, slide in enumerate(prs.slides, 1):
            title_shape = slide.shapes.title
            title = title_shape.text.strip() if title_shape is not None and title_shape.has_text_frame else ""
            pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
            described = [p for p in pictures if (p._element.xpath("./p:nvPicPr/p:cNvPr/@descr") or [""])[0].strip()]
            tables = [s for s in slide.shapes if getattr(s, "has_table", False) and s.has_table]
            order = [f"{s.name}" for s in slide.shapes]
            lines.append(
                f"Slide {number}: layout {slide.slide_layout.name!r}; título do slide: {title!r}" if title else
                f"Slide {number}: layout {slide.slide_layout.name!r}; sem título de slide"
            )
            for picture_number, picture in enumerate(pictures, 1):
                alt_text = (picture._element.xpath("./p:nvPicPr/p:cNvPr/@descr") or [""])[0].strip()
                lines.append(f"  imagem {picture_number} do slide {number}: texto alternativo = {alt_text!r}")
            lines.append(
                f"  imagens: {len(pictures)}; com texto alternativo preenchido: {len(described)}; tabelas: {len(tables)}"
                + (f" (primeira linha marcada como cabeçalho: {', '.join('sim' if t.table.first_row else 'não' for t in tables)})" if tables else "")
                + f"; ordem dos objetos no slide (a ordem de leitura): {_listed(order)}"
            )
            notes = slide.has_notes_slide and bool(slide.notes_slide.notes_text_frame.text.strip())
            lines.append(f"  notas do apresentador: {'sim' if notes else 'não'}")
        lines.append("Limites: contraste, tamanho de fonte efetivo e animações não são verificados por esta leitura.")
        return _block(lines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[document_facts] PPTX: %s", exc)
        return _block([f"Não foi possível ler a estrutura do PPTX ({type(exc).__name__}); nada se pode afirmar sobre títulos de slide, imagens ou ordem de leitura."])


# ---------------------------------------------------------------------------------------------------- PDF
def pdf_facts(data: bytes) -> str:
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        root: Any = reader.trailer["/Root"]
        lines: list[str] = []
        mark_info = root.get("/MarkInfo")
        marked = bool(mark_info.get_object().get("/Marked")) if mark_info is not None else False
        struct_root = root.get("/StructTreeRoot")
        lines.append(f"Marcado (tagged PDF, /MarkInfo /Marked): {'sim' if marked else 'não'}")
        lines.append(f"Árvore de estrutura (/StructTreeRoot): {'presente' if struct_root is not None else 'ausente'}")
        lang = root.get("/Lang")
        lines.append(f"Idioma do documento (/Lang): {str(lang)!r}" if lang else "Idioma do documento (/Lang): nenhum")
        prefs = root.get("/ViewerPreferences")
        display_title = bool(prefs.get_object().get("/DisplayDocTitle")) if prefs is not None else False
        title = (reader.metadata.title if reader.metadata else None) or ""
        lines.append(f"Título nos metadados: {title!r}" if title else "Título nos metadados: nenhum")
        lines.append(f"Exibir o título na barra da janela (/DisplayDocTitle): {'sim' if display_title else 'não'}")
        lines.append(f"Páginas: {len(reader.pages)}; protegido por senha: {'sim' if reader.is_encrypted else 'não'}")

        no_text = [str(i + 1) for i, page in enumerate(reader.pages) if not (page.extract_text() or "").strip()]
        lines.append(
            f"Páginas sem texto extraível (podem ser imagem digitalizada): {len(no_text)}" + (f" (páginas {_listed(no_text)})" if no_text else "")
        )

        if struct_root is not None:
            from pypdf.generic import ArrayObject, DictionaryObject

            def resolve(value: Any) -> Any:
                return value.get_object() if hasattr(value, "get_object") else value

            figures = with_alt = 0
            seen: set[int] = set()
            truncated = False
            stack = [resolve(struct_root)]
            while stack:
                node = stack.pop()
                # Só dicionários de PDF de verdade, e cada um uma vez: um PDF malformado com referência circular
                # não pode travar a leitura.
                if not isinstance(node, DictionaryObject) or id(node) in seen:
                    continue
                seen.add(id(node))
                if len(seen) > _MAX_STRUCT_NODES:
                    truncated = True
                    break
                if node.get("/S") == "/Figure":
                    figures += 1
                    if str(node.get("/Alt") or "").strip():
                        with_alt += 1
                kids = resolve(node.get("/K"))
                if isinstance(kids, ArrayObject):
                    stack.extend(resolve(kid) for kid in kids)
                elif kids is not None:
                    stack.append(kids)
            lines.append(
                f"Figuras na estrutura: {figures}; com texto alternativo (/Alt): {with_alt}; sem: {figures - with_alt}"
                + ("; a árvore é grande demais e só parte dela foi percorrida, então estas contagens são parciais" if truncated else "")
            )
        else:
            lines.append("Figuras na estrutura: não há árvore de estrutura, então não há como saber quais são figuras nem se têm texto alternativo")
        lines.append("Limites: ordem de leitura real, contraste e a qualidade do texto alternativo não são verificados por esta leitura.")
        return _block(lines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[document_facts] PDF: %s", exc)
        return _block([f"Não foi possível ler a estrutura do PDF ({type(exc).__name__}); nada se pode afirmar sobre marcação, idioma, título ou figuras."])


# ---------------------------------------------------------------------------------------------------- EPUB
def epub_facts(data: bytes) -> str:
    try:
        import posixpath
        import xml.etree.ElementTree as ET

        lines: list[str] = []
        with zipfile.ZipFile(io.BytesIO(data)) as epub:
            names = epub.namelist()
            opf_name = next((n for n in names if n.endswith(".opf")), None)
            if opf_name is None:
                return _block(["O arquivo não tem o manifesto (.opf) de um EPUB; nada se pode afirmar sobre metadados ou navegação."])
            root = ET.fromstring(epub.read(opf_name))

            def local(tag: str) -> str:
                return tag.rsplit("}", 1)[-1]

            metadata = next((c for c in root if local(c.tag) == "metadata"), None)
            values: dict[str, list[str]] = {}
            if metadata is not None:
                for element in metadata:
                    key = local(element.tag)
                    value = (element.text or "").strip() or element.get("content") or ""
                    meta_property = element.get("property")
                    if key == "meta" and meta_property:
                        key = meta_property
                    values.setdefault(key, []).append(value)
            lines.append(f"Título (dc:title): {values.get('title', ['nenhum'])[0]!r}")
            lines.append(f"Idioma (dc:language): {values.get('language', ['nenhum'])[0]!r}")
            for key in ("schema:accessMode", "schema:accessibilityFeature", "schema:accessibilityHazard", "schema:accessibilitySummary", "dcterms:conformsTo"):
                lines.append(f"Metadado {key}: {_listed(values[key]) if key in values else 'ausente'}")

            manifest = next((c for c in root if local(c.tag) == "manifest"), None)
            items = [] if manifest is None else [dict(i.attrib) for i in manifest if local(i.tag) == "item"]
            has_nav = any("nav" in (i.get("properties") or "").split() for i in items)
            lines.append(f"Documento de navegação (nav): {'presente' if has_nav else 'ausente'}")

            opf_dir = posixpath.dirname(opf_name)
            by_id = {i.get("id"): i.get("href") for i in items}
            spine = next((c for c in root if local(c.tag) == "spine"), None)
            order = [by_id.get(r.get("idref")) for r in (spine or []) if local(r.tag) == "itemref"]
            for href in [o for o in order if o]:
                path = posixpath.normpath(posixpath.join(opf_dir, href))
                if path not in names:
                    continue
                html_text = epub.read(path).decode("utf-8", errors="ignore")
                html_lang = re.search(r"<html[^>]*\s(?:xml:)?lang=\"([^\"]*)\"", html_text)
                headings = re.findall(r"<h([1-6])\b", html_text)
                images = re.findall(r"<img\b[^>]*>", html_text)
                no_alt = [i for i in images if not re.search(r"\balt\s*=", i)]
                empty_alt = [i for i in images if re.search(r"\balt\s*=\s*\"\"", i)]
                tables = len(re.findall(r"<table\b", html_text))
                tables_th = len(re.findall(r"<th\b", html_text))
                lines.append(
                    f"{href}: idioma da página {html_lang.group(1)!r}" if html_lang else f"{href}: sem idioma na página"
                )
                lines.append(
                    f"  títulos: {', '.join('h' + h for h in headings) or 'nenhum'}; imagens: {len(images)} "
                    f"(sem atributo alt: {len(no_alt)}; alt vazio: {len(empty_alt)}); tabelas: {tables} (células de cabeçalho th: {tables_th})"
                )
        lines.append("Limites: ordem de leitura real, contraste e a qualidade do texto alternativo não são verificados por esta leitura.")
        return _block(lines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[document_facts] EPUB: %s", exc)
        return _block([f"Não foi possível ler a estrutura do EPUB ({type(exc).__name__}); nada se pode afirmar sobre metadados, navegação ou imagens."])
