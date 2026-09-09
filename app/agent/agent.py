"""
agent.py — Main AI chat loop for the Style Store assistant.

This file runs the full conversation turn:
  1. Loads the customer's message history from the database.
  2. Sends the history + new message to the LLM with available tools.
  3. If the LLM calls a tool (search products, create order, etc.), executes it and feeds the result back.
  4. Repeats until the LLM gives a plain-text reply (no more tool calls).
  5. Saves the updated history and returns the reply + any product card or payment QR to the API.

The system prompt (persona, rules, store knowledge) is imported from prompt.py.
All tools (search, order, validate, etc.) are imported from tools.py.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.agent.prompt import PROMPT_TEMPLATE, PromptRegistry
from app.agent.tools import build_tools
from app.config import get_tenant_context
from app.database.models import ConversationState, Product
from app.providers.llm import get_llm_provider


MAX_TOOL_ITERATIONS = 10  # ordering flow can use up to 4-5 tools in one turn
MAX_HISTORY_MESSAGES = 60  # trim old turns to keep context window manageable


def _load_messages(state: ConversationState) -> list[dict[str, Any]]:
    if state.messages:
        msgs = list(state.messages)
        # Always refresh the system prompt from the registry so activating
        # a new prompt version via the admin API takes effect immediately,
        # even on existing conversations — without a server restart.
        active_prompt = PromptRegistry.get_active_prompt()
        if msgs and msgs[0].get("role") == "system":
            msgs[0]["content"] = active_prompt
        return msgs
    active_prompt = PromptRegistry.get_active_prompt()
    return [{"role": "system", "content": active_prompt}]

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
    # Remove markdown images: ![alt](url) -> remove entirely (frontend shows cards)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", "", text)
    # Remove markdown links: [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # Remove any bare Unsplash / image hosting URLs the LLM leaks into text
    text = re.sub(r"https?://(?:images\.unsplash\.com|unsplash\.com|i\.imgur\.com|cdn\.\S+)\S*", "", text, flags=re.IGNORECASE)
    # Also strip any remaining bare image-extension URLs
    text = re.sub(r"https?://\S+\.(?:png|jpg|jpeg|gif|webp|svg)(?:\?\S*)?", "", text, flags=re.IGNORECASE)
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

    Only two things need fixing:
    1. Assistant tool-call messages must have a content key (null is fine, absent is not).
    2. Dangling assistant tool-call messages with no following tool responses must
       be dropped (happens when a previous request failed after the LLM returned
       tool_calls but before the tools were executed and saved).

    We do NOT trim trailing tool messages — if tool results are present they are
    valid and must be sent so the next LLM call can reason over them.
    """
    # Pass 1: collect tool_call_ids that have a response somewhere in the list
    responded_ids: set[str] = set()
    for msg in messages:
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            responded_ids.add(msg["tool_call_id"])

    # Pass 2: build clean output
    clean: list[dict[str, Any]] = []
    # Track which tool_call_ids we've decided to drop (from dangling blocks)
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
                all_responded = all(tc_id in responded_ids for tc_id in ids_needed)
                if not all_responded:
                    # Dangling — no tool responses for this assistant message.
                    # Drop it and mark its IDs so partial tool messages are also dropped.
                    for tc_id in ids_needed:
                        dropped_ids.add(tc_id)
                    continue
                clean.append({
                    "role": "assistant",
                    "content": msg.get("content"),  # null is valid, absent is not
                    "tool_calls": tool_calls,
                })
            else:
                clean.append({"role": "assistant", "content": msg.get("content", "")})

        elif role == "tool":
            tc_id = msg.get("tool_call_id")
            if not tc_id or tc_id in dropped_ids:
                continue  # drop orphaned or dangling tool message
            clean.append(msg)

        else:
            clean.append(msg)

    return clean



_DIGITAL_PAYMENT_METHODS = {"esewa", "khalti"}  # kept as fallback default


def _extract_product_and_payment(
    db: Session,
    tool_calls_made: list[dict[str, Any]],
    digital_payments: set[str] | None = None,
) -> tuple[Product | None, str | None]:
    """Return (last_product, payment_method_or_None) based on THIS turn's tool calls only.
    History-based persistence is handled via ConversationState.last_product_id in _finalise.
    """
    # Use tenant digital_payments if provided, else fall back to default set
    _digital = digital_payments if digital_payments is not None else _DIGITAL_PAYMENT_METHODS
    product: Product | None = None
    payment_method: str | None = None

    def _is_specific_hit(query: str | None, first_product_name: str) -> bool:
        """Return True if the first result looks like a direct name match for the query.
        Used to decide whether to show a product card from a multi-result search."""
        if not query:
            return False
        # Strip stop-words and check that all significant query words appear in the name
        stop = {"and", "or", "&", "the", "a", "an", "for", "in", "with", "of"}
        q_words = [w.strip(".,;:").lower() for w in query.split()
                   if w.strip(".,;:").lower() not in stop and len(w.strip(".,;:")) >= 2]
        if not q_words:
            return False
        name_lower = first_product_name.lower()
        # Consider it a specific hit if ≥60% of query words appear in the product name
        matches = sum(1 for w in q_words if w in name_lower)
        return matches / len(q_words) >= 0.6

    def _process_call(name: str, arguments: dict, result: dict) -> None:
        nonlocal product, payment_method
        if name == "search_products":
            products_data = result.get("products", [])
            if not products_data:
                return
            first = products_data[0]
            query_arg = arguments.get("query") or ""
            color_arg = arguments.get("color") or ""

            # The LLM sometimes stuffs color into the query string instead of
            # using the separate color param (e.g. query="Firstcry Denim Skirt Beige").
            # Detect this by checking if the top result's color appears in query_arg.
            if not color_arg and first.get("color") and query_arg:
                product_color = first["color"].lower()
                if product_color in query_arg.lower():
                    color_arg = first["color"]  # treat as if color param was used

            if len(products_data) == 1:
                # Single result — always show card
                p = db.get(Product, first["id"])
                if p:
                    product = p
            elif color_arg and _is_specific_hit(query_arg, first.get("name", "")):
                # Multiple results but top result closely matches query name
                # AND a color was specified (explicitly or inferred from query)
                p = db.get(Product, first["id"])
                if p:
                    product = p
            elif not color_arg and len(products_data) <= 3 and _is_specific_hit(query_arg, first.get("name", "")):
                # No color filter but very specific name match with few results
                p = db.get(Product, first["id"])
                if p:
                    product = p
            # else: broad listing — no card
        elif name == "get_product":
            pid = result.get("product_id")
            if pid:
                p = db.get(Product, pid)
                if p:
                    product = p
        elif name in ("check_stock", "get_price_history"):
            pid = result.get("product_id")
            if pid:
                p = db.get(Product, pid)
                if p:
                    product = p
        elif name == "create_order":
            if "order_id" in result:
                raw_pm = result.get("payment_method", "")
                normalised = raw_pm.strip().lower()
                if normalised in _digital:
                    payment_method = normalised
                product = None  # no product card after order confirmation
        elif name == "update_order_payment":
            if "order_id" in result:
                raw_pm = result.get("payment_method", "")
                normalised = raw_pm.strip().lower()
                if normalised in _digital:
                    payment_method = normalised
                else:
                    payment_method = None
                product = None

    # ── Pass 1: current turn tool calls ─────────────────────────────────────
    for call in tool_calls_made:
        _process_call(call["name"], call.get("arguments", {}), call.get("result", {}))

    return product, payment_method


async def handle_chat_message(
    db: Session, conversation_id: str, message: str
) -> tuple[str, Product | None, str | None]:
    """Run one user turn through the agent loop.

    Returns (reply_text, product_or_None, payment_method_or_None).
    - product: last product the agent touched — frontend renders a product card.
    - payment_method: a digital payment method name when an order was just placed
      with digital payment — frontend renders the matching QR code.
    """
    # Resolve tenant config for this request — drives phone validation,
    # payment methods, prompt rendering, and currency.
    tenant = get_tenant_context("default")
    TOOLS, TOOL_SPECS = build_tools(tenant)

    state = db.get(ConversationState, conversation_id)
    if state is None:
        state = ConversationState(
            id=conversation_id,
            messages=[{"role": "system", "content": PromptRegistry.get_active_prompt_for_tenant(tenant)}],
        )
        db.add(state)
        db.commit()

    # last_clean_messages holds the last fully valid state (all tool_calls
    # have matching tool results). We only persist this, never a partial state.
    last_clean_messages = _load_messages(state)
    messages = list(last_clean_messages)  # working copy
    messages.append({"role": "user", "content": message})

    llm = get_llm_provider()
    tool_calls_made: list[dict[str, Any]] = []

    def _finalise(content: str, msgs: list) -> tuple[str, Any, Any]:
        """Save messages, resolve product+payment, update last_product_id, return tuple."""
        _save_messages(db, state, msgs)
        product, payment_method = _extract_product_and_payment(
            db, tool_calls_made,
            digital_payments=set(tenant.digital_payments),
        )

        # ── Card display rule ─────────────────────────────────────────────────
        # Show the product card ONLY when a tool call happened this turn that
        # found a specific product (search, get_product, check_stock).
        # Never show it on text-only turns (name, phone, address, "yes", etc.)
        # so the card doesn't keep reappearing throughout the checkout flow.
        if product is None:
            # Focused tool turn fallback (check_stock / get_product called but
            # product_id came back indirectly — e.g. stock call on known id)
            focused_this_turn = any(
                c["name"] in ("check_stock", "get_product") for c in tool_calls_made
            )
            if focused_this_turn and state.last_product_id:
                product = db.get(Product, state.last_product_id)

        # Text-only turns (name, phone, address, payment, "yes", "show me pic"):
        # do NOT show card — the agent should call get_product explicitly if
        # the user asks to see the image.
        # Exception: if no tool calls but the turn is an explicit image request,
        # the agent should have called get_product. If it didn't, we still
        # suppress the card here to avoid stale cards on every text turn.

        # ── Persist last_product_id ───────────────────────────────────────────
        if product is not None:
            if state.last_product_id != product.id:
                state.last_product_id = product.id
                db.add(state)
                db.commit()
        else:
            # Broad listing — clear last_product_id so it doesn't bleed
            broad_listing = any(
                c["name"] == "search_products"
                and c["result"].get("count", 0) > 1
                and not (
                    c["arguments"].get("color")
                    and _is_specific_hit(
                        c["arguments"].get("query") or "",
                        (c["result"].get("products") or [{}])[0].get("name", ""),
                    )
                )
                for c in tool_calls_made
            )
            if broad_listing and state.last_product_id is not None:
                state.last_product_id = None
                db.add(state)
                db.commit()

        return content, product, payment_method

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            assistant_message = await llm.chat(_sanitise_messages(messages), tools=TOOL_SPECS)
            tool_calls = assistant_message.get("tool_calls")

            if not tool_calls:
                # Plain text reply — the LLM already produced a response with
                # the full system prompt and conversation history. Use it directly.
                # DSPy wraps this for structural tracking and future optimization
                # (BootstrapFewShot), but does NOT replace the reply content.
                raw_content = (assistant_message.get("content") or "").strip()
                content = _strip_markdown(raw_content)

                if not content:
                    content = "Sorry, I couldn't come up with a response — could you rephrase that?"
                messages.append({"role": "assistant", "content": content})
                return _finalise(content, messages)

            # Append assistant tool-call message
            messages.append(assistant_message)

            # Execute every tool and append results
            for call in tool_calls:
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    arguments = {}

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
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result),
                })

            # ── After all tool calls in this iteration ────────────────────────
            # Build confirmation if create_order or update_order_payment succeeded.
            order_confirmations: list[str] = []
            final_payment_method: str | None = None

            for call_rec in tool_calls_made:
                if call_rec["name"] == "create_order":
                    res = call_rec["result"]
                    if "order_id" not in res:
                        continue
                    pm = res.get("payment_method", "")
                    pm_lower = pm.strip().lower()
                    grand_total = res.get("grand_total", 0)
                    currency = res.get("currency", "NPR")
                    order_id = res["order_id"]
                    item_count = res.get("item_count", 1)
                    items_list = res.get("items", [])

                    # Build item lines
                    item_lines = []
                    for it in items_list:
                        name = it.get("product_name", "item")
                        qty  = it.get("quantity", 1)
                        lt   = it.get("line_total", 0)
                        size = it.get("size")
                        sz   = f" size {size}" if size else ""
                        item_lines.append(f"{name}{sz} x{qty} = {lt:,.0f} {currency}")

                    if pm_lower in set(tenant.digital_payments):
                        payment_note = f"The {pm} QR code is displayed in the chat — scan it to complete your payment."
                        final_payment_method = pm_lower
                    else:
                        payment_note = "Please have cash ready upon delivery."

                    summary = ", ".join(item_lines) if item_lines else "your items"
                    order_confirmations.append(
                        f"Order ID: {order_id}. "
                        f"Items: {summary}. "
                        f"Grand total: {grand_total:,.0f} {currency}. "
                        f"Payment: {pm}. {payment_note}"
                    )

                elif call_rec["name"] == "update_order_payment":
                    res = call_rec["result"]
                    if "order_id" not in res:
                        continue
                    pm = res.get("payment_method", "")
                    pm_lower = pm.strip().lower()
                    order_id = res["order_id"]
                    total = res.get("total_price", 0)
                    currency = res.get("currency", "NPR")
                    if pm_lower in set(tenant.digital_payments):
                        payment_note = f"The {pm} QR code is now displayed in the chat — scan it to complete your payment."
                        final_payment_method = pm_lower
                    else:
                        payment_note = "Please have cash ready upon delivery."
                    order_confirmations.append(
                        f"Payment method for Order {order_id} updated to {pm}. "
                        f"Total: {total:,.0f} {currency}. {payment_note}"
                    )

            if order_confirmations:
                body = " ".join(order_confirmations)
                confirmation = f"Your order is confirmed! {body}"
                confirmation = _strip_markdown(confirmation)
                messages.append({"role": "assistant", "content": confirmation})
                return _finalise(confirmation, messages)

            # All tool results are now appended — this is a clean checkpoint.
            # Update last_clean_messages so an exception on the NEXT LLM call
            # doesn't lose this turn's tool results.
            last_clean_messages = list(messages)

        # Exhausted iterations
        fallback = "I wasn't able to finish looking that up — could you try asking again?"
        messages.append({"role": "assistant", "content": fallback})
        return _finalise(fallback, messages)

    except Exception:
        # Something went wrong mid-loop (timeout, API error, etc.).
        # Save only the last clean state so future requests don't get a 400.
        # The user message is included so the conversation doesn't look like
        # we forgot they said something.
        safe = list(last_clean_messages)
        safe.append({"role": "user", "content": message})
        _save_messages(db, state, safe)
        raise  # let chat.py convert this to a 503
