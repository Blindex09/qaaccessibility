"""Sandbox de codigo (portado do Agentic): contêiner descartavel, sem rede, sem host, sem relogio fixo (regra 8)."""

import asyncio
import inspect
import os

import pytest

from backend.src.services import code_sandbox as sandbox


def _flags(args: list[str]) -> str:
    return " ".join(args)


class TestIsolamentoDoContainer:
    def test_argumentos_do_docker_tem_todos_os_limites_de_seguranca(self):
        args = sandbox.docker_run_args(["docker"], "nome", "sha256:abc", ["python", "-c", "print(1)"])
        texto = _flags(args)
        for esperado in (
            "--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges", "--pids-limit 64",
            "--memory 256m", "--user 65534:65534", "--pull never", "--rm",
        ):
            assert esperado in texto
        assert args[-3:] == ["python", "-c", "print(1)"]

    def test_nao_monta_pasta_do_host_nem_repassa_ambiente(self):
        texto = _flags(sandbox.docker_run_args(["docker"], "n", "sha256:a", ["x"]))
        assert "-v " not in texto and "--volume" not in texto and "--mount" not in texto
        assert "--env HOME=/tmp" in texto and "API_KEY" not in texto and "--env-file" not in texto

    def test_nao_existe_parametro_de_prazo(self):
        assert "timeout" not in "".join(inspect.signature(sandbox.run_code_in_sandbox).parameters)


class TestCapturaDaPasta:
    def test_segredos_caches_e_links_ficam_de_fora(self, tmp_path):
        (tmp_path / "app.py").write_text("print(1)", encoding="utf-8")
        (tmp_path / ".env").write_text("OPENAI_API_KEY=x", encoding="utf-8")
        (tmp_path / "chave.pem").write_text("x", encoding="utf-8")
        (tmp_path / ".npmrc").write_text("//registry:_authToken=x", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "m.js").write_text("x", encoding="utf-8")
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "x.md").write_text("x", encoding="utf-8")
        nomes = [nome for nome, _c, _m in sandbox.snapshot_files(tmp_path)]
        assert nomes == ["app.py"]

    def test_arquivo_no_lugar_de_pasta_e_recusado(self, tmp_path):
        arquivo = tmp_path / "a.txt"
        arquivo.write_text("x", encoding="utf-8")
        with pytest.raises((ValueError, OSError)):
            sandbox.snapshot_files(arquivo)

    def test_excesso_de_arquivos_e_recusado(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sandbox, "MAX_SNAPSHOT_FILES", 2)
        for i in range(3):
            (tmp_path / f"{i}.py").write_text("x", encoding="utf-8")
        with pytest.raises(ValueError, match="limite"):
            sandbox.snapshot_files(tmp_path)


class TestEntradaRecusada:
    async def test_runtime_desconhecido(self, tmp_path):
        r = await sandbox.run_code_in_sandbox(tmp_path, ["x"], runtime="ruby")
        assert r["status"] == "rejected" and not r["passed"]

    @pytest.mark.parametrize("comando", [[], "texto", ["ok", ""], ["a\x00b"], ["x"] * 129])
    async def test_comando_invalido(self, tmp_path, comando):
        r = await sandbox.run_code_in_sandbox(tmp_path, comando)
        assert r["status"] == "rejected"

    async def test_sem_docker_diz_que_nao_rodou_e_nunca_cai_no_host(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sandbox, "docker_cli", lambda: None)
        r = await sandbox.run_code_in_sandbox(tmp_path, ["python", "-c", "print(1)"])
        assert r["status"] == "unavailable" and r["passed"] is False

    async def test_contexto_docker_remoto_e_recusado(self, tmp_path, monkeypatch):
        (tmp_path / "a.py").write_text("x", encoding="utf-8")
        monkeypatch.setattr(sandbox, "docker_cli", lambda: "docker")
        monkeypatch.delenv("DOCKER_HOST", raising=False)

        async def comando(argv, payload=b"", **_kw):
            return 0, "tcp://10.0.0.5:2375"

        monkeypatch.setattr(sandbox, "_command", comando)
        r = await sandbox.run_code_in_sandbox(tmp_path, ["python", "a.py"])
        assert r["status"] == "unavailable" and "remoto" in r["output"]


class TestExecucao:
    @pytest.fixture
    def docker_falso(self, tmp_path, monkeypatch):
        (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
        monkeypatch.setattr(sandbox, "docker_cli", lambda: "docker")
        monkeypatch.setenv("DOCKER_HOST", "npipe:////./pipe/docker_engine")
        return []

    async def test_passa_remove_o_container_e_devolve_impressao_digital(self, tmp_path, docker_falso, monkeypatch):
        async def comando(argv, payload=b"", **_kw):
            docker_falso.append(argv)
            if "image" in argv:
                return 0, "sha256:imagem"
            if "run" in argv:
                assert payload  # a pasta vai pela entrada padrao, em tar
                return 0, "1\n"
            return 0, ""

        monkeypatch.setattr(sandbox, "_command", comando)
        r = await sandbox.run_code_in_sandbox(tmp_path, ["python", "a.py"])
        assert r["status"] == "passed" and r["passed"] and r["exit_code"] == 0
        assert r["workspace_fingerprint"] and r["image_id"] == "sha256:imagem"
        assert any("rm" in a and "--force" in a for a in docker_falso)

    async def test_falha_do_codigo_e_falha_nao_aprovacao(self, tmp_path, docker_falso, monkeypatch):
        async def comando(argv, payload=b"", **_kw):
            if "image" in argv:
                return 0, "sha256:imagem"
            return (3, "erro") if "run" in argv else (0, "")

        monkeypatch.setattr(sandbox, "_command", comando)
        r = await sandbox.run_code_in_sandbox(tmp_path, ["python", "a.py"])
        assert r["status"] == "failed" and r["passed"] is False and r["exit_code"] == 3

    async def test_se_parar_de_avancar_o_container_e_removido(self, tmp_path, docker_falso, monkeypatch):
        """Regressao do laco: o que roda e travado nunca fica para tras; a limpeza acontece mesmo assim."""
        async def comando(argv, payload=b"", **_kw):
            docker_falso.append(argv)
            if "image" in argv:
                return 0, "sha256:imagem"
            if "run" in argv:
                raise TimeoutError("parou de avancar")
            return 0, ""

        monkeypatch.setattr(sandbox, "_command", comando)
        r = await sandbox.run_code_in_sandbox(tmp_path, ["python", "a.py"])
        assert r["status"] == "stalled" and r["passed"] is False
        assert any("rm" in a and "--force" in a for a in docker_falso)

    async def test_a_limpeza_roda_fora_do_orcamento_esgotado(self, tmp_path, docker_falso, monkeypatch):
        """Regressao achada ao vivo: a limpeza dentro do orcamento ja esgotado falhava e o contêiner ficava rodando."""
        guardas = {}

        async def comando(argv, payload=b"", **kw):
            guardas["rm" if "rm" in argv else "outro"] = kw.get("guarded", True)
            if "image" in argv:
                return 0, "sha256:imagem"
            if "run" in argv:
                raise TimeoutError("parou de avancar")
            return 0, ""

        monkeypatch.setattr(sandbox, "_command", comando)
        await sandbox.run_code_in_sandbox(tmp_path, ["python", "a.py"])
        assert guardas["rm"] is False

    async def test_cancelamento_propaga_depois_da_limpeza(self, tmp_path, docker_falso, monkeypatch):
        async def comando(argv, payload=b"", **_kw):
            docker_falso.append(argv)
            if "image" in argv:
                return 0, "sha256:imagem"
            if "run" in argv:
                raise asyncio.CancelledError
            return 0, ""

        monkeypatch.setattr(sandbox, "_command", comando)
        with pytest.raises(asyncio.CancelledError):
            await sandbox.run_code_in_sandbox(tmp_path, ["python", "a.py"])
        assert any("rm" in a and "--force" in a for a in docker_falso)

    async def test_nao_confirmar_a_remocao_reprova_o_resultado(self, tmp_path, docker_falso, monkeypatch):
        async def comando(argv, payload=b"", **_kw):
            if "image" in argv:
                return 0, "sha256:imagem"
            if "run" in argv:
                return 0, "ok"
            return 1, "erro ao remover"

        monkeypatch.setattr(sandbox, "_command", comando)
        r = await sandbox.run_code_in_sandbox(tmp_path, ["python", "a.py"])
        assert r["passed"] is False and r["status"] == "failed"


@pytest.mark.skipif(not os.environ.get("QA_SANDBOX_LIVE"), reason="prova ao vivo exige Docker e a imagem local; defina QA_SANDBOX_LIVE=1")
async def test_ao_vivo_o_codigo_roda_sem_rede(tmp_path):
    codigo = "import socket\ntry:\n    socket.create_connection(('1.1.1.1', 53), 2)\n    print('REDE')\nexcept OSError:\n    print('SEM_REDE')\n"
    (tmp_path / "t.py").write_text(codigo, encoding="utf-8")
    r = await sandbox.run_code_in_sandbox(tmp_path, ["python", "t.py"])
    assert r["status"] == "passed" and "SEM_REDE" in r["output"]
