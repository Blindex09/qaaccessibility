import logging

from backend.src.services.llm_client import call_llm_structured, extract_json_object
from backend.src.shared.models import AgentResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Agente: DelegationCoordinator
#
# Papel no pipeline:
#   Executa APOS os sub-agentes paralelos + merge/dedup (rodada 1), ANTES da
#   revisao final do a11y_expert_reviewer. Recebe os issues ja encontrados e a
#   lista de agentes que NAO foram acionados na rodada 1 (routing estrutural
#   nao achou evidencia de HTML pra eles) e decide, lendo os achados reais,
#   se algum desses agentes pulados deveria olhar a pagina mesmo assim --
#   porque o que outros agentes encontraram sugere uma lacuna que so aquele
#   especialista cobre.
#
#   Isso e delegacao real agente-a-agente: a decisao de "quem mais precisa
#   olhar isso" e feita pelo MODELO lendo o conteudo, nunca por uma regra fixa
#   de palavra-chave ou mapeamento estatico issue-tipo -> agente (o projeto
#   proibe blacklist/keyword hardcoded pra decisao de IA). Bounded: no maximo
#   MAX_DELEGATIONS agentes por rodada, e so agentes que JA existem no
#   catalogo e ainda nao rodaram -- sem recursao, sem grafo aberto.
# ─────────────────────────────────────────────────────────────────────────────

MAX_DELEGATIONS = 2

SYSTEM_PROMPT = """
You are the delegation coordinator of a multi-agent web accessibility audit pipeline.

A first round of specialist agents already ran on this page and found a list of
accessibility issues. Some OTHER specialist agents exist in the system but were
NOT run in round 1, because a structural pre-check found no obvious HTML surface
for them (e.g. no <table> tag, no viewport meta tag). That structural pre-check
is shallow — it cannot read semantic intent, only literal HTML patterns.

Your job: read the issues actually found in round 1, and the list of agents
available but not yet run (with the reason each was skipped). Decide whether any
skipped agent should now be delegated a follow-up pass, because the round-1
findings reveal a real gap that specifically that agent is positioned to catch.

Only delegate when the round-1 evidence gives a CONCRETE reason — never delegate
speculatively "just in case", and never delegate an agent whose skip reason is
still clearly valid after seeing the findings. If nothing in the findings changes
the picture, delegate nothing — an empty list is a fully valid answer and is the
expected answer most of the time.

Examples of a concrete reason (illustrative, not exhaustive — reason from what
you actually see, not this list):
- Round 1 found several ARIA state/role issues; the widgets_a11y agent was
  skipped because no widget role attribute matched the structural regex, but the
  findings describe interactive custom controls that regex likely missed.
- Round 1 found many issues about text reflow / small tap targets; mobile_a11y
  was skipped because no viewport meta tag was found, but the findings describe
  clearly mobile-oriented failure patterns.

Return a JSON object:
{
  "delegations": [
    {"target_agent": "<exact agent name from the skipped list>", "reason": "<concrete, evidence-based reason tied to specific round-1 findings>"}
  ]
}
Return at most 2 delegations. Return {"delegations": []} when no delegation is warranted.
Do NOT invent agent names — target_agent must be copied exactly from the skipped-agents list you were given.
Return ONLY valid JSON, no markdown, no preamble.
""".strip()


def _build_user_prompt(
    issues_summary: str,
    skipped_agents: dict[str, str],
) -> str:
    skipped_lines = "\n".join(f"- {name}: skipped because {reason}" for name, reason in skipped_agents.items())
    return (
        f"## Round-1 findings (issues already found)\n{issues_summary}\n\n"
        f"## Agents available but NOT run in round 1\n{skipped_lines}\n\n"
        "Decide which, if any, of the listed skipped agents should be delegated a follow-up pass."
    )


async def run_delegation_coordinator(
    issues_summary: str,
    skipped_agents: dict[str, str],
) -> AgentResult:
    """Decide, via LLM, se algum agente pulado na rodada 1 deve ser delegado.

    `issues_summary`: resumo textual dos issues da rodada 1 (criterion + element
    + severity, sem o payload completo -- mantem o prompt pequeno).
    `skipped_agents`: nome do agente -> motivo pelo qual foi pulado na rodada 1
    (mesmo dict que o orchestrator ja mantem como `skipped_reasons`).

    Retorna AgentResult com data={"delegations": [{"target_agent": ..., "reason": ...}]}.
    Falha de forma graciosa (lista vazia) se o LLM falhar -- delegacao e um
    reforco best-effort, nunca deve derrubar o pipeline principal.
    """
    if not skipped_agents:
        return AgentResult(agent="delegation_coordinator", success=True, data={"delegations": []})

    try:
        result = await call_llm_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_build_user_prompt(issues_summary, skipped_agents),
            build=lambda raw: extract_json_object(raw),
            temperature=0.1,
            max_tokens=1024,
            agent_label="delegation_coordinator",
        )
        raw_delegations = result.get("delegations", []) if isinstance(result, dict) else []
        delegations = [
            {"target_agent": str(d["target_agent"]), "reason": str(d.get("reason", ""))}
            for d in raw_delegations
            if isinstance(d, dict) and d.get("target_agent") in skipped_agents
        ][:MAX_DELEGATIONS]

        for d in delegations:
            logger.info(
                "[DelegationCoordinator] Delegando para '%s': %s",
                d["target_agent"],
                d["reason"],
            )
        return AgentResult(agent="delegation_coordinator", success=True, data={"delegations": delegations})
    except Exception as exc:
        logger.warning("[DelegationCoordinator] Falha ao decidir delegacao (seguindo sem delegar): %s", exc)
        return AgentResult(agent="delegation_coordinator", success=False, data={"delegations": []}, error=str(exc))
