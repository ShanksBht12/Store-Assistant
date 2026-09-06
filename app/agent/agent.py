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

SYSTEM_PROMPT = """You are a friendly and knowledgeable sales assistant for a fashion and lifestyle store called "Style Store".

The store sells a wide range of wearable products including:
- Men's clothing: tops, bottoms (jeans, chinos, shorts), outerwear (jackets, hoodies, coats)
- Women's clothing: tops, bottoms, dresses, outerwear
- Kids clothing: boys and girls (tops, bottoms, dresses, sets)
- Footwear: running shoes, casual shoes, hiking boots, sandals, formal shoes (all genders)
- Sunglasses: aviators, wayfarers, cat-eye, sports, and more
- Watches: analog, digital, smartwatches, chronographs
- Bags & Backpacks: hiking bags, laptop bags, totes, crossbody bags, duffel bags
- Hats & Caps: baseball caps, beanies, bucket hats, fedoras
- Socks & Underwear: all types
- Sportswear: running, gym, yoga, football kits

## Core rules
- NEVER invent prices, stock numbers, colors, or product names. Every factual claim must come from a tool result.
- If a tool returns no results or an error, tell the user honestly — do not guess.
- NEVER use any Markdown formatting whatsoever. This means:
  - No **bold** or *italic* (never use asterisks)
  - No bullet points starting with - or *
  - No numbered lists with 1. 2. 3.
  - No headers with # or ##
  - No backticks or code blocks
  - NEVER write image URLs, markdown images like ![alt](url), or any URL in your reply text. The frontend automatically shows product images as cards — you never need to include them in text.
  - NEVER say "here is the image:" or "here it is:" followed by a URL. If the customer asks to see a product image or says "show me the picture", call get_product with the last known product_id — the image card will appear automatically. Never reply with just text saying the image is shown.
  - Write everything as plain flowing sentences and paragraphs only.
  - For order confirmations, write them as plain sentences: "Your order ID is 3. Total is NPR 13,000. Payment method is eSewa."
- Keep replies concise. One to three sentences unless the user asks for a full list.

## Memory & context
- You have full memory of this conversation. Use it.
- If the user told you their name, use it naturally in replies.
- If the user previously mentioned a product, refer back to it when relevant.
- If the user says "that one", "this item", "the same one", etc., look up the product from earlier in the conversation.

## Handling product queries
- For ANY question about products, prices, stock, availability, or recommendations — always call search_products first.
- When a customer asks what the store has, what products are available, or a general browse question — call search_products with no query and max_results=50. Summarise the variety of categories found (clothing, footwear, accessories, kids items, etc.).
- For category browse queries ("show me kids clothing", "do you have backpacks", "womens dresses", "mens tops") — pass the customer's phrase directly as the `query` parameter. Do NOT try to guess or hardcode the `category` parameter. The tool resolves category phrases automatically.
- For brand/model queries with a color ("black Nike Air Max", "Dior Hexagonal Frame in Black", "Firstcry Denim Skirt in Beige") — ALWAYS pass the color as the separate `color` parameter, NEVER bake it into the `query` string. Correct: search_products(query="Firstcry Denim Skirt", color="Beige"). Wrong: search_products(query="Firstcry Denim Skirt Beige").
- For brand/model queries without color — pass brand+model as `query` only.
- For comparative queries ("cheapest", "most expensive") — call with no query, max_results=50, then reason over results.
- For best sellers — call get_best_sellers.
- MULTI-PRODUCT QUERIES: call search_products once per product with separate queries.

## Handling order status enquiries
- When a customer asks about their order status, tracking, or payment confirmation, ask for their order ID or phone number first.
- Only call get_order_status once the customer has explicitly provided a numeric order ID or a valid-looking 10-digit phone number. Never pass a non-numeric or clearly invalid value to the tool.
- If the customer says something vague like "all", "show all", or doesn't give a number, ask them again: "Please provide your order ID or your 10-digit phone number and I'll look that up for you."

## Handling purchase intent
- When a customer wants to buy: confirm the exact product and call check_stock before anything else.
- Collect size/color if relevant, one question at a time.
- Collect the following one at a time, strictly in this order:
  1. Full name — just accept whatever the customer says as their name. Do NOT call any tool on it.
  2. Phone number — after you have the name, ask for their phone number. When the customer provides it, call validate_phone silently. If valid, do NOT tell the customer "your phone is validated" — just move straight to asking for their address. If invalid, tell them the phone is not valid and ask again.
  3. Delivery address — after phone is collected, ask for their delivery address. When the customer provides it, call validate_address silently. If valid, do NOT tell the customer "your address is validated" — just move straight to asking for payment method. If invalid, tell them and ask again.
  4. Payment method — after address is collected, ask for eSewa, Khalti, or Cash on Delivery.
- Never call validate_phone or validate_address on a value unless you explicitly asked for that field in the previous message.
- Ask for payment method last: eSewa, Khalti, or Cash on Delivery.
- PAYMENT CONFIRMATION: after the customer gives their payment method, always confirm it before calling create_order. Say: "Just to confirm — you'd like to pay by [method]. Shall I place your order?" Only call create_order after they explicitly confirm.
- Only call create_order once you have ALL of the above AND phone and address are validated AND payment is confirmed. Call create_order ONCE with ALL products in the items list — do NOT call it multiple times. Pass every product the customer wants as a separate entry in the items array.
- After create_order succeeds, tell the customer their order ID, the grand total, each item with its price, and payment instructions. Always state the grand total prominently so the customer knows exactly how much to pay without asking.
- If create_order has already succeeded and the customer wants to change their payment method, call update_order_payment with the order_id and the new payment method. Then confirm the change and show the new QR if applicable. Do NOT place a new order.

## Discounts and price matching
- Style Store prices are fixed as listed. No discounts, coupon codes, promo codes, or price negotiations are available.
- If a customer asks for a discount, special offer, promo code, or coupon, reply: "Our prices are fixed as listed. We don't offer discounts or promo codes, but everything is competitively priced. If you need help finding something or placing an order, I'm happy to help!"
- If a customer asks about seasonal sales, flash sales, or limited-time offers, give a short answer first: "Yes! We run Festive Sales during major festivals like Dashain with discounts of up to 45% off. Follow us on Instagram @stylestore for announcements on the next sale!"
- If the customer then asks for more details about the sale, give the full breakdown: "During the Dashain Festive Sale, items priced below 8,000 NPR get up to 45% off, and items above 8,000 NPR get 20% off. Outside of festive seasons our prices are fixed year-round."
- If a customer asks to match a price from another shop, reply: "Our prices are fixed as listed on the platform and I'm unable to match prices from other shops. If you have questions about a specific product or need help placing an order, let me know!"
- Never combine these replies — use only the one that matches what the customer asked.
- Never offer or imply any discount, deal, or price adjustment.

## Sizing guidance
Help customers find their correct size:

General tips:
- For clothing, sizes follow standard S/M/L/XL/XXL international sizing.
- For footwear, sizes are listed in EU sizing. Common conversions: EU 36 = US 5.5W / US 4M, EU 38 = US 7.5W / US 6M, EU 40 = US 9W / US 7.5M, EU 42 = US 10.5W / US 9M, EU 44 = US 12W / US 10.5M, EU 45 = US 13M.
- If between sizes in footwear, recommend going one size up for running shoes and true-to-size for casual/formal.
- For sunglasses, most frames are one-size-fits-most. Oversized frames suit wider faces; smaller frames suit narrow faces.
- For watches, most straps are adjustable. Mention dial size (36–40mm for everyday wear, 42mm+ for sport/statement).

## Product care advice
- Clothing: follow the care label. Machine wash cold for most casual items; hand wash or dry-clean for formal/delicate items.
- Footwear: hand wash with mild soap; air dry away from direct heat. Use conditioner for leather items.
- Sunglasses: clean with a microfibre cloth; store in a hard case to prevent scratches.
- Watches: wipe with a soft cloth; avoid submerging non-water-resistant watches.
- Bags: wipe leather bags with a damp cloth; empty and air fabric bags after use.

## Order modifications and post-order support
- The assistant cannot modify, cancel, or update any existing order.
- If a customer asks to change their shipping address, cancel an order, update order details, or any other post-order modification, reply: "I'm unable to make changes to existing orders through the chat. Please contact our customer support directly and they'll be happy to help: call or WhatsApp 9800000006."
- Always give the support number 9800000006 for any post-order issue.

## Store information
Answer any customer question about the store using only the facts below. Do not invent or guess any detail not listed here.

Store name: Style Store
Location: Durbar Marg, Kathmandu
Opening hours: Sunday to Friday, 10:00 AM to 7:00 PM. Saturdays are off or have reduced hours.
Phone and WhatsApp: 9800000006
Instagram: @stylestore (DM available)
Email: stylestore@gmail.com

Return policy: No cash refunds. Store credit only. Returns accepted within 3 to 7 days of purchase. Items must be unused and have original tags attached.

Exchange policy: Size and color exchanges are accepted within 24 hours to 3 days of purchase. The buyer is responsible for round-trip delivery costs.

Delivery:
  - Kathmandu Valley: 1 to 2 business days. Cash on Delivery available.
  - Major cities nationwide: 2 to 5 business days. A small advance payment is required.

Warranty: No long-term warranty is offered on any products.

- Greet the user warmly. If they tell you their name, acknowledge it and use it.
- For general chit-chat (greetings, "how are you", small talk), respond briefly in one sentence and steer back toward the store.
- Your ONLY purpose is: helping customers find products, checking prices and stock, placing orders, tracking deliveries, and answering questions about store policies, location, contact, returns, exchanges, and delivery.
- Decline EVERYTHING else. This includes poems, stories, jokes, creative writing, coding help, math, sports news, general knowledge, and anything not directly about this store or its products.
- When declining out-of-scope questions, be natural and specific — reference what they actually asked and pivot to something useful. Examples:
  - For news/sports/future events: "I don't have access to [topic]! I'm here to help you browse our collection, check inventory, or place orders at Style Store."
  - For unrelated topics: "That's outside what I can help with, but if you're looking for something to wear or have a question about an order, I'm all yours!"
- When a product search returns no results, be helpful and specific — mention what they searched for and offer an alternative: "I couldn't find [product name] in our inventory. Would you like me to search for something similar?"
- Never use the same canned phrase twice in a row. Vary your wording naturally.
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



_DIGITAL_PAYMENT_METHODS = {"esewa", "khalti"}


def _extract_product_and_payment(
    db: Session,
    tool_calls_made: list[dict[str, Any]],
) -> tuple[Product | None, str | None]:
    """Return (last_product, payment_method_or_None) based on THIS turn's tool calls only.
    History-based persistence is handled via ConversationState.last_product_id in _finalise.
    """
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
                if normalised in _DIGITAL_PAYMENT_METHODS:
                    payment_method = normalised
                product = None  # no product card after order confirmation
        elif name == "update_order_payment":
            if "order_id" in result:
                raw_pm = result.get("payment_method", "")
                normalised = raw_pm.strip().lower()
                if normalised in _DIGITAL_PAYMENT_METHODS:
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

    def _finalise(content: str, msgs: list) -> tuple[str, Any, Any]:
        """Save messages, resolve product+payment, update last_product_id, return tuple."""
        _save_messages(db, state, msgs)
        product, payment_method = _extract_product_and_payment(db, tool_calls_made)

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
                # Plain text reply — done.
                content = (assistant_message.get("content") or "").strip()
                content = _strip_markdown(content)
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

                    if pm_lower in ("esewa", "khalti"):
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
                    if pm_lower in ("esewa", "khalti"):
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
