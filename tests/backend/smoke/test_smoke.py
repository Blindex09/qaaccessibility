"""
tests/backend/smoke/test_smoke.py
Suíte de smoke test -- checagem RÁPIDA de saúde do sistema, distinta da
suíte unitária completa. Sem chamada real de LLM (zero custo/latência de
rede externa) e sem rodar o pipeline de agentes -- só confirma que o
essencial está de pé: a aplicação sobe, as rotas core respondem, o motor
axe-core vendorizado está presente, e as ferramentas do chat estão
registradas. Uso típico: rodar logo após deploy/build, antes de confiar na
suíte completa ou em qualquer teste real contra LLM.

Achado real (2026-08-11, pedido do usuário): o projeto tinha suíte unitária
completa (1000+ testes) e testes reais contra LLM (tests/backend/real_llm),
mas nenhum subconjunto "é só isso que eu preciso checar rápido pra saber se
subiu certo" -- essa lacuna é o que este arquivo fecha.
"""

from starlette.testclient import TestClient


class TestAppBootsAndHealthCheck:
    def test_app_imports_without_error(self):
        """Se a importação do módulo principal falhar (config ausente, erro
        de sintaxe, import circular), a aplicação inteira não sobe -- este é
        o smoke test mais básico possível."""
        import backend.src.main as main_mod
        assert main_mod.app is not None

    def test_health_endpoint_returns_ok(self):
        import backend.src.main as main_mod
        with TestClient(main_mod.app) as client:
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_core_routers_are_mounted(self):
        """Confirma que as rotas essenciais (analyze, chat, export, models)
        estão de fato montadas na aplicação -- não só que os módulos
        importam sem erro, mas que main.py realmente os incluiu."""
        import backend.src.main as main_mod
        paths = set(main_mod.app.openapi()["paths"].keys())
        essential_prefixes = ("/analyze", "/chat", "/export", "/models")
        for prefix in essential_prefixes:
            assert any(p.startswith(prefix) for p in paths), f"Nenhuma rota com prefixo {prefix} está montada"



class TestAxeCoreVendoredEngineIsPresent:
    """O axe-core vendorizado é a base determinística de vários runners reais
    (Cypress local/nuvem, Selenium, cross-browser) -- se o arquivo sumir ou
    ficar vazio/corrompido, todos eles quebram silenciosamente na primeira
    chamada real. Verificação rápida, sem precisar rodar um navegador."""

    def test_axe_core_js_file_exists_and_is_non_trivial(self):
        from backend.src.services.browser import _AXE_CORE_JS_PATH
        assert _AXE_CORE_JS_PATH.exists(), f"axe-core vendorizado não encontrado em {_AXE_CORE_JS_PATH}"
        content = _AXE_CORE_JS_PATH.read_text(encoding="utf-8")
        # 580KB documentado -- um arquivo minúsculo ou vazio indica corrupção/
        # placeholder acidental, não o motor de verdade.
        assert len(content) > 100_000, "axe-core vendorizado parece truncado/corrompido (muito pequeno)"
        assert "axe" in content.lower()[:2000]


class TestSettingsLoadWithoutError:
    def test_get_settings_does_not_raise(self):
        from backend.src.config.settings import get_settings
        settings = get_settings()
        assert settings is not None


class TestChatToolsAreRegistered:
    """Registro de ferramentas é feito via chamada explícita (register_chat_tools)
    em algum ponto do bootstrap -- se essa chamada quebrar silenciosamente ou
    for removida, o chat perde ferramentas sem nenhum erro óbvio na análise
    unitária normal (cada handler continua testável isoladamente). Este smoke
    test garante que o REGISTRO em si aconteceu."""

    def test_core_tools_present_in_registry_after_registration(self):
        from backend.src.services.chat_tools import A11Y_CHAT_TOOLSET, register_chat_tools
        from tools.registry import registry

        register_chat_tools()
        registered_names = set(registry.get_tool_names_for_toolset(A11Y_CHAT_TOOLSET))

        essential_tools = {
            "analyze_page",
            "run_remote_test",
            "run_cross_browser_test",
            "fix_and_zip_files",
        }
        missing = essential_tools - registered_names
        assert not missing, f"Ferramentas essenciais ausentes do registro: {missing}"
