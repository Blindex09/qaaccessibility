"""Testes dos corpos de execução real (subprocess/WebDriver) do remote_runners.

Por que este arquivo existe: `test_remote_runners.py` cobre os contratos das
funções públicas fazendo patch nos helpers locais (`_try_run_local_cypress`,
`_run_newman`, ...). Isso deixava os CORPOS desses helpers -- exatamente onde
o processo externo é disparado -- sem exercício nenhum: `remote_runners.py`
estava em 57% de cobertura, a menor do backend, no módulo de maior raio de
dano (executa npm/npx/cypress/chromedriver na máquina do backend).

O que se fixa aqui é o comportamento de degradação: cada caminho de falha
(binário ausente, timeout, código de saída != 0, relatório ausente ou
ilegível) tem de devolver `None` e deixar o chamador decidir o fallback --
nunca levantar exceção para cima nem inventar um resultado verde.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.services import remote_runners


class _FakeProc:
    """Processo falso com a superfície que o remote_runners realmente usa."""

    def __init__(self, returncode: int = 0, on_communicate=None, raises=None, stdout: bytes = b""):
        self.returncode = returncode
        self._on_communicate = on_communicate
        self._raises = raises
        self._stdout = stdout
        self.killed = False

    async def communicate(self):
        if self._raises is not None:
            raise self._raises
        if self._on_communicate is not None:
            self._on_communicate()
        return (self._stdout, b"")

    def kill(self):
        self.killed = True


def _fake_exec(proc: _FakeProc, capture: list | None = None):
    async def _exec(*args, **kwargs):
        if capture is not None:
            capture.append((args, kwargs))
        return proc

    return _exec


# -- _run_newman --------------------------------------------------------------


def _grava_relatorio_como_o_spec_faz(projeto, args, violations=None):
    """O spec gerado grava o relatorio SEMPRE, inclusive vazio (ver
    `_CYPRESS_SPEC_TEMPLATE`). A simulacao precisa fazer o mesmo, senao exercita
    um cenario que nao existe mais: hoje a ausencia de relatorio significa que a
    execucao falhou, e o codigo cai para o motor via nuvem."""
    spec = Path(args[args.index("--spec") + 1])
    run_id = spec.name.removeprefix("a11y_audit_").removesuffix(".cy.js")
    (projeto / f"a11y_report_{run_id}.json").write_text(
        json.dumps({"violations": violations or [], "incomplete": [], "testEngine": {"name": "axe-core"}}),
        encoding="utf-8",
    )


async def test_newman_sem_npx_no_path_devolve_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert await remote_runners._run_newman({"info": {}}) is None


async def test_newman_le_o_relatorio_que_o_processo_escreveu(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npx")
    esperado = {"run": {"stats": {"assertions": {"total": 3, "failed": 0}}}}
    capture: list = []

    def _escreve_relatorio():
        # O caminho do relatório vem no próprio comando (--reporter-json-export).
        argv = capture[-1][0]
        destino = Path(argv[argv.index("--reporter-json-export") + 1])
        destino.write_text(json.dumps(esperado), encoding="utf-8")

    proc = _FakeProc(on_communicate=_escreve_relatorio)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(proc, capture))

    assert await remote_runners._run_newman({"info": {}}) == esperado


async def test_newman_sem_relatorio_gerado_devolve_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npx")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(_FakeProc()))
    assert await remote_runners._run_newman({"info": {}}) is None


async def test_newman_com_relatorio_ilegivel_devolve_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npx")
    capture: list = []

    def _escreve_lixo():
        argv = capture[-1][0]
        destino = Path(argv[argv.index("--reporter-json-export") + 1])
        destino.write_text("nao e json", encoding="utf-8")

    proc = _FakeProc(on_communicate=_escreve_lixo)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(proc, capture))
    assert await remote_runners._run_newman({"info": {}}) is None


async def test_newman_com_binario_sumido_no_meio_devolve_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npx")

    async def _exec(*_args, **_kwargs):
        raise FileNotFoundError("npx")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)
    assert await remote_runners._run_newman({"info": {}}) is None


async def test_newman_no_timeout_mata_o_processo_e_devolve_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npx")
    proc = _FakeProc(raises=TimeoutError())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(proc))

    assert await remote_runners._run_newman({"info": {}}, timeout_seconds=0.01) is None
    assert proc.killed, "processo pendurado tem de ser morto, nao deixado orfao"


# -- _install_local_cypress ---------------------------------------------------


@pytest.fixture
def projeto_cypress(tmp_path, monkeypatch):
    destino = tmp_path / "cypress_local_project"
    monkeypatch.setattr(remote_runners, "_default_local_cypress_dir", lambda: destino)
    return destino


async def test_instalar_cypress_sem_npm_no_path_devolve_none(projeto_cypress, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert await remote_runners._install_local_cypress() is None


async def test_instalar_cypress_cria_o_scaffold_que_o_npm_install_nao_cria(projeto_cypress, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npm")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(_FakeProc(returncode=0)))
    monkeypatch.setattr("backend.src.security.secret_store.save_secret", MagicMock())

    resultado = await remote_runners._install_local_cypress()

    assert resultado == str(projeto_cypress)
    # Sem cypress.config.js o `cypress run` recusa rodar -- e o achado que o
    # docstring da funcao registra, e o que diferencia "pacotes baixados" de
    # "instalacao que realmente executa um teste".
    assert (projeto_cypress / "cypress.config.js").exists()
    assert (projeto_cypress / "package.json").exists()


async def test_instalar_cypress_com_npm_falhando_devolve_none(projeto_cypress, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npm")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(_FakeProc(returncode=1)))
    assert await remote_runners._install_local_cypress() is None


async def test_instalar_cypress_no_timeout_mata_o_processo(projeto_cypress, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npm")
    proc = _FakeProc(raises=TimeoutError())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(proc))

    assert await remote_runners._install_local_cypress(timeout_seconds=0.01) is None
    assert proc.killed


# -- _try_run_local_selenium --------------------------------------------------


async def test_selenium_local_devolve_o_resultado_do_axe(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/chromedriver")
    esperado = {"violations": [{"id": "image-alt"}], "incomplete": []}
    monkeypatch.setattr(asyncio, "to_thread", AsyncMock(return_value=esperado))

    assert await remote_runners._try_run_local_selenium("https://exemplo.com") == esperado


async def test_selenium_local_com_driver_quebrado_devolve_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/chromedriver")
    monkeypatch.setattr(asyncio, "to_thread", AsyncMock(side_effect=RuntimeError("session not created")))

    assert await remote_runners._try_run_local_selenium("https://exemplo.com") is None


async def test_selenium_local_no_timeout_devolve_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/chromedriver")
    monkeypatch.setattr(asyncio, "to_thread", AsyncMock(side_effect=TimeoutError()))

    assert await remote_runners._try_run_local_selenium("https://exemplo.com") is None


async def test_selenium_sem_chromedriver_so_roda_se_a_instalacao_foi_autorizada(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    chamou = AsyncMock(return_value={"violations": [], "incomplete": []})
    monkeypatch.setattr(asyncio, "to_thread", chamou)

    # Sem autorizacao: nem tenta.
    assert await remote_runners._try_run_local_selenium("https://exemplo.com") is None
    chamou.assert_not_awaited()

    # Com autorizacao explicita: deixa o Selenium Manager resolver o driver.
    resultado = await remote_runners._try_run_local_selenium("https://exemplo.com", allow_driver_auto_install=True)
    assert resultado == {"violations": [], "incomplete": []}
    chamou.assert_awaited_once()


# -- _try_run_local_cypress ---------------------------------------------------


@pytest.fixture
def projeto_cypress_pronto(tmp_path, monkeypatch):
    # O nome PRECISA conter um marcador de acessibilidade: `local_project_guard`
    # só deixa rodar comando em diretório de terceiros cujo caminho indique um
    # projeto de acessibilidade (fronteira estrutural, ver o teste de recusa
    # logo abaixo).
    destino = tmp_path / "projeto-a11y"
    (destino / "node_modules").mkdir(parents=True)
    monkeypatch.setenv("CYPRESS_LOCAL_PROJECT_DIR", str(destino))
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npx")
    return destino


async def test_cypress_recusa_diretorio_de_terceiros_fora_do_escopo(tmp_path, monkeypatch):
    """Fronteira de blast radius: nenhum subprocess pode ser disparado antes da checagem."""
    fora_do_escopo = tmp_path / "projeto-qualquer"
    (fora_do_escopo / "node_modules").mkdir(parents=True)
    monkeypatch.setenv("CYPRESS_LOCAL_PROJECT_DIR", str(fora_do_escopo))
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npx")

    disparou = MagicMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", disparou)

    with pytest.raises(remote_runners.CypressProjectOutOfScopeError):
        await remote_runners._try_run_local_cypress("https://exemplo.com")
    disparou.assert_not_called()


async def test_cypress_local_nao_instalado_cai_para_a_nuvem(projeto_cypress_pronto, monkeypatch):
    # `npx --no-install cypress version` com returncode != 0 = nao instalado.
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(_FakeProc(returncode=1)))
    assert await remote_runners._try_run_local_cypress("https://exemplo.com") is None


async def test_cypress_local_sem_relatorio_e_falha_de_execucao(projeto_cypress_pronto, monkeypatch):
    """Comportamento INVERTIDO em 2026-08-31, depois de medir contra a pagina real.

    Este teste afirmava que ausencia de relatorio significava "zero violacoes".
    O raciocinio tinha fundamento (com skipFailures=true o cy.checkA11y so
    escrevia o arquivo quando havia achados), mas "sem arquivo" tambem acontece
    quando nenhum spec roda, quando o --record e recusado, ou quando a pagina
    nao carrega.

    Medido contra https://www.w3.org/WAI/demos/bad/before/home.html -- a pagina
    que o W3C publica DE PROPOSITO cheia de violacoes: o Cypress local devolveu
    0 violacoes e passed=True enquanto o mesmo axe-core pela nuvem achava 8.
    Certificar como limpa uma pagina quebrada e o pior modo de falha de uma
    ferramenta de acessibilidade.

    O spec agora grava o relatorio SEMPRE, inclusive vazio, entao a ausencia
    virou sinal inequivoco de falha. `None` faz o chamador cair no motor via
    nuvem -- degradacao para um resultado real, nao para um veredito inventado.
    """
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec(_FakeProc(returncode=0)))

    resultado = await remote_runners._try_run_local_cypress("https://exemplo.com")

    assert resultado is None


async def test_cypress_local_le_o_relatorio_e_limpa_os_artefatos(projeto_cypress_pronto, monkeypatch):
    esperado = {"violations": [{"id": "color-contrast"}], "incomplete": []}

    async def _exec(*args, **kwargs):
        if "version" in args:
            return _FakeProc(returncode=0)
        # A execucao real do cypress escreveria o relatorio dentro do projeto.
        spec = Path(args[args.index("--spec") + 1])
        # a11y_audit_<run_id>.cy.js -- `.stem` tira só o último sufixo (.js).
        run_id = spec.name.removeprefix("a11y_audit_").removesuffix(".cy.js")
        destino = projeto_cypress_pronto / f"a11y_report_{run_id}.json"
        destino.write_text(json.dumps(esperado), encoding="utf-8")
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)

    assert await remote_runners._try_run_local_cypress("https://exemplo.com") == {
        **esperado,
        "_cypress_dashboard_url": None,
    }
    # Spec e relatorio sao temporarios dentro do projeto persistente: se
    # ficarem para tras, a proxima execucao le o resultado da anterior.
    assert list((projeto_cypress_pronto / "cypress" / "e2e").glob("a11y_audit_*.cy.js")) == []
    assert list(projeto_cypress_pronto.glob("a11y_report_*.json")) == []


# -- Gravacao real no Cypress Cloud -------------------------------------------


async def test_cypress_local_grava_no_cloud_e_devolve_a_url_do_run(projeto_cypress_pronto, monkeypatch):
    monkeypatch.setenv("CYPRESS_PROJECT_ID", "abc123")
    monkeypatch.setenv("CYPRESS_RECORD_KEY", "chave-secreta")
    comandos: list = []
    ambientes: list = []

    async def _exec(*args, **kwargs):
        comandos.append(args)
        ambientes.append(kwargs.get("env") or {})
        if "version" in args:
            return _FakeProc(returncode=0)
        _grava_relatorio_como_o_spec_faz(projeto_cypress_pronto, args)
        saida = b"Recorded Run: https://cloud.cypress.io/projects/abc123/runs/42\n"
        return _FakeProc(returncode=0, stdout=saida)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)
    relatorio = await remote_runners._try_run_local_cypress("https://exemplo.com")

    run_cmd = comandos[-1]
    assert "--record" in run_cmd and "chave-secreta" in run_cmd
    # `--project` no CLI do Cypress e o CAMINHO do projeto, nao o projectId: o
    # id tem de ir por variavel de ambiente, senao o --record falha.
    assert "--project" not in run_cmd
    assert ambientes[-1]["CYPRESS_PROJECT_ID"] == "abc123"
    assert relatorio["_cypress_dashboard_url"] == "https://cloud.cypress.io/projects/abc123/runs/42"


async def test_cypress_local_sem_chaves_nao_passa_record(projeto_cypress_pronto, monkeypatch):
    monkeypatch.delenv("CYPRESS_PROJECT_ID", raising=False)
    monkeypatch.delenv("CYPRESS_RECORD_KEY", raising=False)
    comandos: list = []

    async def _exec(*args, **kwargs):
        comandos.append(args)
        if "--spec" in args:
            _grava_relatorio_como_o_spec_faz(projeto_cypress_pronto, args)
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)
    relatorio = await remote_runners._try_run_local_cypress("https://exemplo.com")

    assert "--record" not in comandos[-1]
    assert relatorio["_cypress_dashboard_url"] is None


async def test_record_pedido_mas_sem_url_de_run_nao_conta_como_gravado(projeto_cypress_pronto, monkeypatch):
    """Chave invalida ou sem rede: o Cypress roda, mas nao grava. O resultado
    NAO pode dizer que sincronizou."""
    monkeypatch.setenv("CYPRESS_PROJECT_ID", "abc123")
    monkeypatch.setenv("CYPRESS_RECORD_KEY", "chave-errada")

    async def _exec(*args, **kwargs):
        if "version" in args:
            return _FakeProc(returncode=0)
        # O Cypress rodou a suite (o spec gravou o relatorio) mas a gravacao
        # na nuvem foi recusada -- os dois fatos sao independentes.
        _grava_relatorio_como_o_spec_faz(projeto_cypress_pronto, args)
        return _FakeProc(returncode=1, stdout=b"Your Record Key is not valid\n")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)
    relatorio = await remote_runners._try_run_local_cypress("https://exemplo.com")

    assert relatorio["_cypress_dashboard_url"] is None


async def test_resumo_local_reporta_gravacao_e_url(monkeypatch):
    monkeypatch.setenv("CYPRESS_PROJECT_ID", "abc123")
    monkeypatch.setenv("CYPRESS_RECORD_KEY", "chave-secreta")
    relatorio = {
        "violations": [],
        "incomplete": [],
        "testEngine": {"name": "axe-core"},
        "_cypress_dashboard_url": "https://cloud.cypress.io/projects/abc123/runs/42",
    }
    with patch(
        "backend.src.services.remote_runners._try_run_local_cypress",
        new=AsyncMock(return_value=relatorio),
    ):
        resultado = await remote_runners.run_remote_accessibility_audit("https://exemplo.com", location="local")

    assert resultado["cypress_cloud_synced"] is True
    assert resultado["cypress_dashboard_url"] == "https://cloud.cypress.io/projects/abc123/runs/42"
    assert "cypress_cloud_error" not in resultado


async def test_resumo_local_explica_quando_a_gravacao_falhou(monkeypatch):
    monkeypatch.setenv("CYPRESS_PROJECT_ID", "abc123")
    monkeypatch.setenv("CYPRESS_RECORD_KEY", "chave-errada")
    relatorio = {"violations": [], "incomplete": [], "_cypress_dashboard_url": None}
    with patch(
        "backend.src.services.remote_runners._try_run_local_cypress",
        new=AsyncMock(return_value=relatorio),
    ):
        resultado = await remote_runners.run_remote_accessibility_audit("https://exemplo.com", location="local")

    assert resultado["cypress_cloud_synced"] is False
    assert resultado["cypress_cloud_recording_configured"] is True
    assert "cypress_cloud_error" in resultado
