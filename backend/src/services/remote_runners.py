"""
remote_runners.py
Módulo de execução remota/local de testes de acessibilidade para Selenium, Postman e Cypress.

Achado real corrigido (auditoria 2026-08-10): os três runners não rodavam
Selenium/Postman/Cypress nenhum -- `run_remote_selenium` e
`run_remote_cypress_simulation` só reexecutavam o orquestrador de IA próprio
do projeto e devolviam o resultado relabeled como se fosse um runner externo;
`run_remote_postman_contract` só reimplementava 3 checks fixos em Python.
Agora todos rodam de verdade:

Cypress e Selenium seguem o MESMO contrato de duas camadas, decidido pelo
USUÁRIO via `location` (nunca escolhido/fallback silencioso pelo modelo --
ver `chat_tools.py::_RUN_REMOTE_TEST_SCHEMA`):

1. run_remote_selenium: `location="local"` roda o Selenium WebDriver DE
   VERDADE (Chrome + `chromedriver` já instalados na máquina do backend,
   axe-core injetado via `driver.execute_script`); sem chromedriver
   resolvível, devolve erro claro (nunca cai pra nuvem sozinho quando local
   foi pedido). `location="cloud"` (ou default) roda o axe-core real via
   Playwright/Browserless -- mesmo motor de detecção que `axe-selenium-python`
   usa, sem precisar de driver local.
2. run_remote_postman_contract: roda uma collection Postman real via Newman
   (subprocess `npx newman run`) -- a collection real do usuário quando
   POSTMAN_API_KEY + POSTMAN_COLLECTION_ID estão configurados, ou uma gerada
   com pm.test() reais equivalentes ao contrato básico. Fallback honesto
   (`newman_ran: false`) se npx/newman não estiverem disponíveis.
3. run_remote_cypress_simulation: `location="local"` roda o binário Cypress
   DE VERDADE (Test Runner + cypress-axe) via subprocess, se
   `CYPRESS_LOCAL_PROJECT_DIR` apontar para um projeto já instalado (nunca
   dispara uma instalação -- o binário tem ~300MB); sem isso, devolve erro
   claro. `location="cloud"` (ou default) roda o axe-core real via
   nuvem/Browserless. As violações são reais nos dois casos; muda só QUAL
   runner executou de fato, e a resposta sempre diz isso (`runner`/`engine`).
"""

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _summarize_axe_results(axe_results: dict[str, Any]) -> dict[str, Any]:
    """Reduz o payload verboso do axe.run() (nodes, html, target, todos os
    metadados) para o formato enxuto que o chat/relatório consome."""
    violations = axe_results.get("violations", []) or []
    by_impact: dict[str, int] = {}
    for v in violations:
        impact = v.get("impact") or "unknown"
        by_impact[impact] = by_impact.get(impact, 0) + 1

    critical_issues = [
        {
            "id": v.get("id"),
            "impact": v.get("impact"),
            "description": v.get("description"),
            "help": v.get("help"),
            "help_url": v.get("helpUrl"),
            "wcag_tags": [t for t in (v.get("tags") or []) if t.startswith("wcag")],
            "affected_elements": len(v.get("nodes", [])),
            "example_selector": (v.get("nodes") or [{}])[0].get("target", []),
        }
        for v in violations
    ]

    return {
        "engine": "axe-core",
        "engine_version": axe_results.get("testEngine", {}).get("version"),
        "total_violations": len(violations),
        "total_incomplete": len(axe_results.get("incomplete", []) or []),
        "violations_by_impact": by_impact,
        "critical_issues": critical_issues[:10],
        "passed": len(violations) == 0,
        # Achado real (pedido do usuário, 2026-08-11): critical_issues acima é
        # só um resumo (top 10) pro modelo narrar -- pra alimentar
        # last_analysis_store (e desbloquear planilha/checklist/PDF/VPAT a
        # partir de um teste remoto real, não só de analyze_page), o handler
        # em chat_tools.py precisa do CONJUNTO COMPLETO de violações. Prefixo
        # "_" para o chat_tools remover antes de devolver a resposta ao
        # modelo -- verboso demais e redundante com critical_issues.
        "_raw_violations": violations,
    }


async def _try_run_local_selenium(
    url: str, timeout_seconds: float = 60.0, allow_driver_auto_install: bool = False,
) -> dict[str, Any] | None:
    """
    Roda o Selenium WebDriver DE VERDADE (Chrome local + axe-core injetado).

    Por padrão (`allow_driver_auto_install=False`) só roda se `chromedriver`
    já estiver no PATH -- nunca baixa nada sozinho num tool call comum.
    Quando o usuário pediu explicitamente pra instalar (`location=
    "install_local"` em run_remote_selenium), `allow_driver_auto_install=True`
    deixa o "Selenium Manager" (nativo do Selenium 4.6+) resolver e baixar o
    chromedriver certo por conta própria -- essa é a instalação de verdade.
    Devolve None se indisponível/falhar -- o chamador NÃO cai pra nuvem
    sozinho quando local foi pedido explicitamente (ver run_remote_selenium).
    """
    import asyncio
    import shutil

    chromedriver_path = shutil.which("chromedriver")
    if not chromedriver_path and not allow_driver_auto_install:
        return None

    def _run_sync() -> dict[str, Any]:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        from backend.src.services.browser import get_axe_core_js

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        if chromedriver_path:
            driver = webdriver.Chrome(service=Service(executable_path=chromedriver_path), options=options)
        else:
            # Sem caminho explícito, o Selenium Manager resolve/baixa o driver
            # sozinho -- só chega aqui quando o usuário autorizou a instalação.
            driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            driver.execute_script(get_axe_core_js())
            return driver.execute_async_script(
                "var callback = arguments[arguments.length - 1];"
                "window.axe.run(document, {resultTypes: ['violations', 'incomplete']})"
                ".then(function (results) { callback(results); });"
            )
        finally:
            driver.quit()

    effective_timeout = timeout_seconds if chromedriver_path else max(timeout_seconds, 180.0)
    try:
        logger.info(
            "[RemoteRunner] Rodando Selenium local de verdade (chromedriver=%s, auto_install=%s) para %s",
            chromedriver_path, allow_driver_auto_install, url,
        )
        return await asyncio.wait_for(asyncio.to_thread(_run_sync), timeout=effective_timeout)
    except TimeoutError:
        logger.warning("[RemoteRunner] Selenium local excedeu o timeout de %ss.", effective_timeout)
        return None
    except Exception as exc:
        logger.warning("[RemoteRunner] Falha ao executar Selenium local: %s", exc)
        return None


async def run_remote_selenium(url: str, location: str | None = None) -> dict[str, Any]:
    """
    Roda uma auditoria de acessibilidade real com o motor axe-core, em UM dos
    lugares -- decisão explícita do USUÁRIO via `location`, mesmo padrão de
    `run_remote_cypress_simulation` (ver docstring lá para o raciocínio completo):

    - `location="local"`: Selenium WebDriver DE VERDADE (Chrome + chromedriver
      já instalados na máquina do backend). Sem isso disponível, devolve
      `status="error"` com a opção de instalar -- NÃO cai pra nuvem sozinho.
    - `location="install_local"`: instala de verdade (deixa o Selenium Manager
      baixar o chromedriver certo) e roda -- só quando o usuário pediu
      explicitamente após ser perguntado (ver _RUN_REMOTE_TEST_SCHEMA).
    - `location="cloud"` (ou None, compatibilidade): axe-core via
      Playwright/Browserless, mesmo motor de detecção, sem driver local.
    """
    browserless_url = os.getenv("BROWSERLESS_WS_URL", "").strip()
    logger.info(
        "[RemoteRunner] Executando auditoria de acessibilidade (rótulo selenium, location=%s) para %s (Browserless Configured=%s)",
        location, url, bool(browserless_url),
    )
    try:
        if location in ("local", "install_local"):
            local_results = await _try_run_local_selenium(
                url, allow_driver_auto_install=(location == "install_local"),
            )
            if local_results is None:
                if location == "install_local":
                    return {
                        "status": "error",
                        "error": (
                            "Não foi possível instalar/rodar o Selenium local automaticamente "
                            "(o Selenium Manager não conseguiu baixar/usar o chromedriver nesta "
                            "máquina). Pergunte ao usuário se prefere rodar na nuvem em vez disso."
                        ),
                    }
                return {
                    "status": "error",
                    "error": (
                        "Selenium local não está disponível nesta máquina (chromedriver não "
                        "encontrado no PATH). Pergunte ao usuário se ele quer que você instale "
                        "agora (chame de novo com location='install_local') ou se prefere rodar "
                        "na nuvem (location='cloud')."
                    ),
                }
            summary = _summarize_axe_results(local_results)
            summary.update({"status": "ok", "runner": "selenium_local", "url": url})
            return summary

        from backend.src.services.browser import run_axe_core_audit
        axe_results = await run_axe_core_audit(url)
        summary = _summarize_axe_results(axe_results)
        summary.update({"status": "ok", "runner": "selenium_remote", "url": url})
        return summary
    except Exception as exc:
        logger.error("[RemoteRunner] Erro na auditoria de acessibilidade (selenium): %s", exc)
        return {"status": "error", "error": str(exc)}


def _build_generated_a11y_contract_collection(api_url: str) -> dict[str, Any]:
    """Monta uma Postman Collection v2.1 real (com pm.test() de verdade) para
    verificar o contrato básico de acessibilidade de uma API, usada quando o
    usuário não tem uma collection própria configurada (POSTMAN_COLLECTION_ID)."""
    return {
        "info": {
            "name": "QA Accessibility - Verificação de Contrato de API",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [{
            "name": "Verifica contrato de acessibilidade da API",
            "request": {"method": "GET", "url": api_url},
            "event": [{
                "listen": "test",
                "script": {
                    "type": "text/javascript",
                    "exec": [
                        "pm.test('Status code e 200 OK', function () {",
                        "  pm.response.to.have.status(200);",
                        "});",
                        "pm.test('Resposta e um JSON valido', function () {",
                        "  pm.response.to.be.json;",
                        "});",
                        "pm.test('Contrato contem atributos de acessibilidade', function () {",
                        "  const body = pm.response.json();",
                        "  const keys = ['alt', 'aria', 'label', 'title', 'description', 'score', 'issues'];",
                        "  pm.expect(keys.some((k) => Object.prototype.hasOwnProperty.call(body, k))).to.be.true;",
                        "});",
                    ],
                },
            }],
        }],
    }


async def _fetch_real_postman_collection(postman_key: str) -> dict[str, Any] | None:
    """Busca a collection real do usuário na Postman Cloud API, se
    POSTMAN_COLLECTION_ID estiver configurado. Devolve None se não configurado
    ou se a busca falhar (chamador cai no fallback gerado)."""
    collection_id = os.getenv("POSTMAN_COLLECTION_ID", "").strip()
    if not collection_id:
        return None
    try:
        res = requests.get(
            f"https://api.getpostman.com/collections/{collection_id}",
            headers={"x-api-key": postman_key},
            timeout=10,
        )
        if res.status_code == 200:
            return res.json().get("collection")
        logger.warning(
            "[RemoteRunner] Postman Cloud devolveu %s ao buscar a collection %s",
            res.status_code, collection_id,
        )
    except Exception as exc:
        logger.warning("[RemoteRunner] Falha ao buscar collection real do Postman: %s", exc)
    return None


async def _run_newman(collection: dict[str, Any], timeout_seconds: float = 90.0) -> dict[str, Any] | None:
    """Roda a collection via Newman de verdade (`npx newman run ... --reporters json`),
    processo real do Node, não Python reimplementando os mesmos checks.
    Devolve None (não uma exceção) se npx/newman não estiver disponível ou
    estourar o timeout -- o chamador decide o fallback, isso aqui só relata
    'não consegui rodar de verdade'."""
    import asyncio
    import shutil
    import tempfile
    from pathlib import Path

    # No Windows, `npx` e um shim `.CMD` -- create_subprocess_exec não passa
    # pelo shell nem por PATHEXT, então "npx" puro nunca resolve (FileNotFoundError
    # mesmo com o comando funcionando normalmente no terminal). shutil.which
    # resolve o caminho completo do executável de forma portável (Windows/Unix).
    npx_path = shutil.which("npx")
    if not npx_path:
        logger.warning("[RemoteRunner] npx não encontrado no PATH do servidor -- caindo no fallback leve.")
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        collection_path = Path(tmpdir) / "collection.json"
        report_path = Path(tmpdir) / "report.json"
        collection_path.write_text(json.dumps(collection), encoding="utf-8")

        cmd = [
            npx_path, "--yes", "newman", "run", str(collection_path),
            "--reporters", "json", "--reporter-json-export", str(report_path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
            except TimeoutError:
                proc.kill()
                logger.warning("[RemoteRunner] Newman excedeu o timeout de %ss", timeout_seconds)
                return None
        except FileNotFoundError:
            logger.warning("[RemoteRunner] npx/newman não encontrado no servidor -- caindo no fallback leve.")
            return None
        except Exception as exc:
            logger.warning("[RemoteRunner] Falha ao executar Newman: %s", exc)
            return None

        if not report_path.exists():
            logger.warning("[RemoteRunner] Newman não gerou relatório (run pode ter falhado antes de executar).")
            return None
        try:
            return json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[RemoteRunner] Relatório do Newman veio ilegível: %s", exc)
            return None


def _summarize_newman_report(report: dict[str, Any]) -> dict[str, Any]:
    """Reduz o relatório verboso do Newman pro formato enxuto que o chat consome."""
    run = report.get("run", {})
    stats = run.get("stats", {})
    assertions_total = stats.get("assertions", {}).get("total", 0)
    assertions_failed = stats.get("assertions", {}).get("failed", 0)
    assertions_passed = max(0, assertions_total - assertions_failed)
    score = int((assertions_passed / assertions_total) * 100) if assertions_total else 0

    tests: list[dict[str, Any]] = []
    http_status: int | None = None
    for execution in run.get("executions", []):
        response = execution.get("response") or {}
        if http_status is None:
            http_status = response.get("code")
        for assertion in execution.get("assertions", []):
            tests.append({
                "name": assertion.get("assertion", ""),
                "passed": not assertion.get("error"),
            })

    return {
        "engine": "newman",
        "newman_ran": True,
        "http_status": http_status,
        "score": score,
        "tests": tests,
        "passed": assertions_failed == 0 and assertions_total > 0,
    }


async def run_remote_postman_contract(api_url: str) -> dict[str, Any]:
    """
    Executa a validação de contrato de API de acessibilidade rodando uma
    collection Postman DE VERDADE via Newman (subprocess real do Node/npx).
    Usa a collection real do usuário quando POSTMAN_API_KEY + POSTMAN_COLLECTION_ID
    estão configurados; caso contrário, gera uma collection mínima com pm.test()
    reais equivalentes aos 3 checks de contrato básico.

    Achado real corrigido (auditoria 2026-08-10): antes disto, a "validação
    Postman" era só 3 checks fixos reimplementados em Python -- nunca rodava
    de fato um runner Postman/Newman. Se `npx`/`newman` não estiverem
    disponíveis no servidor (ou o run estourar o timeout), cai de volta nesse
    mesmo check leve, mas com `newman_ran: false` explícito -- nunca finge que
    rodou de verdade quando não rodou.
    """
    logger.info("[RemoteRunner] Executando validação de contrato Postman remoto para: %s", api_url)
    # A ferramenta é exposta ao modelo; aplique a mesma barreira SSRF usada
    # pelas rotas públicas antes de qualquer conexão de saída.
    from backend.src.routes.analyze import _validate_url_ssrf

    _validate_url_ssrf(api_url)
    postman_key = os.getenv("POSTMAN_API_KEY", "").strip()
    postman_cloud_synced = False
    collection: dict[str, Any] | None = None

    if postman_key:
        try:
            pm_res = requests.get(
                "https://api.getpostman.com/me",
                headers={"x-api-key": postman_key},
                timeout=5,
            )
            if pm_res.status_code == 200:
                user_data = pm_res.json().get("user", {})
                logger.info("[RemoteRunner] Conectado com sucesso ao Postman Cloud: %s", user_data.get("username"))
                postman_cloud_synced = True
                collection = await _fetch_real_postman_collection(postman_key)
        except Exception as exc:
            logger.warning("[RemoteRunner] Não foi possível autenticar na Postman Cloud API: %s", exc)

    if collection is None:
        collection = _build_generated_a11y_contract_collection(api_url)

    try:
        report = await _run_newman(collection)
        if report is not None:
            summary = _summarize_newman_report(report)
            summary.update({
                "status": "ok",
                "runner": "postman_remote",
                "postman_cloud_synced": postman_cloud_synced,
                "api_url": api_url,
            })
            return summary

        # Fallback honesto: newman indisponível/timeout -- mesmo check leve de
        # antes, mas rotulado como tal (newman_ran=False), nunca disfarçado.
        response = requests.get(api_url, timeout=10)
        status_code = response.status_code
        try:
            data = response.json()
        except Exception:
            data = {}

        is_json = isinstance(data, dict)
        has_a11y_fields = any(k in data for k in ("alt", "aria", "label", "title", "description", "score", "issues")) if is_json else False

        tests = [
            {"name": "Status code é 200 OK", "passed": status_code == 200},
            {"name": "Resposta é um JSON válido", "passed": is_json},
            {"name": "Contrato contém atributos de acessibilidade", "passed": has_a11y_fields},
        ]
        passed_count = sum(1 for t in tests if t["passed"])
        score = int((passed_count / len(tests)) * 100)

        return {
            "status": "ok",
            "runner": "postman_remote",
            "engine": "lightweight_contract_check",
            "newman_ran": False,
            "postman_cloud_synced": postman_cloud_synced,
            "api_url": api_url,
            "http_status": status_code,
            "score": score,
            "tests": tests,
            "passed": score == 100,
        }
    except Exception as exc:
        logger.error("[RemoteRunner] Erro na validação Postman remota: %s", exc)
        return {"status": "error", "error": str(exc)}



_CYPRESS_SPEC_TEMPLATE = """// spec gerado automaticamente pelo QA Accessibility para auditoria real via cypress-axe
// Achado real (2026-08-11): cy.injectAxe()/cy.checkA11y() são comandos
// customizados registrados pelo pacote cypress-axe -- normalmente via um
// supportFile separado, que exigiria fazer o "scaffold" completo do projeto
// (não é o que `npm install` sozinho faz). Importar aqui, direto no spec
// (supportFile: false no cypress.config.js), evita depender desse arquivo.
require('cypress-axe');

// Achado real (2026-08-11, contra um site de terceiros de verdade): scripts
// de terceiros da PÁGINA ALVO (analytics, widgets) podem lançar erros JS não
// capturados -- por padrão o Cypress falha o teste inteiro nesse caso, antes
// mesmo de rodar a auditoria de acessibilidade. Não estamos testando se o
// JavaScript da página funciona sem erros, só sua acessibilidade -- erros de
// aplicação de terceiros não devem interromper a checagem de a11y.
Cypress.on('uncaught:exception', () => false);

describe('Auditoria de acessibilidade (QA Accessibility)', () => {{
  it('roda axe-core na página alvo', () => {{
    cy.visit({url!r});
    cy.injectAxe();
    // Achado real (2026-08-11): com skipFailures=true (não travar o "teste"
    // por causa de violações), cy.checkA11y NÃO expõe as violações no
    // relatório JSON do reporter Mocha -- só loga no console do Test Runner.
    // O callback (3º parâmetro) recebe o array de violações no formato
    // axe-core completo, de verdade -- escrevemos isso num arquivo próprio
    // (cy.writeFile, relativo ao projectRoot) e o Python lê ele diretamente,
    // reaproveitando o mesmo _summarize_axe_results usado pelo caminho nuvem.
    cy.checkA11y({scope!r}, null, (violations) => {{
      cy.writeFile({report_filename!r}, {{ violations: violations, incomplete: [], testEngine: {{ name: 'axe-core' }} }});
    }}, true);
  }});
}});
"""


class CypressMultipleInstallationsFoundError(Exception):
    """A busca real achou mais de um projeto com Cypress instalado -- quem
    decide qual usar é o usuário (via `clarify`), nunca uma escolha silenciosa
    daqui. `candidates` traz os caminhos reais encontrados."""

    def __init__(self, candidates: list[str]):
        self.candidates = candidates
        super().__init__(f"{len(candidates)} instalações locais de Cypress encontradas: {candidates}")


class CypressProjectOutOfScopeError(Exception):
    """O diretório de projeto (achado por busca ou informado explicitamente)
    não tem nome de projeto de acessibilidade -- fora do escopo permitido
    para execução de comando local (ver local_project_guard.py)."""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        super().__init__(f"Diretório fora do escopo de acessibilidade: {project_dir}")


# Locais comuns de projeto onde um usuário sem nuvem provavelmente já tem um
# projeto Cypress instalado -- busca rasa (poucos níveis) e limitada em tempo,
# nunca uma varredura do disco inteiro (lento e invasivo demais pra um tool
# call de chat). Nomes de pasta escolhidos por convenção real de devs, não
# uma lista exaustiva -- é um "norte" (ver pedido do usuário), não garantia.
_LOCAL_PROJECT_SEARCH_SUBDIRS = (
    "", "projects", "Projects", "dev", "Dev", "code", "Code", "workspace",
    "Workspace", "repos", "Repos", "src", "git", "Documents", "Desktop",
)
_LOCAL_CYPRESS_SEARCH_MAX_DIRS = 400
_LOCAL_CYPRESS_SEARCH_TIMEOUT_SECONDS = 8.0


def _search_for_local_cypress_installations() -> list[str]:
    """
    Busca real (não simulada) por TODOS os projetos com Cypress já instalado
    na máquina do backend -- pra usuários que NÃO têm CYPRESS_LOCAL_PROJECT_DIR
    configurado nem querem depender da nuvem. Olha pastas de projeto comuns
    (home do usuário + subpastas de convenção real: projects/dev/code/repos/...)
    até 2 níveis de profundidade, procurando `node_modules/cypress/package.json`
    -- presença real do pacote, não só o nome da pasta.

    Acha TODAS as ocorrências (não para na primeira) porque um usuário real
    pode ter Cypress instalado em mais de um projeto -- se houver mais de uma,
    quem decide qual usar é o USUÁRIO (via `clarify`), nunca uma escolha
    silenciosa daqui (mesmo princípio de local vs. nuvem, ver
    _RUN_REMOTE_TEST_SCHEMA em chat_tools.py).

    Limitada em quantidade de diretórios visitados e em tempo (constantes
    acima) -- é uma busca best-effort com "norte" nos locais mais prováveis,
    não uma varredura exaustiva do disco inteiro (lento e invasivo demais
    para um tool call de chat).
    """
    import time
    from pathlib import Path

    home = Path.home()
    # Achado real (2026-08-11): em sistema de arquivos case-insensitive
    # (Windows, macOS por padrão), "projects" e "Projects" da lista de
    # convenção acima resolvem pro MESMO diretório físico -- sem deduplicar
    # os roots, o mesmo projeto seria visitado (e reportado) duas vezes,
    # fazendo a IA achar que existem 2 instalações quando é a mesma.
    seen_roots: set[str] = set()
    roots = []
    for sub in _LOCAL_PROJECT_SEARCH_SUBDIRS:
        candidate_root = home / sub
        if not candidate_root.is_dir():
            continue
        key = os.path.normcase(str(candidate_root.resolve()))
        if key in seen_roots:
            continue
        seen_roots.add(key)
        roots.append(candidate_root)

    found: list[str] = []
    seen_found: set[str] = set()
    start = time.monotonic()
    visited = 0
    for root in roots:
        try:
            candidates = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
        except OSError:
            continue
        for candidate in candidates:
            if time.monotonic() - start > _LOCAL_CYPRESS_SEARCH_TIMEOUT_SECONDS or visited > _LOCAL_CYPRESS_SEARCH_MAX_DIRS:
                logger.info("[RemoteRunner] Busca por Cypress local encerrada por limite de tempo/diretórios.")
                return found
            visited += 1
            marker = candidate / "node_modules" / "cypress" / "package.json"
            if marker.is_file():
                key = os.path.normcase(str(candidate.resolve()))
                if key in seen_found:
                    continue
                seen_found.add(key)
                logger.info("[RemoteRunner] Cypress local encontrado por busca real em %s", candidate)
                found.append(str(candidate))
    return found


async def _try_run_local_cypress(
    url: str, scope_selector: str = "", timeout_seconds: float = 120.0,
    project_dir_override: str | None = None,
) -> dict[str, Any] | None:
    """
    Roda o binário Cypress DE VERDADE (Test Runner + cypress-axe) na máquina
    onde o backend está rodando, SE já estiver instalado -- nunca dispara uma
    instalação (o binário do Cypress tem ~300MB e isso travaria o chat).

    Resolve o projeto em três etapas: (1) `project_dir_override`, se o usuário
    já escolheu entre múltiplas instalações numa pergunta anterior; (2)
    `CYPRESS_LOCAL_PROJECT_DIR`, se configurado; (3) senão, uma busca real por
    locais de projeto comuns (`_search_for_local_cypress_installations`) --
    pra usuários que já têm Cypress instalado em algum projeto seu e não têm
    nuvem configurada, sem precisar informar o caminho manualmente. Se a busca
    achar MAIS DE UMA instalação, levanta `CypressMultipleInstallationsFoundError`
    -- não é decisão nossa escolher qual usar. Se achar exatamente uma, o
    caminho é persistido (mesmo mecanismo de _install_local_cypress) para a
    próxima chamada não precisar buscar de novo. Sem nada em nenhuma das
    etapas, devolve None e o chamador cai no motor axe-core via nuvem.
    """
    import asyncio
    import shutil
    from pathlib import Path

    project_dir = (project_dir_override or "").strip() or os.getenv("CYPRESS_LOCAL_PROJECT_DIR", "").strip()
    if not project_dir or not Path(project_dir).is_dir():
        found = await asyncio.to_thread(_search_for_local_cypress_installations)
        if not found:
            return None
        if len(found) > 1:
            # Mais de uma instalação real encontrada -- não é decisão nossa
            # escolher qual usar (pode ser um projeto de trabalho vs. um
            # experimento antigo, versões diferentes, etc.). Devolve a lista
            # pro chamador perguntar ao usuário via `clarify` e repassar a
            # escolha em `project_dir_override` na próxima chamada.
            raise CypressMultipleInstallationsFoundError(found)
        project_dir = found[0]
        with contextlib.suppress(Exception):
            from backend.src.security.secret_store import save_secret
            save_secret("CYPRESS_LOCAL_PROJECT_DIR", project_dir)
        os.environ["CYPRESS_LOCAL_PROJECT_DIR"] = project_dir

    # Fronteira de escopo (pedido explicito do usuario, 2026-08-11): rodar
    # comando de terminal num projeto de TERCEIROS (achado por busca ou
    # informado via project_dir_override) so e permitido se o nome do
    # diretorio indicar que e um projeto de acessibilidade -- o proprio
    # diretorio de instalacao GERENCIADO por nos (_default_local_cypress_dir)
    # fica de fora dessa checagem, porque ali quem decide o conteudo somos
    # nos, nao um projeto do usuario.
    if Path(project_dir) != _default_local_cypress_dir():
        from backend.src.services.local_project_guard import is_accessibility_project_dir
        if not is_accessibility_project_dir(project_dir):
            logger.warning(
                "[RemoteRunner] Cypress local recusado: '%s' nao parece um projeto de acessibilidade.",
                project_dir,
            )
            raise CypressProjectOutOfScopeError(project_dir)

    # Auto-cura de instalações feitas ANTES da correção acima (sem
    # cypress.config.js, ou com uma versão desatualizada dele): só no NOSSO
    # diretório de instalação, nunca num projeto de terceiros achado pela
    # busca -- lá, o config é decisão do dono do projeto, não algo pra
    # escrever/sobrescrever por conta própria. Sempre reescreve (não só
    # quando falta) porque o arquivo é 100% gerado por nós, sem dado de
    # usuário -- mais simples e seguro que tentar detectar "está atualizado?".
    if Path(project_dir) == _default_local_cypress_dir():
        config_js = Path(project_dir) / "cypress.config.js"
        config_js.write_text(
            "const { defineConfig } = require('cypress');\n"
            "module.exports = defineConfig({ e2e: { supportFile: false, setupNodeEvents(_on, config) { return config; } } });\n",
            encoding="utf-8",
        )

    npx_path = shutil.which("npx")
    if not npx_path:
        return None

    # `--no-install` garante que, se o cypress não estiver de fato instalado
    # dentro do projeto, isso FALHA rápido em vez de baixar o binário.
    try:
        probe = await asyncio.create_subprocess_exec(
            npx_path, "--no-install", "cypress", "version",
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(probe.communicate(), timeout=15)
        if probe.returncode != 0:
            logger.info("[RemoteRunner] Cypress não está instalado em %s -- usando motor via nuvem.", project_dir)
            return None
    except Exception as exc:
        logger.info("[RemoteRunner] Não foi possível checar Cypress local (%s) -- usando motor via nuvem.", exc)
        return None

    import uuid

    # Achado real (2026-08-11): o Cypress rejeita specs fora do projectRoot
    # ("Can't run because no spec files were found") mesmo passando um
    # caminho absoluto via --spec fora do projeto -- specPattern é resolvido
    # relativo ao projectRoot. O spec precisa morar DENTRO de project_dir.
    # Nome único (uuid) evita colisão entre execuções concorrentes no mesmo
    # projeto persistente; limpo no finally, não com TemporaryDirectory
    # (que criaria fora do projeto de novo).
    run_id = uuid.uuid4().hex[:8]
    spec_dir = Path(project_dir) / "cypress" / "e2e"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / f"a11y_audit_{run_id}.cy.js"
    # cy.writeFile() é relativo ao projectRoot -- escreve aqui, não num tempdir
    # externo (mesma limitação do spec: precisa morar dentro do projeto).
    report_filename = f"a11y_report_{run_id}.json"
    report_path = Path(project_dir) / report_filename
    spec_path.write_text(
        _CYPRESS_SPEC_TEMPLATE.format(url=url, scope=scope_selector or "body", report_filename=report_filename),
        encoding="utf-8",
    )

    cmd = [npx_path, "--no-install", "cypress", "run", "--spec", str(spec_path)]
    logger.info("[RemoteRunner] Rodando Cypress local de verdade em %s para %s", project_dir, url)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=project_dir,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        proc.kill()
        logger.warning("[RemoteRunner] Cypress local excedeu o timeout de %ss.", timeout_seconds)
        return None
    except Exception as exc:
        logger.warning("[RemoteRunner] Falha ao executar Cypress local: %s", exc)
        return None
    finally:
        with contextlib.suppress(OSError):
            spec_path.unlink()

    # Achado real (2026-08-11): com skipFailures=true, cy.checkA11y só invoca
    # o callback (que escreve o arquivo) quando HÁ violações -- página limpa
    # de verdade nunca escreve o arquivo, e isso é um resultado válido (zero
    # violações), não uma falha de execução.
    if not report_path.exists():
        logger.info("[RemoteRunner] Cypress local rodou sem violações encontradas (nenhum arquivo de relatório gerado).")
        return {"violations": [], "incomplete": [], "testEngine": {"name": "axe-core"}}
    try:
        report_text = report_path.read_text(encoding="utf-8")
        return json.loads(report_text)
    except Exception as exc:
        logger.warning("[RemoteRunner] Relatório do Cypress local veio ilegível: %s", exc)
        return None
    finally:
        with contextlib.suppress(OSError):
            report_path.unlink()


def _default_local_cypress_dir() -> Path:
    """Diretório persistente (não um tempdir descartável) onde a instalação
    local do Cypress fica, pra não reinstalar a cada conversa."""
    import tempfile

    base = os.getenv("LOCALAPPDATA") or os.getenv("XDG_CACHE_HOME") or tempfile.gettempdir()
    return Path(base) / "qa_accessibility" / "cypress_local_project"


async def _install_local_cypress(timeout_seconds: float = 300.0) -> str | None:
    """
    Instala o Cypress + cypress-axe DE VERDADE (via `npm install`) num
    diretório persistente na máquina do backend -- só roda quando o usuário
    pediu explicitamente (`location="install_local"`), nunca automaticamente.
    Pode demorar minutos na primeira vez (binário do Cypress é grande).
    Devolve o caminho do projeto instalado, ou None se falhar.
    """
    import asyncio
    import shutil

    project_dir = _default_local_cypress_dir()
    project_dir.mkdir(parents=True, exist_ok=True)
    package_json = project_dir / "package.json"
    if not package_json.exists():
        package_json.write_text(
            json.dumps({"name": "qa-accessibility-cypress-local", "private": True}),
            encoding="utf-8",
        )
    # Achado real (2026-08-11): `npm install` só baixa os pacotes -- não faz o
    # "scaffold" que `cypress open` faria na primeira vez (que é interativo,
    # impossível de rodar num backend headless). Sem cypress.config.js, `cypress
    # run` recusa rodar de todo ("Could not find a Cypress configuration file"),
    # então a instalação "funcionava" (pacotes baixados) mas o teste real nunca
    # rodava -- reproduzido ao vivo com Cypress recém-instalado nesta máquina.
    config_js = project_dir / "cypress.config.js"
    if not config_js.exists():
        config_js.write_text(
            "const { defineConfig } = require('cypress');\n"
            "module.exports = defineConfig({ e2e: { supportFile: false, setupNodeEvents(_on, config) { return config; } } });\n",
            encoding="utf-8",
        )

    npm_path = shutil.which("npm")
    if not npm_path:
        logger.warning("[RemoteRunner] npm não encontrado no PATH -- não é possível instalar o Cypress.")
        return None

    logger.info("[RemoteRunner] Instalando Cypress + cypress-axe de verdade em %s (pode levar minutos)...", project_dir)
    try:
        proc = await asyncio.create_subprocess_exec(
            npm_path, "install", "--no-save", "cypress", "cypress-axe",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        if proc.returncode != 0:
            logger.warning("[RemoteRunner] Instalação do Cypress falhou: %s", stderr.decode("utf-8", errors="ignore")[:500])
            return None
    except TimeoutError:
        proc.kill()
        logger.warning("[RemoteRunner] Instalação do Cypress excedeu o timeout de %ss.", timeout_seconds)
        return None
    except Exception as exc:
        logger.warning("[RemoteRunner] Falha ao instalar Cypress: %s", exc)
        return None

    # Persiste o caminho pra próxima vez não precisar reinstalar -- mesmo
    # mecanismo de config persistente já usado pra chaves (secret_store.py),
    # aqui guardando um caminho local, não um segredo.
    with contextlib.suppress(Exception):
        from backend.src.security.secret_store import save_secret
        save_secret("CYPRESS_LOCAL_PROJECT_DIR", str(project_dir))
    os.environ["CYPRESS_LOCAL_PROJECT_DIR"] = str(project_dir)
    logger.info("[RemoteRunner] Cypress instalado com sucesso em %s", project_dir)
    return str(project_dir)


async def run_remote_cypress_simulation(
    url: str, scope_selector: str = "", location: str | None = None,
    project_dir_override: str | None = None,
) -> dict[str, Any]:
    """
    Roda uma auditoria de acessibilidade real com o motor axe-core, em UM dos
    lugares -- decisão explícita do USUÁRIO via `location`, nunca uma escolha
    silenciosa daqui:

    - `location="local"`: roda o binário Cypress DE VERDADE (Test Runner +
      cypress-axe) na máquina onde o backend roda, via
      `CYPRESS_LOCAL_PROJECT_DIR` (checado de verdade -- pode já estar
      instalado). Se não estiver, devolve `status="error"` oferecendo a
      instalação -- NÃO cai pra nuvem sozinho.
    - `location="install_local"`: instala Cypress + cypress-axe DE VERDADE
      (via npm) num diretório persistente, só depois do usuário confirmar
      explicitamente que quer isso (pode levar minutos) -- depois roda igual
      ao caminho "local".
    - `location="cloud"`: roda via axe-core remoto (Playwright/Browserless),
      mesmo motor de detecção, sem precisar de nada instalado.
    - `location=None`: mantido só por compatibilidade com chamadores antigos
      (ex.: testes) -- o chat_tools.py já barra essa chamada antes de chegar
      aqui quando o usuário ainda não decidiu (ver `run_remote_test_tool`).
      Sem `location`, o comportamento aqui é usar a nuvem, mas isso NUNCA
      deve acontecer a partir do chat sem o usuário ter sido perguntado.

    `scope_selector`, quando fornecido, filtra/escopa a checagem.
    """
    logger.info(
        "[RemoteRunner] Executando auditoria de acessibilidade (rótulo cypress, location=%s) para %s (escopo='%s')",
        location, url, scope_selector,
    )
    project_id = os.getenv("CYPRESS_PROJECT_ID", "").strip()
    record_key = os.getenv("CYPRESS_RECORD_KEY", "").strip()
    cypress_cloud_synced = bool(project_id and record_key)

    try:
        if location == "install_local":
            installed_dir = await _install_local_cypress()
            if installed_dir is None:
                return {
                    "status": "error",
                    "error": (
                        "Não foi possível instalar o Cypress automaticamente nesta máquina "
                        "(verifique se 'npm' está disponível no servidor). Pergunte ao usuário "
                        "se prefere rodar na nuvem em vez disso."
                    ),
                }
            location = "local"  # instalado com sucesso -- segue pro caminho local normal

        if location == "local":
            local_report = await _try_run_local_cypress(
                url, scope_selector, project_dir_override=project_dir_override,
            )
            if local_report is None:
                return {
                    "status": "error",
                    "error": (
                        "Cypress local não está disponível nesta máquina. Pergunte ao usuário se "
                        "ele quer que você instale agora (chame de novo com location="
                        "'install_local') ou se prefere rodar na nuvem (location='cloud')."
                    ),
                }
            summary = _summarize_axe_results(local_report)
            summary.update({
                "status": "ok",
                "runner": "cypress_local",
                "cypress_cloud_synced": cypress_cloud_synced,
                "cypress_project_id": project_id,
                "url": url,
                "scope": scope_selector or "global",
            })
            return summary

        from backend.src.services.browser import run_axe_core_audit
        axe_results = await run_axe_core_audit(url)

        if scope_selector:
            axe_results = dict(axe_results)
            axe_results["violations"] = [
                v for v in (axe_results.get("violations") or [])
                if any(scope_selector in "".join(n.get("target", [])) for n in v.get("nodes", []))
            ]

        summary = _summarize_axe_results(axe_results)
        summary.update({
            "status": "ok",
            "runner": "cypress_remote",
            "cypress_cloud_synced": cypress_cloud_synced,
            "cypress_project_id": project_id,
            "url": url,
            "scope": scope_selector or "global",
        })
        return summary
    except CypressProjectOutOfScopeError as exc:
        from backend.src.services.local_project_guard import accessibility_scope_denial_message
        return {"status": "error", "error": accessibility_scope_denial_message(exc.project_dir)}
    except CypressMultipleInstallationsFoundError as exc:
        candidates_list = "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(exc.candidates))
        return {
            "status": "needs_selection",
            "candidates": exc.candidates,
            "error": (
                f"Foram encontradas {len(exc.candidates)} instalações locais reais de Cypress nesta "
                f"máquina:\n{candidates_list}\nPergunte ao usuário via `clarify` qual delas usar "
                "(apresente as opções reais encontradas), e chame esta ferramenta de novo passando "
                "o caminho escolhido em `local_project_dir`."
            ),
        }
    except Exception as exc:
        logger.error("[RemoteRunner] Erro na auditoria de acessibilidade (cypress): %s", exc)
        return {"status": "error", "error": str(exc)}
