"""
direct_query.py — Standalone "ask anything, get Markdown back" feature.

WHAT THIS IS
  A single-shot LLM call that answers any free-text question in Markdown
  at a caller-specified length. Completely independent of the sales-agent
  flow — no tools, no DB queries, no conversation memory, no system prompt
  from the chatbot persona.

WHAT THIS IS NOT
  - Not a tool-calling loop (agent.py handles that).
  - Not a DB query (no products, orders, or store data accessed here).
  - Not a new LLM client — reuses the existing LLMProvider abstraction.

ENTRY POINT
  generate_direct_answer(question, length, max_words) → str (Markdown)
  Called by app/api/direct_query.py.
"""
from __future__ import annotations

from app.providers.llm import get_llm_provider_for_tenant

# ── Length → instruction map ──────────────────────────────────────────────────

_LENGTH_INSTRUCTIONS: dict[str, str] = {
    "short":  "Answer in 2-3 sentences. Be concise and direct.",
    "medium": "Answer in 1-2 short paragraphs. Cover the key points without padding.",
    "long": (
        "Answer thoroughly. Use multiple paragraphs. "
        "Where appropriate, add Markdown headings (##) and bullet lists to organise the content."
    ),
}

_SYSTEM_PROMPT = """\
You are a knowledgeable, helpful assistant.

Rules:
- Respond ONLY in valid Markdown.
- Do NOT call any tools.
- Do NOT reference store-specific data, products, orders, or customer information unless the user's question explicitly asks about them as general topics.
- Do NOT use the retail sales-agent persona. You are a general-purpose assistant.
- Obey the length instruction given in the user message exactly.
"""


def _build_user_message(question: str, length_instruction: str) -> str:
    return f"Length instruction: {length_instruction}\n\nQuestion: {question}"


async def generate_direct_answer(
    question: str,
    length: str = "medium",
    max_words: int | None = None,
) -> tuple[str, str]:
    """
    Generate a length-controlled Markdown answer for the given question.

    Args:
        question:  The user's free-text question.
        length:    One of 'short', 'medium', 'long'.
        max_words: Optional hard word-count cap — overrides the length preset.

    Returns:
        (answer_markdown, length_used)
        answer_markdown — the LLM's response as a Markdown string.
        length_used     — the effective length instruction that was applied.
    """
    if max_words is not None:
        length_instruction = f"Keep the answer under {max_words} words."
        length_used = f"max_words={max_words}"
    else:
        length_instruction = _LENGTH_INSTRUCTIONS.get(length, _LENGTH_INSTRUCTIONS["medium"])
        length_used = length

    user_message = _build_user_message(question, length_instruction)

    # Use the default tenant's LLM provider — same provider abstraction as the
    # chat endpoint, zero duplication, works with openai/groq/generic/mock.
    from app.config import get_tenant_context
    tenant = get_tenant_context("default")
    llm = get_llm_provider_for_tenant(tenant)

    answer = await llm.generate(
        system_prompt=_SYSTEM_PROMPT,
        user_message=user_message,
    )

    return answer, length_used
