import json
import tempfile
from pathlib import Path

from backend.src.services.chat_tools import fix_local_project_files, read_local_project_files


def _make_temp_dir(name: str) -> str:
    base = Path(tempfile.gettempdir()) / name
    base.mkdir(parents=True, exist_ok=True)
    (base / "index.html").write_text("<html><body><img></body></html>", encoding="utf-8")
    return str(base)


class TestReadLocalProjectFilesScope:
    def test_denies_directory_without_accessibility_name(self):
        project_dir = _make_temp_dir("scopetest_generic_project")
        result = json.loads(read_local_project_files({"project_dir": project_dir}))
        assert "error" in result
        assert "acessibilidade" in result["error"].lower()

    def test_allows_directory_with_accessibility_name(self):
        project_dir = _make_temp_dir("scopetest_projeto_acessibilidade")
        result = json.loads(read_local_project_files({"project_dir": project_dir}))
        assert "error" not in result
        assert result["project_dir"] == project_dir


class TestFixLocalProjectFilesScope:
    def test_denies_directory_without_accessibility_name(self):
        project_dir = _make_temp_dir("scopetest_generic_fix_project")
        result = json.loads(fix_local_project_files({"project_dir": project_dir, "files": []}))
        assert "error" in result
        assert "acessibilidade" in result["error"].lower()
