"""Ferramentas oferecidas por pedido (regra 9: o roteador escolhe os grupos pelo significado).

O código só tem o catálogo. A concessão de segurança não muda; o agente nunca fica sem
alcance: ele pode habilitar outro grupo e ele entra na próxima chamada.
"""

import json
from unittest.mock import AsyncMock

import pytest

import backend.src.services.chat_tools  # noqa: F401  (registra as ferramentas)
from backend.src.services.chat_tools import A11Y_CHAT_TOOLSET, CLARIFY_TOOLSET
from backend.src.services.route_advisor import RouteCandidate, rank_candidates
from backend.src.services.tool_groups import (
    CORE_TOOLS,
    ENABLE_TOOL_GROUP,
    GROUP_DESCRIPTIONS,
    TOOL_GROUPS,
    classified_tools,
    offered_tools,
    tools_of_group,
)
from run_agent import AIAgent
from tools.registry import registry


def _chat_tools() -> set[str]:
    return {name for ts in (A11Y_CHAT_TOOLSET, CLARIFY_TOOLSET) for name in registry.get_tool_names_for_toolset(ts)}


# ----------------------------------------------------------------- catálogo
def test_every_chat_tool_is_classified_so_a_new_tool_never_vanishes_silently():
    unclassified = _chat_tools() - classified_tools()
    assert not unclassified, f"classifique em tool_groups.py: {sorted(unclassified)}"


def test_catalog_only_names_tools_that_exist():
    ghosts = classified_tools() - _chat_tools()
    assert not ghosts, f"ferramentas do catálogo que não existem: {sorted(ghosts)}"


def test_a_tool_belongs_to_one_group_only():
    seen: dict[str, str] = {}
    for group, names in TOOL_GROUPS.items():
        for name in names:
            assert name not in seen, f"{name} está em {seen[name]} e em {group}"
            seen[name] = group


def test_every_group_has_a_description_for_the_router():
    assert set(GROUP_DESCRIPTIONS) == set(TOOL_GROUPS)
    assert all(text.strip() for text in GROUP_DESCRIPTIONS.values())


def test_no_opinion_from_the_router_means_everything_is_offered():
    assert offered_tools(None, _chat_tools()) is None


def test_conceptual_question_gets_only_the_core_tools():
    assert offered_tools([], _chat_tools()) == CORE_TOOLS & _chat_tools()


def test_selected_group_adds_only_its_own_tools():
    offered = offered_tools(["analise"], _chat_tools())
    assert tools_of_group("analise") <= offered
    assert not (tools_of_group("correcao") & offered)
    assert offered >= CORE_TOOLS


def test_the_offered_set_is_much_smaller_than_everything():
    everything = _chat_tools()
    # 5 ferramentas sempre presentes (perguntar, squad, habilitar grupo, carregar e guardar habilidade), medido em 2026-10-18
    assert len(offered_tools([], everything)) <= 5 < len(everything)


# ----------------------------------------------------------------- agente
def _agent(offered):
    return AIAgent(provider="openai", model="m", api_key="k", enabled_toolsets=[A11Y_CHAT_TOOLSET, CLARIFY_TOOLSET],
                   offered_tools=offered)


def _names(agent) -> set[str]:
    return {tool["function"]["name"] for tool in agent._get_api_tools()}


def test_agent_offers_everything_when_the_router_has_no_opinion_and_hides_the_meta_tool():
    names = _names(_agent(None))
    assert names == _chat_tools() - {ENABLE_TOOL_GROUP}


def test_agent_offers_only_what_the_router_chose_plus_the_way_to_ask_for_more():
    names = _names(_agent(offered_tools([], _chat_tools())))
    assert names == CORE_TOOLS & _chat_tools()
    assert ENABLE_TOOL_GROUP in names


def test_a_group_enabled_on_demand_enters_the_next_call_and_stays():
    agent = _agent(offered_tools([], _chat_tools()))
    assert "fix_and_zip_files" not in _names(agent)
    answer = json.loads(agent._dispatch_tool(ENABLE_TOOL_GROUP, {"group": "correcao"}, None))
    assert answer["habilitado"] == "correcao" and "fix_and_zip_files" in answer["ferramentas"]
    assert "fix_and_zip_files" in _names(agent)
    assert "fix_and_zip_files" in _names(agent)  # não sai no meio da tarefa


def test_unknown_group_is_refused_with_the_valid_ones():
    agent = _agent(offered_tools([], _chat_tools()))
    answer = json.loads(agent._dispatch_tool(ENABLE_TOOL_GROUP, {"group": "inexistente"}, None))
    assert "error" in answer and "analise" in answer["error"]


def test_enabling_a_group_never_widens_the_security_grant():
    """O agente só amplia o que já lhe foi concedido ao nascer."""
    agent = AIAgent(provider="openai", model="m", api_key="k", enabled_toolsets=[CLARIFY_TOOLSET],
                    offered_tools=offered_tools([], _chat_tools()))
    answer = json.loads(agent._dispatch_tool(ENABLE_TOOL_GROUP, {"group": "analise"}, None))
    assert "concedida" in answer["error"]  # sem a concessão ao nascer, nem a ferramenta de habilitar roda
    assert "analyze_page" not in _names(agent)


def test_meta_tool_without_an_agent_explains_instead_of_pretending():
    from backend.src.services.chat_tools import enable_tool_group_without_agent

    assert "error" in json.loads(enable_tool_group_without_agent({"group": "analise"}))


# ----------------------------------------------------------------- roteador
def _candidates():
    return [RouteCandidate("ollama-cloud", m, 64000, ("tools",), 1, 2, .75, .75, 0) for m in ("a", "b", "c")]


def _answer(**extra):
    base = {"ranking": ["ollama-cloud::b", "ollama-cloud::a", "ollama-cloud::c"], "complexity": "low",
            "preference": "cost", "compare_models": [], "judge": "", "reason": "economia", "updates": []}
    return json.dumps(base | extra)


@pytest.mark.asyncio
async def test_router_receives_the_catalog_and_must_answer_with_groups_from_it():
    seen = {}

    async def ask(system, payload, schema):
        seen.update(system=system, payload=json.loads(payload), schema=schema)
        return _answer(tool_groups=["analise"])

    advice = await rank_candidates(_candidates(), task="analise a pagina x", step_type="chat", ask=ask,
                                   tool_catalog=GROUP_DESCRIPTIONS)
    assert advice.tool_groups == ["analise"]
    assert seen["payload"]["tool_groups_catalog"] == GROUP_DESCRIPTIONS
    assert "tool_groups" in seen["schema"]["required"]
    assert seen["schema"]["properties"]["tool_groups"]["items"]["enum"] == sorted(GROUP_DESCRIPTIONS)
    assert "lista vazia" in seen["system"]


@pytest.mark.asyncio
async def test_empty_list_is_a_valid_decision_not_a_missing_one():
    ask = AsyncMock(return_value=_answer(tool_groups=[]))
    advice = await rank_candidates(_candidates(), task="o que é WCAG?", step_type="chat-q", ask=ask,
                                   tool_catalog=GROUP_DESCRIPTIONS)
    assert advice.tool_groups == []  # [] = nenhum grupo; None seria "sem opinião"


@pytest.mark.asyncio
async def test_unknown_group_from_the_model_triggers_the_single_contract_repair():
    ask = AsyncMock(side_effect=[_answer(tool_groups=["inventado"]), _answer(tool_groups=["pesquisa"])])
    advice = await rank_candidates(_candidates(), task="pesquise", step_type="chat-r", ask=ask,
                                   tool_catalog=GROUP_DESCRIPTIONS)
    assert advice.tool_groups == ["pesquisa"] and ask.await_count == 2


@pytest.mark.asyncio
async def test_without_a_catalog_the_router_is_not_asked_for_groups_and_gives_no_opinion():
    seen = {}

    async def ask(system, payload, schema):
        seen["schema"] = schema
        return _answer(tool_groups=["analise"])  # mesmo que o modelo invente, ninguém pediu

    advice = await rank_candidates(_candidates(), task="t-sem-catalogo", step_type="clarifier", ask=ask)
    assert "tool_groups" not in seen["schema"]["properties"]
    assert advice.tool_groups is None  # sem opinião: o agente recebe tudo


@pytest.mark.asyncio
async def test_duplicate_groups_are_collapsed_in_order():
    ask = AsyncMock(return_value=_answer(tool_groups=["analise", "documentos", "analise"]))
    advice = await rank_candidates(_candidates(), task="t-dup", step_type="chat-d", ask=ask,
                                   tool_catalog=GROUP_DESCRIPTIONS)
    assert advice.tool_groups == ["analise", "documentos"]


# ----------------------------------------------------------------- menor privilégio e custo da pesquisa profunda
def test_agent_grant_can_be_narrowed_to_the_tools_the_caller_listed():
    agent = AIAgent(provider="openai", model="m", api_key="k", enabled_toolsets=[A11Y_CHAT_TOOLSET, CLARIFY_TOOLSET],
                    allowed_tools=["tavily_search", "exa_search"])
    assert _names(agent) == {"tavily_search", "exa_search"}
    refused = json.loads(agent._dispatch_tool("analyze_page", {"url": "https://example.com"}, None))
    assert "concedida" in refused["error"]  # o resto do toolset NÃO foi concedido


def test_deep_research_subagent_only_receives_search_tools_not_all_33():
    """Regressão (e2e real 2026-10-07): o sub-agente da pesquisa recebia as 33 ferramentas do chat,
    contra o menor privilégio, e pagava ~11 mil tokens de schema a cada chamada."""
    import asyncio
    from unittest.mock import patch

    from backend.src.agents.deep_research import deep_research

    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run_conversation(self, *args, **kwargs):
            return {"final_response": "ok", "failed": False}

    with patch("run_agent.AIAgent", FakeAgent):
        asyncio.run(deep_research.run_deep_research("o que é 1.4.3?"))
    granted = set(captured["allowed_tools"])
    assert granted == tools_of_group("pesquisa") - {"run_deep_research"}
    assert "analyze_page" not in granted and "fix_and_zip_files" not in granted
    assert "run_deep_research" not in granted  # sem recursão


def test_deep_research_spends_a_lot_so_it_goes_through_the_approval_setting():
    assert registry.tools["run_deep_research"]["requires_approval"] is True
    description = registry.tools["run_deep_research"]["schema"]["description"]
    assert "CUSTO ALTO" in description


def test_router_is_told_the_research_group_is_expensive():
    assert "centenas de milhares" in GROUP_DESCRIPTIONS["pesquisa"]
