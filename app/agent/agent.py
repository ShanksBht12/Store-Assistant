"""
Phase 2 agent loop: real function/tool calling with persisted conversation memory.

Every request loads the full message history from ConversationState, appends
the new user turn, runs the tool-calling loop, saves the updated history, and
returns the reply text together with the last product the agent touched (so
the frontend can render a product card).
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.agent.tools import TOOLS, TOOL_SPECS
from app.database.models import ConversationState, Product
from app.providers.llm import get_llm_provider

SYSTEM_PROMPT = """You are a friendly and knowledgeable sales assistant for a shoe store called "Store Assistant".

## Core rules
- NEVER invent prices, stock numbers, colors, or product names. Every factual claim must come from a tool result.
- If a tool returns no results or an error, tell the user honestly — do not guess.
- NEVER use any Markdown formatting whatsoever. This means:
  - No **bold** or *italic* (never use asterisks)
  - No bullet points starting with - or *
  - No numbered lists with 1. 2. 3.
  - No headers with # or ##
  - No backticks or code blocks
  - Write everything as plain flowing sentences and paragraphs only.
  - For order confirmations, write them as plain sentences: "Your order ID is 3. Total is NPR 13,000. Payment method is eSewa."
- Keep replies concise. One to three sentences unless the user asks for a full list.

## Memory & context
- You have full memory of this conversation. Use it.
- If the user told you their name, use it naturally in replies.
- If the user previously mentioned a product, refer back to it when relevant.
- If the user says "that one", "this shoe", "the same one", etc., look up the product from earlier in the conversation.

## Handling product queries
- For ANY question about products, prices, stock, availability, or recommendations — always call search_products first.
- For broad queries ("show me all shoes", "what do you have", "list everything") call search_products with no query and a high max_results (use 50).
- For comparative queries ("cheapest", "most expensive", "best value") call search_products to get all relevant products, then reason over the results to answer.
- For a specific product query ("how much are black Nike shoes?") call search_products with the relevant query and color filter.
- Never answer a product question from memory — always call the tool even if you think you know the answer.

## Handling order status enquiries
- When a customer asks about their order status, tracking, or payment confirmation, call get_order_status.
- Look up by order_id if they have it, otherwise by phone number.
- Report the status clearly: pending_payment means awaiting payment, paid means confirmed, cancelled means the order was cancelled.

## Handling purchase intent
- When a customer wants to buy: confirm the exact product and call check_stock before anything else.
- Collect size/color if relevant, one question at a time.
- Then collect full name, phone number, and delivery address, one at a time.
- Ask for payment method last: eSewa, Khalti, or Cash on Delivery.
- Only call create_order once you have ALL of the above. Never invent or assume any detail.
- After create_order succeeds, confirm the order id, total, and next step for their payment method.

## Handling non-product messages
- Greet the user warmly. If they tell you their name, acknowledge it and use it.
- For general chit-chat, respond briefly and steer back toward helping with the store.
- Politely decline requests outside your scope (coding help, unrelated advice, etc.).
"""

MAX_TOOL_ITERATIONS = 6   # guard against infinite tool-call loops
MAX_HISTORY_MESSAGES = 60  # trim old turns to keep context window manageable


def _load_messages(state: ConversationState) -> list[dict[str, Any]]:
    if state.messages:
        msgs = list(state.messages)
        # Always keep system prompt fresh so prompt changes take effect
        # on existing conversations too.
        if msgs and msgs[0].get("role") == "system":
            msgs[0]["content"] = SYSTEM_PROMPT
        return msgs
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def _save_messages(db: Session, state: ConversationState, messages: list[dict[str, Any]]) -> None:
    system = messages[:1]
    rest = messages[1:]
    if len(rest) > MAX_HISTORY_MESSAGES:
        rest = rest[-MAX_HISTORY_MESSAGES:]
    state.messages = system + rest
    db.add(state)
    db.commit()


def _strip_markdown(text: str) -> str:
    """Remove common Markdown artifacts the LLM occasionally leaks
    despite being told not to. Applied to every assistant reply."""
    # Remove bold/italic: **text** -> text, *text* -> text, __text__ -> text
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}(.*?)_{1,2}", r"\1", text)
    # Remove ATX headers: ## Heading -> Heading
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Convert markdown bullet/numbered lists to plain lines
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Remove inline code backticks
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Collapse triple+ blank lines to double
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()





def _sanitise_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise the message list before sending to the API.

    Handles two problems that cause 400s from OpenRouter:
    1. Assistant messages with tool_calls but content=None — must send content
       as an empty string or null explicitly, not omit the key.
    2. Tool messages must always have tool_call_id. If it was lost during a
       JSON round-trip through SQLite, drop the orphaned tool message to avoid
       a malformed history (better to lose one turn than to crash every turn).
    """
    clean: list[dict[str, Any]] = []
    # Collect valid tool_call ids from assistant messages in this pass
    valid_tool_call_ids: set[str] = set()

    for msg in messages:
        role = msg.get("role")

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                # Ensure content key exists (even as None/null)
                out = {
                    "role": "assistant",
                    "content": msg.get("content"),  # null is fine, missing is not
                    "tool_calls": tool_calls,
                }
                for tc in tool_calls:
                    tc_id = tc.get("id") if isinstance(tc, dict) else None
                    if tc_id:
                        valid_tool_call_ids.add(tc_id)
            else:
                out = {"role": "assistant", "content": msg.get("content", "")}
            clean.append(out)

        elif role == "tool":
            tc_id = msg.get("tool_call_id")
            if not tc_id:
                # Orphaned tool message — drop it
                continue
            valid_tool_call_ids.discard(tc_id)
            clean.append(msg)

        else:
            clean.append(msg)

    return clean





def _extract_product_and_payment(
    db: Session, tool_calls_made: list[dict[str, Any]]
) -> tuple[Product | None, str | None]:
    """Return (last_product, payment_method_or_None).

    - last_product: the most recently touched Product for the frontend card.
    - payment_method: normalised lowercase name ('esewa' or 'khalti') when
      a create_order succeeded with a digital payment method, so the frontend
      knows to render the matching QR code. None for Cash on Delivery or if
      no order was placed this turn.
    """
    product: Product | None = None
    payment_method: str | None = None

    for call in tool_calls_made:
        result = call.get("result", {})

        # search_products returns {"products": [...]}
        if call["name"] == "search_products":
            products_data = result.get("products", [])
            if len(products_data) == 1:
                p = db.get(Product, products_data[0]["id"])
                if p:
                    product = p

        # check_stock and get_price_history return a product_id directly
        elif call["name"] in ("check_stock", "get_price_history"):
            pid = result.get("product_id")
            if pid:
                p = db.get(Product, pid)
                if p:
                    product = p

        # create_order: capture product AND payment method
        elif call["name"] == "create_order":
            # Only surface QR when the order actually succeeded (has order_id)
            if "order_id" in result:
                pid = call.get("arguments", {}).get("product_id")
                if pid:
                    p = db.get(Product, pid)
                    if p:
                        product = p

                raw_pm = result.get("payment_method", "")
                normalised = raw_pm.strip().lower()
                if normalised in _DIGITAL_PAYMENT_METHODS:
                    payment_method = normalised

    return product, payment_method


async def handle_chat_message(
    db: Session, conversation_id: str, message: str
) -> tuple[str, Product | None, str | None]:
    """Run one user turn through the agent loop.

    Returns (reply_text, product_or_None, payment_method_or_None).
    - product: last product the agent touched — frontend renders a product card.
    - payment_method: 'esewa' or 'khalti' when an order was just placed with
      a digital payment method — frontend renders the matching QR code.
    """
    state = db.get(ConversationState, conversation_id)
    if state is None:
        state = ConversationState(
            id=conversation_id,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}],
        )
        db.add(state)
        db.commit()

    messages = _load_messages(state)
    messages.append({"role": "user", "content": message})

    llm = get_llm_provider()
    tool_calls_made: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        assistant_message = await llm.chat(_sanitise_messages(messages), tools=TOOL_SPECS)
        tool_calls = assistant_message.get("tool_calls")

        if not tool_calls:
            # The model produced a plain text reply — we're done.
            content = (assistant_message.get("content") or "").strip()
            content = _strip_markdown(content)
            if not content:
                content = "Sorry, I couldn't come up with a response — could you rephrase that?"
            messages.append({"role": "assistant", "content": content})
            _save_messages(db, state, messages)
            product, payment_method = _extract_product_and_payment(db, tool_calls_made)
            return content, product, payment_method

        # Model wants to call one or more tools — execute them all.
        messages.append(assistant_message)
        for call in tool_calls:
            name = call["function"]["name"]
            try:
                arguments = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}

            # conversation_id is our bookkeeping — inject it for create_order.
            if name == "create_order":
                arguments["conversation_id"] = conversation_id

            func = TOOLS.get(name)
            if func is None:
                result: dict[str, Any] = {"error": f"Unknown tool '{name}'"}
            else:
                try:
                    result = func.run(db, **arguments)
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

    # Exhausted iterations without a final text reply.
    fallback = "I wasn't able to finish looking that up — could you try asking again?"
    messages.append({"role": "assistant", "content": fallback})
    _save_messages(db, state, messages)
    product, payment_method = _extract_product_and_payment(db, tool_calls_made)
    return fallback, product, payment_method
