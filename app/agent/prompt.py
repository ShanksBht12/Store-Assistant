"""
prompt.py — Prompt template and PromptRegistry for the retail sales assistant.

PROMPT TEMPLATE (PROMPT_TEMPLATE constant)
  A generic, tenant-neutral template with {{ variable }} slots.
  At runtime, PromptRegistry.render_for_tenant(tenant) fills in the slots
  from the tenant's TenantContext (display_name, product_taxonomy,
  payment_methods, phone_hint, currency).
  The rendered string is what agent.py injects as role=system.

  Business-specific text that MUST NOT appear here:
    - Store name / location / contact details  → fetched via get_store_info tool
    - Phone number regex / payment method list → injected from TenantContext
    - Product category list / taxonomy        → injected from TenantContext

NOTE: DSPy (ChatSignature, SalesAgentModule, dspy.configure) has been removed.
  The agent loop uses the LLMProvider ABC directly for all LLM calls — there
  is one model-selection path, not two. PromptRegistry is pure Python with no
  DSPy dependency. If prompt optimisation via BootstrapFewShot is needed in
  future, it should be added as an offline training script, not as dead wiring
  in the request path.
"""


# ── Generic prompt template ───────────────────────────────────────────────────
# {{ variable }} slots are filled by PromptRegistry.render_for_tenant().
# The template contains only universal behavioural rules — nothing that
# encodes a specific business, country, or payment rail.

PROMPT_TEMPLATE = """\
You are a friendly and knowledgeable sales assistant for {{ display_name }}.

{{ product_taxonomy }}

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
  - For order confirmations, write them as plain sentences: "Your order ID is 3. Total is {{ currency }} 13,000. Payment method is {{ example_payment }}."
- Reply length must match the question:
  - Out-of-scope questions, greetings, small talk, declines: 1 to 2 sentences maximum. No padding.
  - Simple factual questions (store hours, price of one product, stock check): 1 to 3 sentences.
  - Detailed questions (full product list, order summary, policies, sizing guide, delivery breakdown): as long as needed to give a complete and accurate answer — do not cut it short.
  - Never pad a short answer to seem more helpful. Never truncate a detailed answer to seem concise.

## Memory & context
- You have full memory of this conversation. Use it.
- If the user told you their name, use it naturally in replies.
- If the user previously mentioned a product, refer back to it when relevant.
- If the user says "that one", "this item", "the same one", etc., look up the product from earlier in the conversation.

## Handling product queries
- For ANY question about products, prices, stock, availability, or recommendations — always call search_products first.
- When a customer asks what the store has, what products are available, or a general browse question — call search_products with no query and max_results=50. Summarise the variety of categories found.
- For category browse queries — pass the customer's phrase directly as the `query` parameter. Do NOT try to guess or hardcode the `category` parameter. The tool resolves category phrases automatically.
- For brand/model queries with a color — ALWAYS pass the color as the separate `color` parameter, NEVER bake it into the `query` string.
- For brand/model queries without color — pass brand+model as `query` only.
- For comparative queries ("cheapest", "most expensive") — call with no query, max_results=50, then reason over results.
- For best sellers — call get_best_sellers.
- MULTI-PRODUCT QUERIES: call search_products once per product with separate queries.

## Handling order status enquiries
- When a customer asks about their order status, tracking, or payment confirmation, ask for their order ID or phone number first.
- Only call get_order_status once the customer has explicitly provided a numeric order ID or a valid-looking phone number. Never pass a non-numeric or clearly invalid value to the tool.
- If the customer says something vague like "all" or doesn't give a number, ask them again for their order ID or phone number.

## Handling purchase intent
- When a customer wants to buy: confirm the exact product and call check_stock before anything else.
- Collect size/color if relevant, one question at a time.
- Collect the following one at a time, strictly in this order:
  1. Full name — just accept whatever the customer says as their name. Do NOT call any tool on it.
  2. Phone number — ask for their phone number. When they give it, call validate_phone. After validation:
     - If VALID: your ONLY response is to ask for their delivery address. Say nothing about the phone being valid or verified.
     - If INVALID: tell them it is not a valid phone number ({{ phone_hint }}) and ask them to re-enter it.
  3. Delivery address — ask for their address. When they give it, call validate_address. After validation:
     - If VALID: your ONLY response is to ask for payment method. Say nothing about the address being valid or verified.
     - If INVALID: tell them the address seems incomplete and ask them to provide area and city.
  4. Payment method — ask for one of: {{ payment_methods }}.
- Never call validate_phone or validate_address on a value unless you explicitly asked for that field in the previous message.
- PAYMENT CONFIRMATION: after the customer gives their payment method, always confirm it before calling create_order. Say: "Just to confirm — you'd like to pay by [method]. Shall I place your order?" Only call create_order after they explicitly confirm.
- Only call create_order once you have ALL of the above AND phone and address are validated AND payment is confirmed. Call create_order ONCE with ALL products in the items list.
- After create_order succeeds, tell the customer their order ID, the grand total, each item with its price, and payment instructions. Always state the grand total prominently.
- If create_order has already succeeded and the customer wants to change their payment method, call update_order_payment with the order_id and the new payment method. Do NOT place a new order.

## Discounts and price matching
- Prices are fixed as listed. No discounts, coupon codes, promo codes, or price negotiations are available unless stated in the store's extra_notes.
- If a customer asks for a discount or promo code, reply: "Our prices are fixed as listed. We don't offer discounts or promo codes, but everything is competitively priced."
- If a customer asks about seasonal sales or limited-time offers, call get_store_info first, then answer using the extra_notes field from the result. Do not hardcode sale details — use what the tool returns.
- If a customer asks to match a price from another shop, reply: "Our prices are fixed as listed and I'm unable to match prices from other shops."
- Never offer or imply any discount, deal, or price adjustment.

## Sizing guidance
Help customers find their correct size based on the products in the catalog. Use standard international sizing conventions appropriate for the store's locale ({{ locale }}).

## Product care advice
Provide appropriate care advice based on the product category. Follow best practices for the materials involved.

## Order modifications and post-order support
- The assistant cannot modify, cancel, or update any existing order.
- If a customer asks to change their shipping address, cancel an order, or any other post-order modification, always call get_store_info first to get the current support contact, then direct them to reach out directly.
- Never hardcode the support number — always get it from get_store_info.

## Store information
- NEVER answer from memory for any question about the store's name, location, phone, email, opening hours, return policy, exchange policy, delivery times, or any other store fact.
- For ANY such question, always call get_store_info first, then answer using only the values in the tool result.
- This applies even if you think you know the answer — the database is the only source of truth.

- Greet the user warmly. If they tell you their name, acknowledge it and use it.
- For general chit-chat (greetings, "how are you", small talk), respond briefly in one sentence and steer back toward the store.
- Your ONLY purpose is: helping customers find products, checking prices and stock, placing orders, tracking deliveries, and answering questions about store policies, location, contact, returns, exchanges, and delivery.
- Decline EVERYTHING else politely but firmly, and pivot to something store-related.
- When a product search returns no results, be helpful and specific — mention what they searched for and offer an alternative.
- Never use the same canned phrase twice in a row. Vary your wording naturally.
"""


# ── Prompt Registry ───────────────────────────────────────────────────────────
# Loads the active prompt version from the database at runtime.
# Falls back to the hardcoded SYSTEM_PROMPT if the DB is empty or unavailable.
# agent.py calls get_active_prompt() instead of using SYSTEM_PROMPT directly.

class PromptRegistry:
    """
    Runtime accessor for the versioned system prompt.

    Two render paths:
      1. render_for_tenant(tenant)            — fills PROMPT_TEMPLATE slots from
                                               TenantContext; used at request time.
      2. get_active_prompt_for_tenant(tenant) — checks DB for a tenant-specific
                                               prompt_template override first,
                                               then falls back to the global
                                               active PromptVersion, then to
                                               the built-in PROMPT_TEMPLATE.

    Backward-compat:
      get_active_prompt() — returns the global active PromptVersion text,
                            rendered against the default tenant. Used by
                            existing code paths that don't yet pass a tenant.

    To promote a new prompt version:
        POST /api/prompts            — create a new version
        POST /api/prompts/{id}/activate — make it active
    The next request will automatically pick up the new text.
    """

    # ── Template renderer ────────────────────────────────────────────────────

    @staticmethod
    def render_for_tenant(tenant: "TenantContext") -> str:  # type: ignore[name-defined]
        """
        Render PROMPT_TEMPLATE (or tenant.prompt_template if set) with
        values from the given TenantContext.

        Slots filled:
          {{ display_name }}      — e.g. "Style Store"
          {{ product_taxonomy }}  — free-text category description from tenant config
          {{ currency }}          — e.g. "NPR"
          {{ example_payment }}   — first payment method, e.g. "eSewa"
          {{ payment_methods }}   — comma-separated list, e.g. "eSewa, Khalti, Cash on Delivery"
          {{ phone_hint }}        — shown when phone validation fails
          {{ locale }}            — BCP-47 locale string
        """
        template = tenant.prompt_template or PROMPT_TEMPLATE
        pm_list = tenant.payment_methods
        return (
            template
            .replace("{{ display_name }}",     tenant.display_name)
            .replace("{{ product_taxonomy }}", tenant.product_taxonomy or "")
            .replace("{{ currency }}",         tenant.currency)
            .replace("{{ example_payment }}",  pm_list[0] if pm_list else "card")
            .replace("{{ payment_methods }}",  ", ".join(pm_list) if pm_list else "card")
            .replace("{{ phone_hint }}",       tenant.phone_hint)
            .replace("{{ locale }}",           tenant.locale)
        )

    # ── Per-tenant active prompt ─────────────────────────────────────────────

    @staticmethod
    def get_active_prompt_for_tenant(tenant: "TenantContext") -> str:  # type: ignore[name-defined]
        """
        Return the rendered system prompt for this tenant.

        Priority:
          1. tenant.prompt_template (set in tenant_configs row) — rendered against tenant
          2. Active PromptVersion for this tenant_id from DB — rendered against tenant
          3. Built-in PROMPT_TEMPLATE — rendered against tenant
        """
        # Tenant has its own template override — use it directly
        if tenant.prompt_template:
            return PromptRegistry.render_for_tenant(tenant)

        # Try tenant-scoped active PromptVersion from DB
        try:
            from app.database.database import SessionLocal
            from app.database.models import PromptVersion
            db = SessionLocal()
            try:
                row = (
                    db.query(PromptVersion)
                    .filter(
                        PromptVersion.tenant_id == tenant.tenant_id,
                        PromptVersion.is_active == 1,
                    )
                    .order_by(PromptVersion.version.desc())
                    .first()
                )
                if row:
                    # Render the stored text as a template too — allows
                    # stored prompts to also use {{ slots }} if desired.
                    import dataclasses
                    tenant_dict = dataclasses.asdict(tenant)
                    rendered = row.prompt_text
                    for key, val in tenant_dict.items():
                        if isinstance(val, list):
                            val = ", ".join(val)
                        rendered = rendered.replace(f"{{{{ {key} }}}}", str(val or ""))
                    return rendered
            finally:
                db.close()
        except Exception:
            pass

        # Fall back to built-in template rendered for this tenant
        return PromptRegistry.render_for_tenant(tenant)

    # ── Backward-compat: single-tenant get_active_prompt ────────────────────

    @staticmethod
    def get_active_prompt() -> str:
        """Backward-compatible: returns the active prompt rendered for the
        default tenant. Existing code paths that don't pass a tenant use this."""
        from app.config import get_tenant_context
        tenant = get_tenant_context("default")
        return PromptRegistry.get_active_prompt_for_tenant(tenant)

    @staticmethod
    def seed_initial(db=None) -> None:
        """
        Insert PROMPT_TEMPLATE as version 1 for the 'default' tenant if no
        prompt versions exist for it yet. Called once at startup (main.py).
        """
        from app.database.database import SessionLocal
        from app.database.models import PromptVersion
        close = db is None
        if db is None:
            db = SessionLocal()
        try:
            exists = (
                db.query(PromptVersion)
                .filter(PromptVersion.tenant_id == "default")
                .count()
            )
            if exists == 0:
                db.add(PromptVersion(
                    tenant_id="default",
                    version=1,
                    label="v1-initial",
                    prompt_text=PROMPT_TEMPLATE,
                    notes="Initial generic prompt template seeded automatically at first startup.",
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
        tenant_id: str = "default",
        db=None,
    ) -> "PromptVersion":
        """
        Save a new prompt version for the given tenant.
        Optionally make it the active version for that tenant immediately.
        Version numbers are scoped per tenant (each tenant has its own 1, 2, 3…).
        """
        from app.database.database import SessionLocal
        from app.database.models import PromptVersion
        close = db is None
        if db is None:
            db = SessionLocal()
        try:
            last = (
                db.query(PromptVersion)
                .filter(PromptVersion.tenant_id == tenant_id)
                .order_by(PromptVersion.version.desc())
                .first()
            )
            next_version = (last.version + 1) if last else 1
            if not label:
                label = f"v{next_version}"

            new_pv = PromptVersion(
                tenant_id=tenant_id,
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
                # Deactivate all other versions for THIS tenant only —
                # other tenants' active prompts are unaffected.
                db.query(PromptVersion).filter(
                    PromptVersion.tenant_id == tenant_id,
                    PromptVersion.id != new_pv.id,
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
        Activate a specific prompt version by its DB id.
        Only deactivates other versions belonging to the SAME tenant —
        other tenants' active prompts are unaffected.

        Raises ValueError if version_id does not exist.
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
            # Deactivate only this tenant's versions
            db.query(PromptVersion).filter(
                PromptVersion.tenant_id == row.tenant_id,
            ).update({"is_active": 0})
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
