"""
Phase 2 agent loop: real function/tool calling.

Replaces Phase 1's regex-based intent detection (`_is_product_query`,
`_find_product` in app/orchestrator.py) with the model deciding, per
message, which tool(s) it needs and with what arguments. We execute exactly
what it asks for and feed the real result back, so it's still structurally
blocked from inventing facts -- same anti-hallucination guarantee as
Phase 1, just enforced via tool results instead of a hand-built facts
string.

NOTE: Phase 1's `_special_response()` guardrails (off-topic/programming
questions, the financial-distress response) are safety/off-topic filters,
not product lookups -- they don't belong in the tool loop. Keep running
that check *before* calling `handle_chat_message()` here, the same way
orchestrator.py did.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.agent.tools import TOOL_FUNCTIONS, TOOL_SPECS
from app.providers.llm import get_llm_provider

SYSTEM_PROMPT = """You are a helpful business assistant for an e-commerce store.

Rules you MUST follow:
- Only state prices, colors, stock, and facts that came back from a tool call.
  Never invent a price, color, date, or stock number.
- If a tool returns no results or an error, tell the user you don't have
  that information -- don't guess.
- Always identify a matched product using its model name and color, such as
  "AeroRun X1 in Pink". Do not call it only "shoes".
- Do not use Markdown formatting in your response.
- Keep answers short and conversational.
"""

MAX_TOOL_ITERATIONS = 4  # guard against infinite tool-call loops


async def handle_chat_message(
    db: Session, message: str
) -> tuple[str, list[dict[str, Any]]]:
    """Returns (reply_text, tool_calls_made). tool_calls_made is handy for
    logging and for letting the frontend render a product card from
    whatever search_products/check_stock actually returned."""
    llm = get_llm_provider()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    tool_calls_made: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        assistant_message = await llm.chat(messages, tools=TOOL_SPECS)
        tool_calls = assistant_message.get("tool_calls")

        if not tool_calls:
            content = (assistant_message.get("content") or "").strip()
            if not content:
                # Same failure mode as the Phase 1 blank-reply bug -- never
                # let an empty model response reach the user unexplained.
                content = "Sorry, I couldn't come up with a response -- could you rephrase that?"
            return content, tool_calls_made

        # The model wants to call one or more tools. Record its request,
        # execute each one for real against the DB, and feed the results back.
        messages.append(assistant_message)
        for call in tool_calls:
            name = call["function"]["name"]
            try:
                arguments = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}

            func = TOOL_FUNCTIONS.get(name)
            if func is None:
                result: dict[str, Any] = {"error": f"Unknown tool '{name}'"}
            else:
                try:
                    result = func(db, **arguments)
                except TypeError as exc:
                    result = {"error": f"Bad arguments for '{name}': {exc}"}

            tool_calls_made.append({"name": name, "arguments": arguments, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result),
                }
            )

    # Ran out of iterations without a final answer -- surface it rather than
    # silently returning nothing.
    return (
        "I wasn't able to finish looking that up -- could you try asking again?",
        tool_calls_made,
    )