"""
prompt.py — DSPy Signature and Module for the Style Store sales assistant.

WHY DSPY?
  Raw prompt strings (the old approach) are opaque blobs — hard to version,
  test, or improve systematically. DSPy treats prompts as structured programs:
  - ChatSignature declares WHAT the model should do (inputs, outputs, instructions).
  - SalesAgentModule is the executable unit that DSPy can later optimize
    automatically using BootstrapFewShot or MIPROv2 on real conversation examples,
    without manually rewriting prompt text.

HOW IT FITS THE AGENT LOOP:
  agent.py still drives the full tool-calling loop (tool calls, history, DB).
  DSPy is used for the one part that benefits from optimization: the
  system-prompt injection and the final plain-text reply generation.
  Tool-calling turns bypass DSPy and go directly to the underlying LLM via
  the existing LLMProvider.chat() interface (DSPy doesn't yet handle arbitrary
  tool schemas as cleanly as raw API calls).

SYSTEM PROMPT (SYSTEM_PROMPT constant):
  The raw string is kept here too so agent.py can inject it into the
  conversation history for tool-calling turns, which bypass DSPy.
"""
import dspy


# ── Raw system prompt ─────────────────────────────────────────────────────────
# Used directly by agent.py for tool-calling turns (injected as role=system).
# Also used as the `instructions` field in ChatSignature so DSPy and the
# raw-string path stay in sync from one source.

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
  2. Phone number — ask for their phone number. When they give it, call validate_phone. After validation:
     - If VALID: your ONLY response is to ask for their delivery address. Say nothing about the phone being valid or verified. Example: "Thanks! What is your delivery address?"
     - If INVALID: tell them it is not a valid Nepali mobile number and ask them to re-enter it.
  3. Delivery address — ask for their address. When they give it, call validate_address. After validation:
     - If VALID: your ONLY response is to ask for payment method. Say nothing about the address being valid or verified. Example: "Got it! Would you like to pay by eSewa, Khalti, or Cash on Delivery?"
     - If INVALID: tell them the address seems incomplete and ask them to provide area and city.
  4. Payment method — ask for eSewa, Khalti, or Cash on Delivery.
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


# ── DSPy Signature ────────────────────────────────────────────────────────────
# A Signature declares the input/output contract for one "step" of reasoning.
# DSPy uses this to build and later optimize the prompt automatically.
#
# IMPORTANT: This signature is for the final plain-text reply step only
# (no tool calls). The full tool-calling loop in agent.py bypasses DSPy and
# calls the underlying LLM provider directly — tool calling requires
# exact JSON schemas that DSPy does not yet handle end-to-end.

class ChatSignature(dspy.Signature):
    """Style Store sales assistant. Respond to the customer based on the
    conversation history provided. Be concise, friendly, and accurate.
    Never use Markdown. Never invent product details."""

    conversation_history: str = dspy.InputField(
        desc="Full conversation so far as a JSON-serialized list of role/content dicts"
    )
    user_message: str = dspy.InputField(
        desc="The latest message from the customer"
    )
    tool_results: str = dspy.InputField(
        desc="JSON-serialized tool call results from this turn, or empty string if none"
    )
    reply: str = dspy.OutputField(
        desc="Plain-text reply to the customer. No Markdown, no URLs, no bullet points."
    )


# ── DSPy Module ───────────────────────────────────────────────────────────────
# A Module wraps one or more Predict/ChainOfThought steps.
# This is the unit DSPy can optimize: call dspy.BootstrapFewShot(metric, ...)
# on a SalesAgentModule instance and it will automatically improve the prompts
# using examples from real conversations.

class SalesAgentModule(dspy.Module):
    """
    DSPy module for the Style Store sales assistant's plain-text reply step.

    Usage:
        module = SalesAgentModule()
        result = module(
            conversation_history=json.dumps(messages),
            user_message=user_message,
            tool_results=json.dumps(tool_results),
        )
        reply = result.reply

    To optimize with real examples later:
        from dspy.teleprompt import BootstrapFewShot
        optimized = BootstrapFewShot(metric=your_metric).compile(
            SalesAgentModule(), trainset=examples
        )
    """

    def __init__(self):
        super().__init__()
        # Predict is the standard DSPy predictor — one LLM call per forward().
        # Switch to dspy.ChainOfThought(ChatSignature) for step-by-step reasoning.
        self.predict = dspy.Predict(ChatSignature)

    def forward(
        self,
        conversation_history: str,
        user_message: str,
        tool_results: str = "",
    ) -> dspy.Prediction:
        return self.predict(
            conversation_history=conversation_history,
            user_message=user_message,
            tool_results=tool_results,
        )


# ── Module singleton ──────────────────────────────────────────────────────────
# One instance reused across all requests (DSPy modules are stateless between
# calls; state lives in the conversation history passed as input).
sales_agent_module = SalesAgentModule()


# ── Prompt Registry ───────────────────────────────────────────────────────────
# Loads the active prompt version from the database at runtime.
# Falls back to the hardcoded SYSTEM_PROMPT if the DB is empty or unavailable.
# agent.py calls get_active_prompt() instead of using SYSTEM_PROMPT directly.

class PromptRegistry:
    """
    Runtime accessor for the versioned system prompt.

    Usage:
        text = PromptRegistry.get_active_prompt()   # returns current active text

    The agent calls this once per conversation turn. If the DB has an active
    version, that text is used. If not (fresh install, empty table), the
    hardcoded SYSTEM_PROMPT above is used as the default.

    To promote a new prompt version:
        POST /api/prompts            — create a new version
        POST /api/prompts/{id}/activate — make it active
    The next request will automatically pick up the new text.
    """

    @staticmethod
    def get_active_prompt() -> str:
        """Return the text of the currently active prompt version from DB.
        Falls back to the hardcoded SYSTEM_PROMPT if no active version exists."""
        try:
            from app.database.database import SessionLocal
            from app.database.models import PromptVersion
            db = SessionLocal()
            try:
                row = (
                    db.query(PromptVersion)
                    .filter(PromptVersion.is_active == 1)
                    .order_by(PromptVersion.version.desc())
                    .first()
                )
                if row:
                    return row.prompt_text
            finally:
                db.close()
        except Exception:
            pass   # DB unavailable — fall back to hardcoded
        return SYSTEM_PROMPT

    @staticmethod
    def seed_initial(db=None) -> None:
        """
        Insert the hardcoded SYSTEM_PROMPT as version 1 if the table is empty.
        Called once at application startup (main.py).
        """
        from app.database.database import SessionLocal
        from app.database.models import PromptVersion
        close = db is None
        if db is None:
            db = SessionLocal()
        try:
            if db.query(PromptVersion).count() == 0:
                db.add(PromptVersion(
                    version=1,
                    label="v1-initial",
                    prompt_text=SYSTEM_PROMPT,
                    notes="Initial system prompt seeded automatically at first startup.",
                    is_active=1,
                    created_by="system",
                ))
                db.commit()
        except Exception:
            db.rollback()
        finally:
            if close:
                db.close()

    @staticmethod
    def create_version(
        prompt_text: str,
        label: str = "",
        notes: str = "",
        created_by: str = "admin",
        activate: bool = False,
        db=None,
    ) -> "PromptVersion":
        """
        Save a new prompt version. Optionally make it active immediately.

        Args:
            prompt_text: Full system prompt string.
            label:       Short name e.g. "v3-dspy-optimized".
            notes:       Change description.
            created_by:  Who/what created it ("admin", "dspy-bootstrap", etc.)
            activate:    If True, deactivate all others and activate this one.
            db:          SQLAlchemy session (created internally if not provided).

        Returns:
            The new PromptVersion ORM object.
        """
        from app.database.database import SessionLocal
        from app.database.models import PromptVersion
        close = db is None
        if db is None:
            db = SessionLocal()
        try:
            last = (
                db.query(PromptVersion)
                .order_by(PromptVersion.version.desc())
                .first()
            )
            next_version = (last.version + 1) if last else 1
            if not label:
                label = f"v{next_version}"

            new_pv = PromptVersion(
                version=next_version,
                label=label,
                prompt_text=prompt_text,
                notes=notes,
                is_active=0,
                created_by=created_by,
            )
            db.add(new_pv)
            db.flush()

            if activate:
                db.query(PromptVersion).filter(
                    PromptVersion.id != new_pv.id
                ).update({"is_active": 0})
                new_pv.is_active = 1

            db.commit()
            db.refresh(new_pv)
            return new_pv
        except Exception:
            db.rollback()
            raise
        finally:
            if close:
                db.close()

    @staticmethod
    def activate_version(version_id: int, db=None) -> "PromptVersion":
        """
        Set a specific version as active (deactivates all others).

        Args:
            version_id: Primary key of the PromptVersion to activate.
            db:         SQLAlchemy session.

        Returns:
            The activated PromptVersion row.

        Raises:
            ValueError: If version_id does not exist.
        """
        from app.database.database import SessionLocal
        from app.database.models import PromptVersion
        close = db is None
        if db is None:
            db = SessionLocal()
        try:
            row = db.get(PromptVersion, version_id)
            if row is None:
                raise ValueError(f"PromptVersion id={version_id} not found.")
            db.query(PromptVersion).update({"is_active": 0})
            row.is_active = 1
            db.commit()
            db.refresh(row)
            return row
        except Exception:
            db.rollback()
            raise
        finally:
            if close:
                db.close()
