import json
import tempfile
from pathlib import Path

from backend.src.services.chat_tools import _precheck_local_path, fix_local_project_files, read_local_project_files
from backend.src.services.request_context import request_context


def _make_temp_dir(name: str) -> str:
    base = Path(tempfile.gettempdir()) / name
    base.mkdir(parents=True, exist_ok=True)
    (base / "index.html").write_text("<html><body><img></body></html>", encoding="utf-8")
    return str(base)


# Decisão do dono do projeto (08/10/2026): para ler e corrigir arquivos locais, a autorização é o caminho que a
# pessoa escreveu na conversa mais o cartão de aprovação. O nome da pasta não decide (regra 2: sem palavra-chave).
# O guarda por nome continua só para executar comandos locais (remote_runners).
class TestReadLocalProjectFilesScope:
    def test_reads_any_directory_whatever_its_name(self):
        project_dir = _make_temp_dir("scopetest_generic_project")
        result = json.loads(read_local_project_files({"project_dir": project_dir}))
        assert "error" not in result
        assert result["project_dir"] == project_dir

    def test_missing_directory_is_reported_plainly(self):
        result = json.loads(read_local_project_files({"project_dir": str(Path(tempfile.gettempdir()) / "nao_existe_xyz")}))
        assert "Diretório não encontrado" in result["error"]


class TestFixLocalProjectFilesScope:
    def test_folder_name_no_longer_blocks_the_fix(self):
        project_dir = _make_temp_dir("scopetest_generic_fix_project")
        result = json.loads(fix_local_project_files({"project_dir": project_dir, "files": []}))
        assert "acessibilidade" not in str(result.get("error", "")).lower()


class TestPathMustBeWrittenByThePerson:
    def test_a_path_the_person_wrote_is_accepted(self):
        project_dir = _make_temp_dir("scopetest_written_path")
        with request_context(f"O projeto está em {project_dir}", []):
            assert _precheck_local_path({"project_dir": project_dir}) is None

    def test_an_invented_path_is_refused_before_any_approval(self):
        with request_context("Analise o projeto da loja", []):
            assert _precheck_local_path({"project_dir": "C:/Users/x/Temp"})
