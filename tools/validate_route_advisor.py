"""Validação real opt-in do consultor; reutiliza a chave protegida sem exibi-la.

Uso: python -m tools.validate_route_advisor --live
"""

import argparse
import asyncio
import json

from backend.src.config.settings import get_settings
from backend.src.services.route_advisor import advise_route


async def validate() -> None:
    settings = get_settings()
    tasks = [
        "O usuário disse boa noite após uma saudação. Responda brevemente, sem auditoria solicitada.",
        "Audite este combobox ARIA: aria-expanded=true; aria-controls referencia lista ausente; "
        "foco permanece no input, mas aria-activedescendant referencia item removido. "
        "Analise evidências, limites da conclusão e plano de teste com NVDA.",
    ]
    for task in tasks:
        advice = await advise_route(
            "ollama-cloud", "alto", task=task, step_type="validation",
            api_key=settings.llm_api_key, base_url="https://ollama.com/v1",
            timeout=45, output_tokens=3000,
        )
        print(json.dumps(advice.model_dump(), ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Autoriza chamadas reais ao provedor")
    args = parser.parse_args()
    if not args.live:
        parser.error("Use --live para autorizar chamadas reais.")
    asyncio.run(validate())
