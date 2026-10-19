"""Prova de comportamento com o servidor MCP de acessibilidade (a ferramenta `verify_page_behavior`).

O Qaaccessibility analisa o codigo; o servidor MCP do dono mede o comportamento num navegador real. Aqui se confere a ferramenta, o grupo que o roteador
ve (a decisao de QUANDO usar e' do modelo, pelo significado; o codigo so oferece), a regra do prompt e, com o servidor de verdade por stdio,
que a chamada unica funciona mesmo o cliente MCP subindo o servidor de novo a cada chamada.
"""

import json
import os
import sys
from pathlib import Path

import pytest

from backend.src.services import chat_tools, mcp_client
from backend.src.services.chat_runtime import SYSTEM_PROMPT
from backend.src.services.tool_groups import GROUP_DESCRIPTIONS, TOOL_GROUPS, offered_tools
from tools.registry import registry

MCP_SERVER = Path(os.environ.get("A11Y_MCP_SERVER_PATH", r"C:\projetos IA\mcp\mcp_server.py"))  # o projeto mcp do dono; sem ele os testes de integracao sao pulados

PAGINA = """<!doctype html><html lang="pt"><head><title>Teste</title></head><body><main><h1>Loja</h1>
<button id="abrir">Abrir</button>
<dialog id="d" aria-labelledby="t"><h2 id="t">Confirmar</h2><button id="x">Fechar</button></dialog>
<script>
 document.getElementById('abrir').addEventListener('click', () => document.getElementById('d').showModal());
 document.getElementById('x').addEventListener('click', () => document.getElementById('d').close());
</script></main></body></html>"""


@pytest.fixture(autouse=True)
def raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("QA_MEMORY_DIR", str(tmp_path / "memoria"))
    if "verify_page_behavior" not in registry.tools:
        chat_tools.register_chat_tools()


# ------------------------------------------------------------------ o que o roteador e o modelo veem
class TestCatalogo:
    def test_a_ferramenta_exige_aprovacao_e_fica_num_grupo_proprio(self):
        assert registry.tools["verify_page_behavior"]["requires_approval"] is True
        assert TOOL_GROUPS["comportamento"] == ("verify_page_behavior",)

    def test_o_roteador_ve_a_descricao_do_grupo_e_so_oferece_a_ferramenta_quando_ele_escolhe(self):
        todas = {n for ts in ("a11y_chat", "clarify") for n in registry.get_tool_names_for_toolset(ts)}
        assert "verify_page_behavior" not in offered_tools(["analise"], todas)  # nao vem de brinde
        assert "verify_page_behavior" in offered_tools(["comportamento"], todas)
        assert "verify_page_behavior" not in offered_tools([], todas)  # pergunta conceitual nao a recebe

    def test_a_descricao_do_grupo_diz_quando_usar_e_quando_nao_usar(self):
        texto = GROUP_DESCRIPTIONS["comportamento"]
        for trecho in ("navegador real", "em execução", "confirmar que uma correção", "Não é para ler marcação", "custa um navegador real"):
            assert trecho in texto

    def test_a_ferramenta_diz_ao_modelo_quando_usar_quando_nao_usar_e_o_que_nao_prova(self):
        d = registry.tools["verify_page_behavior"]["schema"]["description"]
        for trecho in ("Do NOT use it to read markup", "WITHOUT `probes`", "null means it could not be measured", "real screen readers", "needs the person's approval"):
            assert trecho in d

    def test_a_regra_23_do_prompt_manda_decidir_pelo_significado_e_nao_afirmar_o_que_nao_foi_provado(self):
        texto = SYSTEM_PROMPT[SYSTEM_PROMPT.index("23. PROVING BEHAVIOR"):]
        for trecho in ("Decide by meaning, not by words", "once without probes", "do not claim anything was proven", "null means not measured"):
            assert trecho in texto


# ------------------------------------------------------------------ o gatilho (sem servidor)
class TestEntradas:
    def test_exige_exatamente_url_ou_html(self):
        assert "exatamente" in json.loads(chat_tools.verify_page_behavior_tool({}))["error"]
        assert "exatamente" in json.loads(chat_tools.verify_page_behavior_tool({"url": "http://x", "html": "<p>"}))["error"]

    def test_as_sondas_precisam_ser_uma_lista_de_objetos_com_kind(self):
        assert "probes" in json.loads(chat_tools.verify_page_behavior_tool({"url": "http://x", "probes": "dialog"}))["error"]
        assert "probes" in json.loads(chat_tools.verify_page_behavior_tool({"url": "http://x", "probes": [{"target": "css:a"}]}))["error"]

    def test_sem_o_servidor_registrado_diz_o_que_fazer_e_nao_finge_que_provou(self):
        saida = json.loads(chat_tools.verify_page_behavior_tool({"url": "http://127.0.0.1:1/"}))
        assert saida["status"] == "not_registered"
        assert "NÃO foi provado" in saida["message"] and saida["how_to_register"]["tool"] == "mcp_register_server" and saida["how_to_register"]["name"] == "accessibility"


class TestChamadaAoServidor:
    def test_repassa_os_argumentos_e_devolve_o_resultado_como_dado(self, monkeypatch):
        mcp_client.register_server("accessibility", sys.executable, ["x.py"])
        chamado = {}

        async def falso(servidor, ferramenta, argumentos):
            chamado.update(servidor=servidor, ferramenta=ferramenta, argumentos=argumentos)
            return {"server": servidor, "tool": ferramenta, "is_error": False, "result": "<dado-de-servidor-mcp>fatos</dado-de-servidor-mcp>"}

        monkeypatch.setattr(mcp_client, "call_tool", falso)
        saida = json.loads(chat_tools.verify_page_behavior_tool(
            {"url": "http://exemplo.test/", "probes": [{"kind": "dialog", "target": "css:#abrir"}], "persona": "screen_reader", "browser": "firefox"}))
        assert chamado["servidor"] == "accessibility" and chamado["ferramenta"] == "a11y_check_page"
        assert json.loads(chamado["argumentos"]["probes"]) == [{"kind": "dialog", "target": "css:#abrir"}]
        assert chamado["argumentos"]["persona"] == "screen_reader" and chamado["argumentos"]["browser"] == "firefox" and chamado["argumentos"]["url"] == "http://exemplo.test/"
        assert saida["status"] == "ok" and "dado-de-servidor-mcp" in saida["result"] and "leitor de tela real" in saida["note"]

    def test_o_padrao_e_so_teclado_e_chromium_e_primeira_chamada_sem_sondas(self, monkeypatch):
        mcp_client.register_server("accessibility", sys.executable, ["x.py"])
        chamado = {}

        async def falso(servidor, ferramenta, argumentos):
            chamado.update(argumentos)
            return {"server": servidor, "tool": ferramenta, "is_error": False, "result": "ok"}

        monkeypatch.setattr(mcp_client, "call_tool", falso)
        chat_tools.verify_page_behavior_tool({"html": "<p>oi</p>"})
        assert chamado["persona"] == "keyboard" and chamado["browser"] == "chromium" and chamado["probes"] == "" and chamado["html"] == "<p>oi</p>"

    def test_erro_do_servidor_vira_status_error_e_falha_de_conexao_vira_mensagem_sem_detalhe_interno(self, monkeypatch):
        mcp_client.register_server("accessibility", sys.executable, ["x.py"])

        async def com_erro(*a):
            return {"server": "accessibility", "tool": "a11y_check_page", "is_error": True, "result": "falhou"}

        monkeypatch.setattr(mcp_client, "call_tool", com_erro)
        assert json.loads(chat_tools.verify_page_behavior_tool({"url": "http://x/"}))["status"] == "error"

        async def explode(*a):
            raise OSError("caminho secreto C:\\x")

        monkeypatch.setattr(mcp_client, "call_tool", explode)
        saida = json.loads(chat_tools.verify_page_behavior_tool({"url": "http://x/"}))
        assert saida["status"] == "error" and "OSError" in saida["error"] and "secreto" not in json.dumps(saida)


# ------------------------------------------------------------------ o servidor de verdade, por stdio, uma chamada por processo
@pytest.mark.skipif(not MCP_SERVER.is_file(), reason="projeto mcp do dono nao esta nesta maquina")
class TestComServidorReal:
    """Mock nao prova integracao: aqui o cliente MCP do Qaaccessibility sobe o servidor de verdade a CADA chamada (como sempre faz) e a verificacao
    funciona porque a ferramenta e' de chamada unica. Com sessao entre chamadas, a segunda chamada perderia o navegador da primeira."""

    def _registrar(self):
        mcp_client.register_server("accessibility", sys.executable, [str(MCP_SERVER)])

    def test_primeira_chamada_traz_os_fatos_e_os_seletores(self):
        self._registrar()
        saida = json.loads(chat_tools.verify_page_behavior_tool({"html": PAGINA}))
        assert saida["status"] == "ok", saida
        corpo = saida["result"]
        assert "<dado-de-servidor-mcp" in corpo and "nunca instrução" in corpo
        dados = json.loads(corpo.split("\n", 1)[1].rsplit("\n</dado-de-servidor-mcp>", 1)[0])
        assert dados["tab_walk"]["stops"] and any(e["css"] == "#abrir" for e in dados["elements"]) and "leitor de tela real" in dados["not_verified"]

    def test_segunda_chamada_roda_a_sonda_com_o_seletor_da_primeira_num_processo_novo(self):
        self._registrar()
        saida = json.loads(chat_tools.verify_page_behavior_tool({"html": PAGINA, "probes": [{"kind": "dialog", "target": "css:#abrir"}]}))
        assert saida["status"] == "ok", saida
        dados = json.loads(saida["result"].split("\n", 1)[1].rsplit("\n</dado-de-servidor-mcp>", 1)[0])
        sonda = dados["probes"][0]
        assert sonda["kind"] == "dialog" and sonda["unmet"] == [] and len(sonda["checks"]) == 8
