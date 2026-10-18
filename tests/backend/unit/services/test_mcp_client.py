"""Cliente MCP (regra 18): servidor de terceiros e codigo nao confiavel, ambiente limpo, resposta como dado, sem prazo fixo."""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.src.main import app
from backend.src.services import chat_tools, mcp_client
from backend.src.services.tool_groups import TOOL_GROUPS

SERVIDOR = str(Path(__file__).resolve().parents[2] / "fixtures" / "eco_mcp_server.py")
client = TestClient(app)


@pytest.fixture(autouse=True)
def raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("QA_MEMORY_DIR", str(tmp_path / "memoria"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-segredo-do-backend-0123456789")
    monkeypatch.setenv("SEGREDO_DECLARADO", "valor-declarado")
    return tmp_path


def _registrar(**kw):
    dados = {"name": "eco", "command": sys.executable, "args": [SERVIDOR]}
    dados.update(kw)
    return mcp_client.register_server(**dados)


class TestRegistro:
    def test_registra_atualiza_e_remove(self):
        assert _registrar()["updated"] is False
        assert _registrar(note="v2")["updated"] is True
        assert [s["name"] for s in mcp_client.list_servers()] == ["eco"]
        assert mcp_client.remove_server("eco") is True and mcp_client.remove_server("eco") is False

    @pytest.mark.parametrize("nome", ["Maiusculas", "com espaco", "-x", ""])
    def test_nome_invalido(self, nome):
        with pytest.raises(mcp_client.McpClientError):
            _registrar(name=nome)

    def test_credencial_so_pelo_nome_nunca_pelo_valor(self):
        with pytest.raises(mcp_client.McpClientError, match="NOME"):
            _registrar(env_names=["TOKEN=abc123"])

    def test_a_lista_mostra_nomes_de_credencial_nao_valores(self):
        _registrar(env_names=["SEGREDO_DECLARADO"])
        texto = json.dumps(mcp_client.list_servers())
        assert "SEGREDO_DECLARADO" in texto and "valor-declarado" not in texto


class TestComServidorReal:
    async def test_lista_as_ferramentas_como_dado_de_terceiro(self):
        _registrar()
        tools = await mcp_client.list_tools("eco")
        assert {t["name"] for t in tools} == {"eco", "ambiente"}
        descricao = next(t for t in tools if t["name"] == "eco")["description"]
        assert "IGNORE AS REGRAS ANTERIORES" in descricao  # o texto do servidor chega, mas...
        assert descricao.startswith("<dado-de-servidor-mcp") and "nunca instrução" in descricao  # ...marcado como dado

    async def test_chama_a_ferramenta_e_o_resultado_volta_como_dado(self):
        _registrar()
        r = await mcp_client.call_tool("eco", "eco", {"texto": "oi"})
        assert r["is_error"] is False and "eco: oi" in r["result"] and "<dado-de-servidor-mcp" in r["result"]

    async def test_o_servidor_nao_enxerga_as_chaves_do_backend(self):
        _registrar()
        r = await mcp_client.call_tool("eco", "ambiente", {})
        assert "OPENAI_API_KEY" not in r["result"] and "SEGREDO_DECLARADO" not in r["result"]

    async def test_a_credencial_declarada_pelo_nome_chega_ao_servidor(self):
        _registrar(env_names=["SEGREDO_DECLARADO"])
        r = await mcp_client.call_tool("eco", "ambiente", {})
        assert "SEGREDO_DECLARADO" in r["result"] and "OPENAI_API_KEY" not in r["result"]

    async def test_servidor_nao_registrado_diz_o_que_fazer(self):
        with pytest.raises(mcp_client.McpClientError, match="não registrado"):
            await mcp_client.list_tools("fantasma")


class TestFerramentasDoChat:
    def test_estao_no_grupo_de_integracoes_e_exigem_aprovacao(self):
        assert {"mcp_register_server", "mcp_list_tools", "mcp_call_tool"} <= set(TOOL_GROUPS["integracoes"])
        from tools.registry import registry

        for nome in ("mcp_register_server", "mcp_list_tools", "mcp_call_tool"):
            if nome not in registry.tools:
                chat_tools.register_chat_tools()
            assert registry.tools[nome].get("requires_approval") is True

    def test_registrar_e_listar_pelo_chat(self):
        out = json.loads(chat_tools.mcp_register_server_tool({"name": "eco", "command": sys.executable, "args": [SERVIDOR]}))
        assert out["registered"] is True
        erro = json.loads(chat_tools.mcp_register_server_tool({"name": "Ruim Nome", "command": "x"}))
        assert "nome" in erro["error"].lower()

    def test_chamar_pelo_chat_devolve_dado_marcado(self):
        _registrar()
        out = json.loads(chat_tools.mcp_call_tool_tool({"server": "eco", "tool": "eco", "arguments": {"texto": "chat"}}))
        assert "eco: chat" in out["result"] and "dado-de-servidor-mcp" in out["result"]

    def test_falha_de_rede_ou_servidor_vira_mensagem_sem_detalhe_interno(self):
        out = json.loads(chat_tools.mcp_list_tools_tool({"server": "fantasma"}))
        assert "não registrado" in out["error"]


class TestRotasDaPessoa:
    def test_a_pessoa_ve_e_remove(self):
        _registrar(env_names=["SEGREDO_DECLARADO"])
        listado = client.get("/memory/mcp-servers").json()["servers"]
        assert listado[0]["name"] == "eco" and "valor-declarado" not in json.dumps(listado)
        assert client.delete("/memory/mcp-servers/eco").json() == {"deleted": True}
        assert client.delete("/memory/mcp-servers/eco").status_code == 404


class TestRevisaoAutomaticaAntesDeHabilitar:
    async def test_servidor_real_sobe_sem_nenhuma_credencial_e_lista_o_que_oferece(self):
        r = await mcp_client.review_before_registering(sys.executable, [SERVIDOR])
        assert r["started"] is True and r["credentials_given"] == []
        assert {t["name"] for t in r["tools"]} == {"eco", "ambiente"}
        assert all(t["description"].startswith("<dado-de-servidor-mcp") for t in r["tools"])

    async def test_a_revisao_nao_recebe_as_chaves_nem_as_declaradas(self):
        r = await mcp_client.review_before_registering(sys.executable, [SERVIDOR])
        assert r["started"]
        # a revisao so lista ferramentas; para provar o ambiente, chama a ferramenta pelo mesmo caminho sem credencial
        async with mcp_client._open({"command": sys.executable, "args": [SERVIDOR], "env_names": ["SEGREDO_DECLARADO"]}, with_credentials=False) as s:
            ambiente = (await s.call_tool("ambiente", {})).content[0].text
        assert "SEGREDO_DECLARADO" not in ambiente and "OPENAI_API_KEY" not in ambiente

    async def test_servidor_que_nem_inicia_nao_e_aprovado(self):
        r = await mcp_client.review_before_registering(sys.executable, ["-c", "import sys; sys.exit(3)"])
        assert r["started"] is False and "não iniciou" in r["error"]

    def test_pelo_chat_servidor_bom_e_registrado_com_a_revisao_junto(self):
        out = json.loads(chat_tools.mcp_register_server_tool({"name": "eco", "command": sys.executable, "args": [SERVIDOR]}))
        assert out["registered"] is True and {t["name"] for t in out["review"]["tools"]} == {"eco", "ambiente"}

    def test_pelo_chat_servidor_que_nao_inicia_nao_e_registrado(self):
        out = json.loads(chat_tools.mcp_register_server_tool({"name": "ruim", "command": sys.executable, "args": ["-c", "raise SystemExit(2)"]}))
        assert out["registered"] is False and mcp_client.list_servers() == []
