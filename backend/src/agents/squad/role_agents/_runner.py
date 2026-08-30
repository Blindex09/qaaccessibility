"""Execução compartilhada dos agentes de papel da squad.

Por que um runner único: os seis papéis diferem no QUE decidem (o
`SYSTEM_PROMPT` e o handoff que produzem), não em COMO são executados. Copiar
o mesmo bloco de call_llm + parse + tratamento de erro seis vezes seria a
duplicação que o README proíbe. Aqui há uma via só; cada módulo de papel traz
apenas a sua responsabilidade.

Degradação: um papel que falha NUNCA derruba o fluxo da squad. Ele devolve uma
`RoleDecision` com `succeeded=False` e um blocker legível, e o coordenador
decide -- do mesmo jeito que um membro real de squad que não conseguiu
concluir levanta a mão em vez de travar a sprint.
"""

import json
import logging
from typing import Any

from backend.src.services.llm_client import call_llm

from ..contracts import RoleDecision
from ..roles import SquadRole

logger = logging.getLogger(__name__)

# Contrato de saída comum a todos os papéis. Vai no fim de cada SYSTEM_PROMPT
# para que o modelo devolva sempre a mesma forma, qualquer que seja o papel.
OUTPUT_CONTRACT = """
## Output contract (MANDATORY)

Return ONLY a single JSON object, no prose, no markdown fences:

{
  "summary": "one sentence: what you decided, in the user's language",
  "decisions": ["short, verifiable statements of what is now decided"],
  "blockers": ["what genuinely prevents moving forward; empty list if none"],
  "handoff": { "key": "value pairs the NEXT role consumes as input" }
}

Rules:
- `blockers` is not a wishlist. Only list something that actually stops the
  next role from doing its job. An empty list is the normal case.
- `handoff` is the deliverable, not a summary for a human. Put in it exactly
  what the next role needs to act.
- Never invent findings about the page. You coordinate; the 29 accessibility
  specialists detect. Stay inside your role.
- Answer in the same language as the user's request.
"""

_MAX_INPUT_CHARS = 12000


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Extrai o objeto JSON da resposta, tolerando cercas de markdown.

    `extract_json_array` do llm_client resolve o caso de LISTA, que é o
    formato dos agentes de detecção. Papéis devolvem um OBJETO, então o
    equivalente vive aqui em vez de afrouxar aquele helper para os dois.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("resposta do papel nao contem objeto JSON")
    return json.loads(text[start : end + 1])


async def run_role(
    *,
    role: SquadRole,
    system_prompt: str,
    context: dict[str, Any],
    model_tier: str = "alto",
) -> RoleDecision:
    """Roda um papel da squad e devolve a decisão dele.

    `context` é o que o papel recebe para decidir -- tipicamente o objetivo do
    usuário mais os `handoff` dos papéis anteriores. Serializado como JSON
    para o modelo, sem template de texto: o que um papel entrega é o que o
    próximo lê, literalmente.
    """
    payload = json.dumps(context, ensure_ascii=False, indent=2)[:_MAX_INPUT_CHARS]
    logger.info("[Squad:%s] Decidindo (contexto=%d chars)", role.value, len(payload))

    try:
        raw = await call_llm(
            system_prompt=system_prompt + OUTPUT_CONTRACT,
            user_prompt=f"Squad context so far:\n{payload}",
            temperature=0.2,
            agent_label=f"squad_{role.value}",
            model_tier=model_tier,
        )
        data = _extract_json_object(raw)
    except Exception as exc:
        logger.warning("[Squad:%s] Falhou: %s", role.value, exc)
        return RoleDecision(
            role=role,
            summary=f"O papel {role.value} nao conseguiu concluir sua decisao.",
            blockers=[f"{role.value} indisponivel nesta rodada: {exc}"],
            succeeded=False,
            error=str(exc),
        )

    handoff = data.get("handoff")
    decision = RoleDecision(
        role=role,
        summary=str(data.get("summary") or "").strip(),
        decisions=_coerce_str_list(data.get("decisions")),
        blockers=_coerce_str_list(data.get("blockers")),
        handoff=handoff if isinstance(handoff, dict) else {},
    )
    logger.info(
        "[Squad:%s] %d decisao(oes), %d bloqueio(s)",
        role.value,
        len(decision.decisions),
        len(decision.blockers),
    )
    return decision
