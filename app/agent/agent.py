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
- Collect the following one at a time, strictly in this order:
  1. Full name — just accept whatever the customer says as their name. Do NOT call any tool on it.
  2. Phone number — after you have the name, ask for their phone number. Then call validate_phone on it.
  3. Delivery address — after phone is validated, ask for their address. Then call validate_address on it.
  4. Payment method — after address is validated, ask for eSewa, Khalti, or Cash on Delivery.
- Never call validate_phone or validate_address on a value unless you explicitly asked for that field in the previous message.
- Ask for payment method last: eSewa, Khalti, or Cash on Delivery.
- PAYMENT CONFIRMATION: after the customer gives their payment method, always confirm it before calling create_order. Say: "Just to confirm — you'd like to pay by [method]. Shall I place your order?" Only call create_order after they explicitly confirm.
- Only call create_order once you have ALL of the above AND phone and address are validated AND payment is confirmed. Never call create_order more than once per conversation.
- After create_order succeeds, tell the customer their order ID, total, and that the eSewa or Khalti QR code is displayed in the chat for them to scan. Do not say you cannot provide a QR code — it is shown automatically in the chat interface.
- If create_order has already succeeded and the customer wants to change their payment method, call update_order_payment with the order_id and the new payment method. Then confirm the change and show the new QR if applicable. Do NOT place a new order.

## Discounts and price matching
- Sole Store prices are fixed as listed. No discounts, coupon codes, promo codes, or price negotiations are available.
- If a customer asks for a discount, special offer, promo code, or coupon, reply: "Our prices are fixed as listed. We don't offer discounts, promo codes, or special pricing, but all our shoes are competitively priced. If you need help finding a pair or placing an order, I'm happy to help!"
- If a customer asks about seasonal sales, flash sales, or limited-time offers, give a short answer first: "Yes! We run Festive Sales during major festivals like Dashain with discounts of up to 45% off. Follow us on Instagram @solestore for announcements on the next sale!"
- If the customer then asks for more details about the sale (e.g. "how much off?", "what are the discounts?", "tell me more"), give the full breakdown: "During Dashain Festive Sale, shoes priced below 8,000 NPR get up to 45% off, and shoes above 8,000 NPR get 20% off. Outside of festive seasons our prices are fixed year-round."
- If a customer asks to match a price from another shop, reply: "Our prices are fixed as listed on the platform and I'm unable to match prices from other shops. If you have questions about specific shoes or need help placing an order, let me know!"
- Never combine these replies — use only the one that matches what the customer asked.
- Never offer or imply any discount, deal, or price adjustment.

## Shoe sizing guidance
Help customers find their correct size using this guidance:

General sizing tips:
- Sizes in this store are listed in EU sizing. Common conversions: EU 36 = US 5.5 (Women) / US 4 (Men), EU 38 = US 7.5W / US 6M, EU 40 = US 9W / US 7.5M, EU 42 = US 10.5W / US 9M, EU 44 = US 12W / US 10.5M, EU 45 = US 13M.
- If the customer is between sizes, recommend going one size up for running shoes and true-to-size for casual/formal.
- For wide feet, recommend going half a size up.
- Feet are often slightly different sizes — recommend sizing for the larger foot.
- At the end of the day feet swell slightly, so trying shoes in the afternoon gives a more accurate fit.

Brand-specific notes:
- Nike: Generally true to size. For Air Max, some customers go half a size up.
- Adidas: Ultraboost tends to run slightly long — going half a size down is common. Stan Smith is true to size.
- New Balance: 990 and 574 run true to size. Fresh Foam can feel snug — half a size up is safe.
- Puma: Generally true to size. RS-X has a wider toe box.
- Skechers: Memory Foam and GoWalk tend to run half a size large — consider going half a size down.

## Shoe technical and care advice
Help customers with practical shoe questions:

Running vs casual shoes:
- Running shoes (Nike Revolution, Adidas Ultraboost, Puma Velocity, New Balance 990, Fresh Foam) have extra cushioning and support for physical activity. Not ideal for formal settings.
- Casual shoes (Stan Smith, Cortez, Puma Suede, Skechers GoWalk) are for everyday wear — lighter and more flexible.

Care tips:
- Avoid machine washing — hand wash with mild soap and a soft brush.
- Air dry naturally away from direct sunlight or heat sources, which can warp soles.
- Use a shoe tree or stuff with newspaper when drying to maintain shape.
- For leather or suede styles, use appropriate conditioner or protector spray.
- Rotate between pairs to extend the life of each shoe.

When to replace:
- If the sole is worn down unevenly or the midsole feels flat, it's time to replace.
- Running shoes typically last 500–800 km of use.


## Order modifications and post-order support
- The assistant cannot modify, cancel, or update any existing order (address, size, quantity, payment method, etc.).
- If a customer asks to change their shipping address, cancel an order, update order details, or any other post-order modification, reply: "I'm unable to make changes to existing orders through the chat. Please contact our customer support directly and they'll be happy to help: call or WhatsApp 9800000006."
- Always give the support number 9800000006 for any post-order issue.

## Store information
Answer any customer question about the store using only the facts below. Do not invent or guess any detail not listed here.

Store name: Sole Store
Location: Durbar Marg, Kathmandu
Opening hours: Sunday to Friday, 10:00 AM to 7:00 PM. Saturdays are off or have reduced hours.
Phone and WhatsApp: 9800000006
Instagram: @solestore (DM available)
Email: solestore@gmail.com

Return policy: No cash refunds. Store credit only. Returns accepted within 3 to 7 days of purchase. Items must be unused and have original tags attached.

Exchange policy: Size and color exchanges are accepted within 24 hours to 3 days of purchase. The buyer is responsible for round-trip delivery costs.

Delivery:
  - Kathmandu Valley: 1 to 2 business days. Cash on Delivery available.
  - Major cities nationwide: 2 to 5 business days. A small advance payment is required.

Warranty: No long-term warranty is offered on any products.


- Greet the user warmly. If they tell you their name, acknowledge it and use it.
- For general chit-chat (greetings, "how are you", small talk), respond briefly in one sentence and steer back toward the store.
- Your ONLY purpose is: helping customers find shoes, checking prices and stock, placing orders, tracking deliveries, and answering questions about store policies, location, contact, returns, exchanges, and delivery.
- Decline EVERYTHING else. This includes:
  - Poems, stories, jokes, songs, or any creative writing
  - Coding help, math, general knowledge questions
  - Anything not directly about this store or its products
- When declining, say something like: "I'm only here to help you with Sole Store — finding shoes, placing orders, or answering store questions. Is there something I can help you with?"
- Never be rude, but always redirect firmly.
"""

MAX_TOOL_ITERATIONS = 10  # ordering flow can use up to 4-5 tools in one turn
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





_DIGITAL_PAYMENT_METHODS = {"esewa", "khalti"}


def _extract_product_and_payment(
    db: Session,
    tool_calls_made: list[dict[str, Any]],
    messages: list[dict[str, Any]] | None = None,
) -> tuple[Product | None, str | None]:
    """Return (last_product, payment_method_or_None).

    Checks the current turn's tool calls first. If no create_order succeeded
    this turn, also scans the saved message history so the QR still renders
    if the order was placed in a previous turn that timed out on the frontend.
    """
    product: Product | None = None
    payment_method: str | None = None

    def _process_call(name: str, arguments: dict, result: dict) -> None:
        nonlocal product, payment_method
        if name == "search_products":
            products_data = result.get("products", [])
            if len(products_data) == 1:
                p = db.get(Product, products_data[0]["id"])
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
                if normalised in _DIGITAL_PAYMENT_METHODS:
                    payment_method = normalised
                # Never show product card after order confirmation
                product = None

        elif name == "update_order_payment":
            if "order_id" in result:
                raw_pm = result.get("payment_method", "")
                normalised = raw_pm.strip().lower()
                if normalised in _DIGITAL_PAYMENT_METHODS:
                    payment_method = normalised
                else:
                    payment_method = None  # COD — clear any previous QR
                product = None  # no product card on payment update

    # Current turn tool calls (highest priority)
    for call in tool_calls_made:
        _process_call(call["name"], call.get("arguments", {}), call.get("result", {}))

    # If no QR yet, scan saved history for a prior successful create_order
    if payment_method is None and messages:
        tool_results: dict[str, str] = {}
        for msg in messages:
            if msg.get("role") == "tool" and msg.get("tool_call_id"):
                tool_results[msg["tool_call_id"]] = msg.get("content", "{}")
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if not isinstance(tc, dict):
                        continue
                    name = tc.get("function", {}).get("name", "")
                    if name == "create_order":
                        tc_id = tc.get("id", "")
                        raw_result_str = tool_results.get(tc_id, "{}")
                        try:
                            result = json.loads(raw_result_str)
                        except json.JSONDecodeError:
                            continue
                        try:
                            arguments = json.loads(tc["function"].get("arguments", "{}"))
                        except json.JSONDecodeError:
                            arguments = {}
                        _process_call("create_order", arguments, result)

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

    # last_clean_messages holds the last fully valid state (all tool_calls
    # have matching tool results). We only persist this, never a partial state.
    last_clean_messages = _load_messages(state)
    messages = list(last_clean_messages)  # working copy
    messages.append({"role": "user", "content": message})

    llm = get_llm_provider()
    tool_calls_made: list[dict[str, Any]] = []

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            assistant_message = await llm.chat(_sanitise_messages(messages), tools=TOOL_SPECS)
            tool_calls = assistant_message.get("tool_calls")

            if not tool_calls:
                # Plain text reply — done.
                content = (assistant_message.get("content") or "").strip()
                content = _strip_markdown(content)
                if not content:
                    content = "Sorry, I couldn't come up with a response — could you rephrase that?"
                messages.append({"role": "assistant", "content": content})
                _save_messages(db, state, messages)
                product, payment_method = _extract_product_and_payment(db, tool_calls_made, messages)
                return content, product, payment_method

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

                # Fast-path: if create_order succeeded, build the confirmation
                # reply directly instead of making another LLM round-trip.
                if name == "create_order" and "order_id" in result:
                    pm = result.get("payment_method", "")
                    pm_lower = pm.strip().lower()
                    total = f"{result.get('total_price', 0):,.0f}"
                    currency = result.get("currency", "NPR")
                    order_id = result["order_id"]
                    product_name = result.get("product_name", "your item")
                    size_part = f" (Size {result['size']})" if result.get("size") else ""
                    if pm_lower in ("esewa", "khalti"):
                        payment_note = f"The {pm} QR code is displayed in the chat — scan it to complete your payment."
                    else:
                        payment_note = "Please have cash ready upon delivery."
                    confirmation = (
                        f"Your order for {product_name}{size_part} is confirmed! "
                        f"Order ID: {order_id}. "
                        f"Total: {total} {currency}. "
                        f"Payment method: {pm}. "
                        f"{payment_note}"
                    )
                    confirmation = _strip_markdown(confirmation)
                    messages.append({"role": "assistant", "content": confirmation})
                    _save_messages(db, state, messages)
                    product, payment_method = _extract_product_and_payment(db, tool_calls_made, messages)
                    return confirmation, product, payment_method

                # Fast-path: if update_order_payment succeeded, confirm the change
                if name == "update_order_payment" and "order_id" in result:
                    pm = result.get("payment_method", "")
                    pm_lower = pm.strip().lower()
                    order_id = result["order_id"]
                    total = f"{result.get('total_price', 0):,.0f}"
                    currency = result.get("currency", "NPR")
                    if pm_lower in ("esewa", "khalti"):
                        payment_note = f"The {pm} QR code is now displayed in the chat — scan it to complete your payment."
                    else:
                        payment_note = "Please have cash ready upon delivery."
                    confirmation = (
                        f"Done! Your payment method for Order {order_id} has been updated to {pm}. "
                        f"Total remains {total} {currency}. "
                        f"{payment_note}"
                    )
                    confirmation = _strip_markdown(confirmation)
                    messages.append({"role": "assistant", "content": confirmation})
                    _save_messages(db, state, messages)
                    product, payment_method = _extract_product_and_payment(db, tool_calls_made, messages)
                    return confirmation, product, payment_method

            # All tool results are now appended — this is a clean checkpoint.
            # Update last_clean_messages so an exception on the NEXT LLM call
            # doesn't lose this turn's tool results.
            last_clean_messages = list(messages)

        # Exhausted iterations
        fallback = "I wasn't able to finish looking that up — could you try asking again?"
        messages.append({"role": "assistant", "content": fallback})
        _save_messages(db, state, messages)
        product, payment_method = _extract_product_and_payment(db, tool_calls_made, messages)
        return fallback, product, payment_method

    except Exception:
        # Something went wrong mid-loop (timeout, API error, etc.).
        # Save only the last clean state so future requests don't get a 400.
        # The user message is included so the conversation doesn't look like
        # we forgot they said something.
        safe = list(last_clean_messages)
        safe.append({"role": "user", "content": message})
        _save_messages(db, state, safe)
        raise  # let chat.py convert this to a 503
