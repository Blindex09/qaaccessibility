"""Grava uma chamada REAL de um provedor (texto, fluxo e chamada de ferramenta) e a guarda como arquivo de referência.

Por quê: mock inventado não prova integração (regra 11). O leitor do Gemini quebrou em produção porque os testes usavam um
formato de eventos que a API já não envia. Com a gravação real, os testes de contrato (`tests/backend/unit/providers/`)
reproduzem exatamente o que o provedor devolve, e o modo `--check` acusa quando o provedor muda o formato.

Uso:
  .venv/Scripts/python scripts/record_provider_contract.py --provider gemini            # grava
  .venv/Scripts/python scripts/record_provider_contract.py --provider gemini --check    # compara com o gravado

A chave vem do cofre (uma por provedor) e nunca é impressa nem gravada. Segredos do conteúdo (assinaturas de raciocínio) são
trocados por um marcador. Custa cerca de três chamadas mínimas.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "backend" / "fixtures" / "providers"
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

PROMPT = "Responda em uma frase: o que é contraste de cor?"
TOOL_PROMPT = "Qual o clima em Recife? Use a ferramenta clima."
TOOL = {
    "type": "function",
    "name": "clima",
    "description": "Clima de uma cidade",
    "parameters": {"type": "object", "properties": {"cidade": {"type": "string"}}, "required": ["cidade"]},
}


def scrub(value):
    """Troca assinaturas de raciocínio (longas e opacas) por um marcador, em qualquer profundidade."""
    if isinstance(value, dict):
        return {k: ("<assinatura omitida>" if "signature" in k and isinstance(v, str) else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def dump(obj):
    if hasattr(obj, "model_dump"):
        return scrub(obj.model_dump(exclude_none=True, mode="json"))
    return scrub(json.loads(json.dumps(obj, default=str)))


def key_for(provider: str) -> str:
    from backend.src.security.secret_store import load_provider_key

    key = load_provider_key("LLM", provider)
    if not key:
        raise SystemExit(f"Sem chave guardada para {provider}. Coloque-a nas Configurações.")
    return key


def record_gemini(model: str) -> dict:
    from google import genai

    client = genai.Client(api_key=key_for("gemini"))
    scenarios = {}
    for name, kwargs in (("text", {"input": PROMPT}), ("tool_call", {"input": TOOL_PROMPT, "tools": [TOOL]})):
        events, interaction_id = [], None
        for event in client.interactions.create(model=model, stream=True, store=True, **kwargs):
            events.append(dump(event))
            if getattr(event, "event_type", "") == "interaction.completed":
                interaction_id = event.interaction.id
        stored = dump(client.interactions.get(id=interaction_id)) if interaction_id else None
        scenarios[name] = {"events": events, "stored_interaction": stored}
    import importlib.metadata as metadata

    return {"sdk": {"google-genai": metadata.version("google-genai")}, "scenarios": scenarios}


def record_ollama(model: str) -> dict:
    import ollama

    client = ollama.Client(host="https://ollama.com", headers={"Authorization": f"Bearer {key_for('ollama-cloud')}"}, timeout=120)
    scenarios = {}
    tools = [{"type": "function", "function": {"name": TOOL["name"], "description": TOOL["description"], "parameters": TOOL["parameters"]}}]
    for name, kwargs in (
        ("text", {"messages": [{"role": "user", "content": PROMPT}]}),
        ("tool_call", {"messages": [{"role": "user", "content": TOOL_PROMPT}], "tools": tools}),
    ):
        chunks = [dump(chunk) for chunk in client.chat(model=model, stream=True, think=False, **kwargs)]
        scenarios[name] = {"events": chunks, "stored_interaction": None}
    import importlib.metadata as metadata

    return {"sdk": {"ollama": metadata.version("ollama")}, "scenarios": scenarios}


RECORDERS = {"gemini": (record_gemini, "gemini-3.5-flash-lite"), "ollama-cloud": (record_ollama, "gpt-oss:20b")}


def shape(recording: dict) -> dict:
    """O que identifica o formato: os tipos de evento (e os campos de cada um), não o texto."""
    result = {}
    for name, scenario in recording["scenarios"].items():
        kinds: dict[str, list[str]] = {}
        for event in scenario["events"]:
            kind = str(event.get("event_type") or event.get("type") or "chunk")
            kinds.setdefault(kind, sorted(set(kinds.get(kind, [])) | set(event.keys())))
        result[name] = kinds
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=sorted(RECORDERS))
    parser.add_argument("--model")
    parser.add_argument("--check", action="store_true", help="compara o formato atual com o gravado e acusa mudança")
    args = parser.parse_args()
    recorder, default_model = RECORDERS[args.provider]
    model = args.model or default_model
    path = FIXTURES / args.provider / "contract.json"

    recording = {
        "provider": args.provider,
        "model": model,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prompts": {"text": PROMPT, "tool_call": TOOL_PROMPT},
        **recorder(model),
    }
    if args.check:
        if not path.exists():
            print(f"Sem gravação anterior em {path}; rode sem --check.")
            return 2
        saved = json.loads(path.read_text(encoding="utf-8"))
        old, new = shape(saved), shape(recording)
        if old == new:
            print(f"SEM MUDANÇA de formato em {args.provider} (SDK {recording['sdk']}).")
            return 0
        print(f"MUDOU o formato de {args.provider}. Regrave, atualize o leitor e os testes de contrato.")
        for scenario in sorted(set(old) | set(new)):
            if old.get(scenario) != new.get(scenario):
                print(f"  cenário {scenario}:\n    antes:  {old.get(scenario)}\n    agora:  {new.get(scenario)}")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recording, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Gravado em {path.relative_to(ROOT)} ({sum(len(s['events']) for s in recording['scenarios'].values())} eventos, SDK {recording['sdk']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
