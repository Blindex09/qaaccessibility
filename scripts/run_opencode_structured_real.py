"""Valida o fallback real Ollama Cloud -> OpenCode Go/GPT-5.6 Luna."""

import asyncio
import getpass
import json
import os
import sys


async def main():
    # Ambiente primeiro: `getpass` bloqueia esperando stdin interativo, entao
    # rodar este script de forma nao-interativa (CI, agente, nohup) travava
    # para sempre sem imprimir nada. So cai no prompt quando ha terminal.
    key = os.getenv("OPENCODE_GO_API_KEY") or os.getenv("OPENCODE_API_KEY")
    if not key and sys.stdin is not None and sys.stdin.isatty():
        key = getpass.getpass("OPENCODE_GO_API_KEY: ")
    if not key:
        raise SystemExit(
            "Defina OPENCODE_GO_API_KEY (ou OPENCODE_API_KEY) no ambiente antes de rodar "
            "este script, ou execute-o num terminal interativo."
        )
    os.environ["OPENCODE_GO_API_KEY"] = key

    from backend.src.services.llm_client import call_llm_structured

    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "route": {"type": "string"}},
        "required": ["ok", "route"],
        "additionalProperties": False,
    }

    result = await call_llm_structured(
        "Return only the requested JSON object.",
        "Return ok=true and route='structured-fallback'.",
        lambda raw: json.loads(raw),
        attempts=1,
        max_tokens=256,
        agent_label="e2e-opencode-structured-fallback",
        response_schema=schema,
    )
    if result.get("ok") is not True or result.get("route") != "structured-fallback":
        raise AssertionError(result)
    print("structured_output=ok provider_expected=opencode-go model_expected=gpt-5.6-luna", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"STRUCTURED_FAILURE={type(exc).__name__}: {exc}", flush=True)
        sys.exit(1)
