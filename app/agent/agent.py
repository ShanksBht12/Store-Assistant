"""
agent.py — Business-agnostic LLM chat loop.

This file runs one conversation turn:
  1. Loads message history from the database.
  2. Sends history + new message to the LLM with the registry's tool specs.
  3. If the LLM calls a tool, dispatches it through the ToolRegistry and feeds
     the result back — no knowledge of what the tool does or what it queries.
  4. Repeats until the LLM produces a plain-text reply.
  5. Saves updated history and returns (reply, card_data, payment_method).

WHAT THIS FILE KNOWS NOTHING ABOUT
  - Products, Orders, Product ORM models
  - search_products, create_order, check_stock, or any tool by name
  - eSewa, Khalti, or any payment rail
  - Phone number formats or validation rules
  - Any business type whatsoever

All of that lives in the ToolRegistry implementation injected at call time.
The retail adapter is in retail_registry.py. A marketing agency adapter would
be in agency_registry.py, etc. This file stays unchanged when a new business
type is onboarded.

REGISTRY INJECTION
  handle_chat_message() accepts a `registry: ToolRegistry` parameter.
  router.py constructs the right registry for the active tenant and passes it in.
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.agent.prompt import PromptRegistry
from app.agent.registry import ToolRegistry
from app.database.models import ConversationState
from app.providers.llm.base import LLMProvider

if TYPE_CHECKING:
    from app.config import TenantContext


MAX_TOOL_ITERATIONS = 10  # ordering flow can use up to 4-5 tools in one turn
MAX_HISTORY_MESSAGES = 60  # trim old turns to keep context window manageable


# ── Message history helpers ───────────────────────────────────────────────────

def _load_messages(state: ConversationState, tenant: "TenantContext") -> list[dict[str, Any]]:
    if state.messages:
        msgs = list(state.messages)
        # Refresh system prompt on every turn so activating a new prompt
        # version or changing tenant config takes effect without a restart.
        active_prompt = PromptRegistry.get_active_prompt_for_tenant(tenant)
        if msgs and msgs[0].get("role") == "system":
            msgs[0]["content"] = active_prompt
        return msgs
    active_prompt = PromptRegistry.get_active_prompt_for_tenant(tenant)
    return [{"role": "system", "content": active_prompt}]


def _save_messages(
    db: Session,
    state: ConversationState,
    messages: list[dict[str, Any]],
) -> None:
    system = messages[:1]
    rest   = messages[1:]
    if len(rest) > MAX_HISTORY_MESSAGES:
        rest = rest[-MAX_HISTORY_MESSAGES:]
    state.messages = system + rest
    db.add(state)
    db.commit()


# ── Markdown stripper ─────────────────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    """Remove Markdown artifacts the LLM occasionally leaks despite being
    instructed not to. Applied to every assistant reply."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(
        r"https?://(?:images\.unsplash\.com|unsplash\.com|i\.imgur\.com|cdn\.\S+)\S*",
        "", text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r"https?://\S+\.(?:png|jpg|jpeg|gif|webp|svg)(?:\?\S*)?",
        "", text, flags=re.IGNORECASE,
    )
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}(.*?)_{1,2}",   r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+",   "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+",   "", text, flags=re.MULTILINE)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Message sanitiser ─────────────────────────────────────────────────────────

def _sanitise_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise the message list before sending to the LLM API.

    Fixes two classes of issues:
    1. Assistant tool-call messages must have a `content` key (null is fine).
    2. Dangling assistant tool-call blocks with no matching tool responses are
       dropped — they arise when a previous request failed mid-turn.
    """
    responded_ids: set[str] = set()
    for msg in messages:
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            responded_ids.add(msg["tool_call_id"])

    clean: list[dict[str, Any]] = []
    dropped_ids: set[str] = set()

    for msg in messages:
        role = msg.get("role")

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                ids_needed = [
                    tc.get("id") for tc in tool_calls
                    if isinstance(tc, dict) and tc.get("id")
                ]
                if not all(tc_id in responded_ids for tc_id in ids_needed):
                    for tc_id in ids_needed:
                        dropped_ids.add(tc_id)
                    continue
                clean.append({
                    "role":       "assistant",
                    "content":    msg.get("content"),
                    "tool_calls": tool_calls,
                })
            else:
                clean.append({"role": "assistant", "content": msg.get("content", "")})

        elif role == "tool":
            tc_id = msg.get("tool_call_id")
            if not tc_id or tc_id in dropped_ids:
                continue
            clean.append(msg)

        else:
            clean.append(msg)

    return clean


# ── Main entry point ──────────────────────────────────────────────────────────

async def handle_chat_message(
    db:              Session,
    conversation_id: str,
    message:         str,
    registry:        ToolRegistry,
    tenant:          "TenantContext",
    llm:             LLMProvider,
) -> tuple[str, dict | None, str | None]:
    """
    Run one user turn through the agent loop.

    Parameters
    ----------
    db              : SQLAlchemy session
    conversation_id : UUID string for this conversation
    message         : the customer's latest message
    registry        : ToolRegistry implementation for this tenant/business type
    tenant          : TenantContext for prompt rendering and digital_payments set
    llm             : LLMProvider resolved for this tenant — injected by router.py
                      so agent.py never calls the global provider factory directly

    Returns
    -------
    (reply_text, card_data, payment_method)
    """
    # ── Load or create conversation state ────────────────────────────────────
    state = db.get(ConversationState, conversation_id)
    if state is None:
        state = ConversationState(
            id=conversation_id,
            messages=[{
                "role":    "system",
                "content": PromptRegistry.get_active_prompt_for_tenant(tenant),
            }],
        )
        db.add(state)
        db.commit()

    last_clean_messages = _load_messages(state, tenant)
    messages = list(last_clean_messages)
    messages.append({"role": "user", "content": message})

    tool_calls_made: list[dict[str, Any]] = []
    digital_payments = set(tenant.digital_payments)

    # ── Finalise helper (called on every exit path) ───────────────────────────
    def _finalise(content: str, msgs: list) -> tuple[str, dict | None, str | None]:
        _save_messages(db, state, msgs)
        card_data, payment_method = registry.extract_turn_extras(db, tool_calls_made)
        return content, card_data, payment_method

    # ── Tool-calling loop ─────────────────────────────────────────────────────
    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            assistant_message = await llm.chat(
                _sanitise_messages(messages),
                tools=registry.tool_specs,
            )
            tool_calls = assistant_message.get("tool_calls")

            if not tool_calls:
                # Plain-text reply — return it directly.
                raw_content = (assistant_message.get("content") or "").strip()
                content     = _strip_markdown(raw_content) or (
                    "Sorry, I couldn't come up with a response — could you rephrase that?"
                )
                messages.append({"role": "assistant", "content": content})
                return _finalise(content, messages)

            # Append assistant tool-call message
            messages.append(assistant_message)

            # Dispatch every tool in this iteration
            for call in tool_calls:
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                result = registry.run_tool(db, name, arguments, conversation_id)

                tool_calls_made.append({
                    "name":      name,
                    "arguments": arguments,
                    "result":    result,
                })
                messages.append({
                    "role":        "tool",
                    "tool_call_id": call["id"],
                    "content":     json.dumps(result),
                })

            # Check for a deterministic order/transaction confirmation.
            # If the registry returns one, skip the LLM reply for this turn.
            confirmation, payment_method = registry.build_order_confirmation(
                tool_calls_made, digital_payments
            )
            if confirmation:
                confirmation = _strip_markdown(confirmation)
                messages.append({"role": "assistant", "content": confirmation})
                _save_messages(db, state, messages)
                card_data, _ = registry.extract_turn_extras(db, tool_calls_made)
                return confirmation, card_data, payment_method

            # All tool results appended — safe checkpoint.
            last_clean_messages = list(messages)

        # Exhausted max iterations
        fallback = "I wasn't able to finish looking that up — could you try asking again?"
        messages.append({"role": "assistant", "content": fallback})
        return _finalise(fallback, messages)

    except Exception:
        # Preserve the last clean state so future requests don't get a 400.
        safe = list(last_clean_messages)
        safe.append({"role": "user", "content": message})
        _save_messages(db, state, safe)
        raise
