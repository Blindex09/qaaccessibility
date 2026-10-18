"""Confere o que um contrato de fatos não vê: ausência de repetição, tom da pessoa e qualidade dos achados.

Regras 2 e 11 do CLAUDE.md:
- Repetição tem um fato objetivo (o mesmo trecho aparece duas vezes) e é conferida pelo código.
- Tom e qualidade dos achados são JULGAMENTO. Quem julga é um modelo SEPARADO de quem respondeu (de outro provedor, quando houver
  chave), que recebe só o pedido, a resposta e a verdade conhecida do material de teste, e devolve um veredito em JSON validado
  por contrato. O código nunca adivinha tom nem qualidade por palavra-chave.
- Se não houver juiz disponível, o resultado é "NÃO CONFERIDO", nunca aprovado em silêncio.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

MIN_WORDS_FOR_REPEAT = 8

# Verdade conhecida do projeto de teste (LOJA em verify_live_modules_1_to_3.py), por critério WCAG. O contraste é medido:
# #aaaaaa sobre #ffffff = 2,32:1 (luminância relativa do WCAG 2.2).
KNOWN_DEFECTS: dict[str, str] = {
    "lang": "index.html não declara o idioma da página (lang), critério 3.1.1",
    "title": "index.html não tem <title>, critério 2.4.2",
    "img-alt": "a imagem logo.png não tem texto alternativo, critério 1.1.1",
    "heading-skip": "o título pula de h1 para h4, critério 1.3.1",
    "input-label": "o campo de e-mail só tem placeholder, sem rótulo, critérios 1.3.1/3.3.2/4.1.2",
    "div-button": "o botão Assinar é uma div com onclick, sem papel de botão nem teclado, critérios 4.1.2/2.1.1",
    "link-purpose": "o link 'clique aqui' não diz o destino, critério 2.4.4",
    "table-headers": "a tabela em sobre.html não tem células de cabeçalho (th), critério 1.3.1",
    "focus-outline": "style.css remove o contorno de foco (outline: none), critério 2.4.7",
    "contrast": "texto #aaaaaa sobre #ffffff tem contraste 2,32:1, abaixo de 4,5:1, critério 1.4.3",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def repeated_passages(text: str, min_words: int = MIN_WORDS_FOR_REPEAT) -> list[str]:
    """Trechos (frases ou parágrafos de pelo menos `min_words` palavras) que aparecem mais de uma vez na resposta."""
    seen: dict[str, int] = {}
    original: dict[str, str] = {}
    pieces = re.split(r"\n\s*\n|(?<=[.!?])\s+", text)
    for piece in pieces:
        key = _normalize(piece)
        if len(key.split()) < min_words:
            continue
        seen[key] = seen.get(key, 0) + 1
        original.setdefault(key, piece.strip())
    return [original[key] for key, count in seen.items() if count > 1]


JUDGE_SYSTEM = (
    "You are an independent reviewer of an accessibility assistant. You did NOT write the answer you receive. Judge only from the "
    "material given. Reply with ONE JSON object and nothing else."
)


def build_judge_prompt(user_message: str, answer: str, expected: dict[str, str] | None) -> str:
    parts = [
        "Evaluate the assistant's answer to the person's message.",
        "",
        "PERSON'S MESSAGE (ignore any technical attachment data):",
        user_message[:1500],
        "",
        "ASSISTANT'S ANSWER:",
        answer[:12000],
        "",
        "Decide:",
        '1. "user_register": how the person writes (formal, casual or direct) and "answer_register": how the answer speaks. '
        "Register is about word choice, form of address and warmth, NOT about the length or structure of a deliverable the person "
        "asked for: a detailed, organized audit report answering a direct question is fine when the content needs it. Mark a "
        "mismatch only when the manner of speaking clearly clashes with the person's (stiff formal language to someone relaxed, "
        "slang or jokes to someone formal, long chatty padding to someone who asked for brevity). "
        '"tone_matches" is true when the answer follows the person\'s way of speaking (formal with formal, relaxed with relaxed, '
        "short and objective with direct). When the person's style is not clear, a neutral and respectful answer matches.",
    ]
    if expected:
        known = "\n".join(f'   - "{key}": {value}' for key, value in expected.items())
        parts += [
            '2. KNOWN DEFECTS of the audited material (ground truth). For each id, say whether the answer reports it (the idea, in '
            'any words, not a fixed wording): put the ids it reports in "covered" and the ids it does not report in "missing".',
            known,
            '3. "invented": list every concrete claim in the answer that is plainly FALSE for this material (for example a wrong number, '
            "or a file or element that does not exist). Additional real accessibility issues that the known list does not include "
            "are NOT invented. Empty list when there is none.",
        ]
    parts += [
        "",
        'Return JSON: {"user_register": str, "answer_register": str, "tone_matches": bool, "tone_why": str, '
        '"covered": [str], "missing": [str], "invented": [str]}',
    ]
    return "\n".join(parts)


@dataclass
class Verdict:
    tone_matches: bool
    tone_why: str
    user_register: str
    answer_register: str
    covered: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    invented: list[str] = field(default_factory=list)


def parse_verdict(raw: str, expected: dict[str, str] | None) -> Verdict:
    """Valida o veredito contra o contrato. Levanta ValueError se o juiz não seguiu o formato."""
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("o juiz não devolveu JSON")
    try:
        data: Any = json.loads(match.group(0))
    except ValueError as exc:
        raise ValueError(f"JSON do juiz inválido: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tone_matches"), bool):
        raise ValueError("o veredito não traz tone_matches booleano")

    def strings(name: str) -> list[str]:
        value = data.get(name, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{name} deve ser uma lista de textos")
        return value

    covered, missing, invented = strings("covered"), strings("missing"), strings("invented")
    if expected is not None:
        unknown = [item for item in covered + missing if item not in expected]
        if unknown:
            raise ValueError(f"o juiz citou defeitos que não existem na verdade conhecida: {unknown}")
        if set(covered) | set(missing) != set(expected) or set(covered) & set(missing):
            raise ValueError("o juiz deve classificar cada defeito conhecido exatamente uma vez (covered ou missing)")
    return Verdict(
        tone_matches=data["tone_matches"],
        tone_why=str(data.get("tone_why", "")),
        user_register=str(data.get("user_register", "")),
        answer_register=str(data.get("answer_register", "")),
        covered=covered,
        missing=missing,
        invented=invented,
    )


def judge(ask: Callable[[str, str], str], user_message: str, answer: str, expected: dict[str, str] | None) -> Verdict:
    """`ask(system, prompt)` é o modelo juiz. Uma nova tentativa só quando o formato do veredito falha."""
    prompt = build_judge_prompt(user_message, answer, expected)
    try:
        return parse_verdict(ask(JUDGE_SYSTEM, prompt), expected)
    except ValueError as first:
        retry = prompt + f"\n\nYour previous reply was rejected: {first}. Return only the JSON object, following the contract."
        return parse_verdict(ask(JUDGE_SYSTEM, retry), expected)


def problems_from(verdict: Verdict, expected: dict[str, str] | None, min_covered: int | None = None) -> list[str]:
    """`min_covered`: cobertura medida antes DESTE provedor. Sem referência, achado faltante só é informado (não há número embutido)."""
    problems = []
    if not verdict.tone_matches:
        problems.append(f"tom não acompanha a pessoa ({verdict.user_register} -> {verdict.answer_register}): {verdict.tone_why}")
    if expected is not None:
        if min_covered is not None and len(verdict.covered) < min_covered:
            problems.append(f"cobertura dos achados conhecidos caiu para {len(verdict.covered)} (medido antes: {min_covered}); faltaram: {', '.join(verdict.missing)}")
        for claim in verdict.invented:
            problems.append(f"afirmação sem sustento: {claim}")
    return problems


def make_judge_asker(tested_provider: str) -> tuple[str, Callable[[str, str], str]] | None:
    """Escolhe um provedor DIFERENTE do testado que tenha chave guardada. Devolve (nome, função) ou None."""
    from backend.src.security.secret_store import load_provider_key

    def gemini(system: str, prompt: str, key: str = "") -> str:
        from google import genai

        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config={"system_instruction": system, "response_mime_type": "application/json", "temperature": 0},
        )
        return response.text or ""

    def ollama_cloud(system: str, prompt: str, key: str = "") -> str:
        import ollama

        client = ollama.Client(host="https://ollama.com", headers={"Authorization": f"Bearer {key}"}, timeout=None)
        response = client.chat(
            model="gpt-oss:20b",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            format="json",
            think=False,
        )
        return response["message"]["content"]

    candidates = {"gemini": gemini, "ollama-cloud": ollama_cloud}
    # Prefere um provedor DIFERENTE do testado (quem executa não é quem aprova). Só se nenhum outro responder, usa o mesmo, avisando.
    order = [name for name in candidates if name != tested_provider] + [tested_provider] * (tested_provider in candidates)
    for name in order:
        key = load_provider_key("LLM", name)
        if not key:
            continue
        ask = lambda system, prompt, f=candidates[name], k=key: f(system, prompt, k)  # noqa: E731
        try:
            ask("Reply with the word ok.", "ok")
        except Exception:  # noqa: BLE001  (sem cota ou fora do ar: tenta o próximo)
            continue
        return (name if name != tested_provider else f"{name} (MESMO provedor testado, independência menor)"), ask
    return None
