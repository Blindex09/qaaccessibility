"""Source map for Astro and MDX files: which components a page uses and what HTML they render.

Astro (.astro) and MDX (.mdx) sources are not HTML. The specialists audit rendered markup, so a
source file only helps if the model knows what each component turns into. This module extracts the
objective syntax facts (import statements and capitalised tags), then attaches, for every component
the project takes from a catalogued library, the catalog entry that describes the HTML it renders.

Nothing here judges accessibility or decides intent. Identifiers are looked up, never guessed, and the
source files are untrusted data: only identifier-shaped names and bounded module paths are ever echoed.
"""

import os
import re
from dataclasses import dataclass, field

from backend.src.shared.component_library_calibration import library_component_entry

ASTRO_EXTENSIONS = frozenset({".astro", ".mdx"})

# Libraries whose rendered HTML is catalogued in component_library_knowledge.md.
CATALOGUED_LIBRARIES = frozenset({"accessible-astro-components", "accessible-astro-launcher"})

_IMPORT = re.compile(r"""import\s+([^;'"]*?)\s+from\s+['"]([^'"\n]{1,200})['"]""", re.DOTALL)
_TAG = re.compile(r"<([A-Z][A-Za-z0-9]*)(?=[\s/>])")
_NAME = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_SAFE_MODULE = re.compile(r"[A-Za-z0-9@._~:/\-]{1,200}")
_LOCAL_PREFIXES = (".", "@components", "@layouts", "@assets", "@utils", "@/", "~/", "src/")


def _clean(text: str, limit: int = 160) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", text)[:limit]


@dataclass(frozen=True)
class Binding:
    """One imported identifier: the local name, the name exported by the module, and the module."""

    local: str
    imported: str
    module: str


@dataclass
class FileMap:
    path: str
    library: list[Binding] = field(default_factory=list)
    project: list[Binding] = field(default_factory=list)
    third_party: list[Binding] = field(default_factory=list)


def parse_imports(source: str) -> list[Binding]:
    """Extract import bindings (default, named, aliased) from an Astro frontmatter or an MDX file."""
    bindings: list[Binding] = []
    for clause, module in _IMPORT.findall(source):
        if not _SAFE_MODULE.fullmatch(module):
            continue
        named = re.search(r"\{([^}]*)\}", clause)
        if named:
            for item in named.group(1).split(","):
                words = item.replace("type ", "", 1).split()
                if not words or not _NAME.fullmatch(words[0]):
                    continue
                local = words[2] if len(words) == 3 and words[1] == "as" and _NAME.fullmatch(words[2]) else words[0]
                bindings.append(Binding(local=local, imported=words[0], module=module))
        default = clause.split("{")[0].strip().rstrip(",").strip()
        namespace = re.fullmatch(r"\*\s+as\s+([A-Za-z_$][A-Za-z0-9_$]*)", default)
        if namespace:
            bindings.append(Binding(local=namespace.group(1), imported="*", module=module))
        elif default and _NAME.fullmatch(default):
            bindings.append(Binding(local=default, imported="default", module=module))
    return bindings


def used_tags(source: str) -> list[str]:
    """Capitalised tag names in the order of first use."""
    return list(dict.fromkeys(_TAG.findall(source)))


def _is_project_module(module: str) -> bool:
    return module.startswith(_LOCAL_PREFIXES)


def build_file_map(path: str, source: str) -> FileMap:
    """Classify the components a file actually uses: catalogued library, project file, third party."""
    imports = {binding.local: binding for binding in parse_imports(source)}
    file_map = FileMap(path=_clean(path))
    for tag in used_tags(source):
        binding = imports.get(tag)
        if binding is None:
            continue
        if binding.module in CATALOGUED_LIBRARIES:
            file_map.library.append(binding)
        elif _is_project_module(binding.module):
            file_map.project.append(binding)
        else:
            file_map.third_party.append(binding)
    return file_map


def _locate_project_file(binding: Binding, provided_paths: list[str]) -> str | None:
    """The one provided file whose name matches the imported module, or None when absent or ambiguous."""
    wanted = os.path.basename(binding.module)
    if not wanted:
        return None
    matches = [path for path in provided_paths if os.path.basename(path.replace("\\", "/")) == wanted]
    return matches[0] if len(matches) == 1 else None


_FILE_MARKER = re.compile(r"^--- ([^\r\n]{1,300}?) ---[ \t]*$", re.MULTILINE)
_PASTED_NAME = "(pasted source)"


def split_file_blocks(text: str) -> list[tuple[str, str]]:
    """Split text sent as `--- path ---` blocks (the chat's format for a project) into (path, content).

    A text without markers is one file. When it is Astro/MDX source (it imports from a catalogued
    library) it is named as pasted source so it still gets a map; any other text is returned unnamed.
    """
    markers = list(_FILE_MARKER.finditer(text))
    if not markers:
        pasted = any(f"'{lib}'" in text or f'"{lib}"' in text for lib in CATALOGUED_LIBRARIES)
        return [(_PASTED_NAME + ".astro", text)] if pasted else []
    blocks: list[tuple[str, str]] = []
    for position, marker in enumerate(markers):
        end = markers[position + 1].start() if position + 1 < len(markers) else len(text)
        blocks.append((marker.group(1).strip(), text[marker.end() : end]))
    return blocks


def source_map_for_text(text: str) -> str:
    """Source map for text that may carry Astro/MDX files; empty when it does not."""
    return build_source_map(split_file_blocks(text))


def build_source_map(files: list[tuple[str, str]]) -> str:
    """Prompt block for a set of project files; empty when no Astro or MDX file is present."""
    sources = [(name, text) for name, text in files if os.path.splitext(name.lower())[1] in ASTRO_EXTENSIONS]
    if not sources:
        return ""

    provided = [name for name, _ in files]
    lines = [
        "=== ASTRO/MDX SOURCE MAP ===",
        "Syntax facts read from import statements and tags (not accessibility findings). Astro and MDX files "
        "are source, not rendered HTML: audit what each component renders, using the entries below, and mark "
        "anything that depends on a component whose HTML is unknown as pendente-manual instead of assuming.",
    ]
    used: dict[str, None] = {}
    for name, text in sources:
        file_map = build_file_map(name, text)
        lines.append(f"\nFile: {file_map.path}")
        if file_map.library:
            lines.append("  Library components: " + ", ".join(dict.fromkeys(_clean(b.imported, 60) for b in file_map.library)))
            for binding in file_map.library:
                used.setdefault(binding.imported, None)
        for binding in dict.fromkeys(file_map.project):
            located = _locate_project_file(binding, provided)
            where = f"{_clean(located)} (included in this analysis; its markup is the rendered HTML)" if located else (
                f"{_clean(binding.module, 80)} (file not provided; its rendered HTML is unknown)"
            )
            lines.append(f"  Project component: {_clean(binding.local, 60)} -> {where}")
        if file_map.third_party:
            lines.append(
                "  Third-party components (HTML not catalogued): "
                + ", ".join(f"{_clean(b.local, 60)} ({_clean(b.module, 80)})" for b in dict.fromkeys(file_map.third_party))
            )

    if used:
        lines.append("\nHTML rendered by the library components used above (from the catalog):")
        seen_sections: set[str] = set()
        for component in used:
            entry = library_component_entry(component)
            if entry is None:
                lines.append(f"\n{_clean(component, 60)}: no catalog entry; its rendered HTML is unknown, do not assume it.")
            elif entry not in seen_sections:
                seen_sections.add(entry)
                lines.append("\n" + entry)
    lines.append("=== END ASTRO/MDX SOURCE MAP ===\n")
    return "\n".join(lines)
