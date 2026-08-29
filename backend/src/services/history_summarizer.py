"""LLM summarization of older conversation turns for long-running chats.

Replaces the crude `content[:max_chars]` clip that the HTML-oriented
`context_compressor` performed on plain chat text: that path silently dropped
whatever fell past the limit, so the agent simply forgot the middle of the
conversation with no trace of what was lost.

Pattern follows Anthropic's compaction guidance (platform.claude.com,
"Compaction") and its context-engineering article: once a size threshold is
crossed, summarize the older turns into one compact block and keep the most
recent turns verbatim, preserving decisions, unresolved questions and concrete
technical details rather than prose.

Cost is real, so the caller only invokes this when the budget is actually
exceeded, and the summarizer itself runs as a leaf sub-agent -- no tools, single
iteration, minimal reasoning effort -- exactly like the other cheap sub-agent
calls in this codebase.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SUMMARY_MAX_TOKENS = 1024

SUMMARY_PROMPT = (
    "You compact the older part of a conversation so an assistant can keep working "
    "without re-reading it. Write a dense summary that preserves: the user's goal and "
    "constraints, decisions already made, facts and identifiers established (URLs, file "
    "names, error messages, WCAG criteria), work already completed, and any question "
    "still open. Drop pleasantries and redundant tool chatter. Write plain prose, no "
    "markdown, no preamble, and never invent anything that is not in the transcript."
)


def render_transcript(messages: list[dict[str, Any]]) -> str:
    """Flatten messages into a readable transcript for the summarizer."""
    return "\n\n".join(
        f"{message.get('role', 'unknown')}: {str(message.get('content') or '').strip()}" for message in messages
    )


def summarize_messages(
    messages: list[dict[str, Any]],
    provider: str,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """Summarize `messages` into a single compact block.

    Raises `RuntimeError` when the provider call fails or returns nothing, so the
    caller can fall back to truncation deliberately instead of losing the turn.
    """
    if not messages:
        return ""

    from run_agent import AIAgent

    agent = AIAgent(
        model=model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        max_iterations=1,
        quiet_mode=True,
        max_tokens=_SUMMARY_MAX_TOKENS,
        # Leaf call: no tools, minimal reasoning -- this is a compression step,
        # not a task that benefits from deliberation.
        request_overrides={"reasoning_effort": "low"},
        ephemeral_system_prompt=SUMMARY_PROMPT,
        enabled_toolsets=[],
        log_prefix="[a11y:compaction]",
    )
    result = agent.run_conversation(
        user_message=("Summarize the following earlier part of the conversation:\n\n" + render_transcript(messages))
    )

    if result.get("failed"):
        raise RuntimeError(str(result.get("error") or "falha sem detalhe no resumo do histórico"))

    summary = str(result.get("final_response") or "").strip()
    if not summary:
        raise RuntimeError("o modelo devolveu um resumo vazio do histórico")

    logger.info(
        "[history_summarizer] %d mensagens antigas resumidas em %d chars",
        len(messages),
        len(summary),
    )
    return summary
