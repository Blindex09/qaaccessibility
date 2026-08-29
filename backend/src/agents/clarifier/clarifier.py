import logging

from backend.src.services.llm_client import call_llm, extract_json_object
from backend.src.shared.models import AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are the QA Accessibility Clarifier and Semantic Router. Your ONLY job is to analyze the user's incoming message and route it to the correct intent, determining if the message is within the scope of digital accessibility auditing or if it is ambiguous and needs clarification.

You must categorize the user's message into one of these intents:
- "analyze_url": User explicitly wants to audit/analyze an external URL or web page.
- "analyze_code": User explicitly wants to audit/analyze a local file path, directory, or a raw HTML/CSS/JS/TSX code snippet.
- "chat_a11y": User is asking a conversational question, requesting a tutorial, explaining a concept, discussing accessibility rules (WCAG, Section 508, WAI-ARIA, contrast, screen readers), OR sending greetings/pleasantries/introductory remarks (e.g. "fala meu amigo, blz?", "olá", "tudo bem?", "bom dia", "pode me ajudar?"). All greetings and chat starters must be routed to "chat_a11y" so the conversational agent can greet the user naturally and keep the focus on accessibility.
- "fix_code": User provides a code snippet or describes accessibility issues and wants the agent to generate/provide a fixed, accessible version of that code.
- "out_of_scope": User is explicitly asking for general programming tasks (e.g. "write a backend database script"), general software engineering, or completely unrelated topics (cooking, politics, history) that have absolutely no connection to accessibility.
- "needs_clarification": The request is related to accessibility but is ambiguous, incomplete, or lacks critical details (e.g., "analyze this" without providing any code, file, or URL target, or "how do I fix" without a code snippet or context).

## Rules:
1. "out_of_scope": digital accessibility is the core limit. If a user asks "how do I center a div" without any accessibility context, it is out of scope. If they ask "how do I make a centered div focusable for screen readers", it is "chat_a11y".
2. Greetings and pleasantries ("olá", "tudo bem", "fala meu amigo, blz", "está aí?") are NOT out of scope. Route them to "chat_a11y" so the agent can respond conversationally.
3. "needs_clarification": Set this to true if the intent is "needs_clarification". In this case, you MUST generate 1 specific, polite clarification question to ask the user. For all other intents, questions should be empty.
4. Be highly semantic and ignore keywords. Analyze the meaning.

## Output Format:
You MUST return ONLY a valid JSON object matching this schema:
{
  "intent": "analyze_url | analyze_code | chat_a11y | fix_code | out_of_scope | needs_clarification",
  "needs_clarification": true | false,
  "question": "Clarification question text here, or empty if needs_clarification is false",
  "explanation": "Brief reasoning for the classification (Portuguese if user prompt is Portuguese, otherwise English)"
}

Return ONLY raw JSON. No markdown fences, no formatting, no conversational text.
""".strip()


async def run_clarifier(user_message: str) -> AgentResult:
    """
    Analisa semanticamente o input do usuário para definir a intencao do chat.
    Evita chamadas caras de ferramentas se a query for fora de escopo ou ambigua.
    """
    logger.info("[ClarifierAgent] Analisando intencao da mensagem do usuário...")
    if not user_message.strip():
        return AgentResult(
            agent="clarifier",
            success=True,
            data={
                "intent": "needs_clarification",
                "needs_clarification": True,
                "question": "Olá! Como posso ajudar você hoje com a acessibilidade do seu projeto?",
                "explanation": "Mensagem vazia.",
            },
        )

    try:
        raw = await call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=f"Analyze this user message:\n\n{user_message}",
            temperature=0.0,
            max_tokens=250,
            agent_label="clarifier",
            model_tier="fast",
        )
        data = extract_json_object(raw)

        # Garante fallback e chaves basicas
        intent = data.get("intent", "needs_clarification")
        needs_clarify = bool(data.get("needs_clarification", intent == "needs_clarification"))
        question = data.get("question", "")
        explanation = data.get("explanation", "")

        logger.info("[ClarifierAgent] Intencao classificada: %s", intent)
        return AgentResult(
            agent="clarifier",
            success=True,
            data={
                "intent": intent,
                "needs_clarification": needs_clarify,
                "question": question,
                "explanation": explanation,
            },
        )
    except Exception as exc:
        logger.error("[ClarifierAgent] Falha na clarificacao: %s", exc)
        return AgentResult(
            agent="clarifier",
            success=False,
            data={},
            error=str(exc),
        )
