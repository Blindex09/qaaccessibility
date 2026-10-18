"""Component-library knowledge shared by the chat and the analysis specialists.

The single source is `resources/component_library_knowledge.md`: a platform-neutral
method for auditing what a component library really renders, plus a catalog of
concrete libraries. This module only slices that file into prompt blocks; it
decides nothing about a page and never classifies one.
"""

import re
from pathlib import Path

_SOURCE = Path(__file__).resolve().parents[1] / "resources" / "component_library_knowledge.md"
_METHOD_HEADING = "## Método geral"
_CATALOG_HEADING = "## Catálogo"

_HEADER = (
    "COMPONENT LIBRARY CALIBRATION (reference knowledge, written in Portuguese; answer in the language "
    "the task asks for). Judge the rendered DOM and the props that produced it, never the component name or "
    "its documentation. Native elements are valid patterns. This calibrates findings, it does not suppress a "
    "real, evidenced defect."
)


def _sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = ""
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current, buffer = line, [line]
        elif current:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    return sections


def _load() -> tuple[str, str]:
    sections = _sections(_SOURCE.read_text(encoding="utf-8"))
    method = next(body for heading, body in sections.items() if heading.startswith(_METHOD_HEADING))
    catalog = next(body for heading, body in sections.items() if heading.startswith(_CATALOG_HEADING))
    return method, catalog


_METHOD, _CATALOG = _load()

_COMPONENT_NAME = re.compile(r"[A-Z][A-Za-z0-9]*")


def _catalog_entries(catalog: str) -> dict[str, str]:
    """Map each component identifier named in a catalog heading to that heading's section.

    A heading such as "Tabs, TabsList e TabsPanel" names several components that share one
    entry. This is a lookup by identifier, not a judgement about any page.
    """
    entries: dict[str, str] = {}
    heading = ""
    buffer: list[str] = []

    def flush() -> None:
        if not heading:
            return
        body = "\n".join(buffer).strip()
        for part in re.split(r",| e ", heading):
            name = part.strip()
            if _COMPONENT_NAME.fullmatch(name):
                entries.setdefault(name, body)

    for line in catalog.splitlines():
        if line.startswith("### "):
            flush()
            heading, buffer = line[4:].strip(), [line]
        elif heading:
            buffer.append(line)
    flush()
    return entries


_ENTRIES = _catalog_entries(_CATALOG)


def library_component_entry(name: str) -> str | None:
    """Catalog section describing the HTML a library component renders, or None if not catalogued."""
    return _ENTRIES.get(name)

# Every specialist and the chat: how to read any component library's output.
COMPONENT_LIBRARY_METHOD = f"{_HEADER}\n\n{_METHOD}"

# Only the specialists that judge composed components: method plus the library catalog.
COMPONENT_LIBRARY_FULL = f"{COMPONENT_LIBRARY_METHOD}\n\n{_CATALOG}"
