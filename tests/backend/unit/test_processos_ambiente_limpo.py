"""Credencial por execucao e ambiente limpo para processos filhos (regra 1: escopo de credencial e sandbox).

Antes, os runners herdavam o os.environ inteiro: toda chave de provedor ficava visivel para codigo de terceiros
(pacotes npm, specs, colecoes). Agora o filho recebe o ambiente minimo do sistema mais o que a execucao pediu.
"""

import ast
from pathlib import Path

import pytest

from backend.src.security.process_env import clean_env, credential_lease

_RAIZ = Path(__file__).resolve().parents[3] / "backend" / "src"
_ORIGEM = {
    "PATH": "/usr/bin", "SystemRoot": "C:/Windows", "TEMP": "/tmp", "LANG": "pt_BR.UTF-8",
    "OPENAI_API_KEY": "sk-segredo", "ANTHROPIC_API_KEY": "ak-segredo", "GEMINI_API_KEY": "g-segredo",
    "CYPRESS_RECORD_KEY": "rk-segredo", "DATABASE_URL": "postgres://u:p@h/db",
}


class TestAmbienteLimpo:
    def test_so_o_minimo_do_sistema_passa(self):
        env = clean_env(source=_ORIGEM)
        assert set(env) == {"PATH", "SystemRoot", "TEMP", "LANG"}

    def test_nenhuma_chave_de_provedor_passa(self):
        assert not any("KEY" in nome or "URL" in nome for nome in clean_env(source=_ORIGEM))

    def test_o_que_a_execucao_pede_entra(self):
        env = clean_env({"CYPRESS_PROJECT_ID": "abc"}, source=_ORIGEM)
        assert env["CYPRESS_PROJECT_ID"] == "abc" and "OPENAI_API_KEY" not in env

    def test_busca_do_sistema_ignora_maiusculas(self):
        assert clean_env(source={"path": "/x"}) == {"path": "/x"}


class TestEmprestimoDeCredencial:
    def test_empresta_so_o_pedido_pelo_nome(self):
        with credential_lease(["CYPRESS_RECORD_KEY", "NAO_EXISTE"], source=_ORIGEM) as lease:
            assert lease.names == ("CYPRESS_RECORD_KEY",)
            env = lease.env()
        assert env["CYPRESS_RECORD_KEY"] == "rk-segredo"
        assert "OPENAI_API_KEY" not in env

    def test_devolvida_ao_sair_e_nao_serve_mais(self):
        with credential_lease(["CYPRESS_RECORD_KEY"], source=_ORIGEM) as lease:
            pass
        with pytest.raises(PermissionError):
            lease.env()
        assert lease.names == ()

    def test_devolvida_tambem_quando_a_execucao_falha_ou_e_cancelada(self):
        holder = {}
        with pytest.raises(RuntimeError), credential_lease(["CYPRESS_RECORD_KEY"], source=_ORIGEM) as lease:
            holder["lease"] = lease
            raise RuntimeError("falhou")
        with pytest.raises(PermissionError):
            holder["lease"].env()

    def test_o_registro_guarda_nomes_nunca_valores(self, caplog):
        with caplog.at_level("INFO"), credential_lease(["CYPRESS_RECORD_KEY"], source=_ORIGEM):
            pass
        assert "CYPRESS_RECORD_KEY" in caplog.text
        assert "rk-segredo" not in caplog.text


class TestNenhumProcessoHerdaOAmbienteInteiro:
    """Defesa contra a volta: todo processo filho do backend declara o ambiente (env=) em vez de herdar o do pai."""

    _SPAWNS = ("subprocess.run", "subprocess.Popen", "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell")

    def test_todo_spawn_passa_env(self):
        sem_env = []
        for caminho in sorted(_RAIZ.rglob("*.py")):
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                spawn = isinstance(no, ast.Call) and ast.unparse(no.func) in self._SPAWNS
                if spawn and not any(kw.arg == "env" for kw in no.keywords):
                    sem_env.append(f"{caminho.relative_to(_RAIZ).as_posix()}:{no.lineno}")
        assert sem_env == []
