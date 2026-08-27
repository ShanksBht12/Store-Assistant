"""
Phase 1 orchestrator.

Real function/tool calling (where Grok itself decides which tool to
invoke) is a Phase 2 concern — see app/agent/agent.py's docstring.
For Phase 1 we keep the flow simple and still fully DB-grounded:

    user message
        -> naive product + color match against the database
        -> build a system prompt containing ONLY real DB facts
        -> Grok turns those facts into a natural reply
        -> if no product matched, tell the LLM explicitly so it
           does not invent an answer
        -> the matched product (if any) is also returned as
           structured data so the frontend can render a product card

This satisfies the core anti-hallucination rule from day one, even
before the tool-calling architecture exists.
"""
from sqlalchemy import or_
from sqlalchemy.orm import Session
import re

from app.database.models import Product, ProductPriceHistory
from app.providers.llm import get_llm_provider

SYSTEM_PROMPT_TEMPLATE = """You are a helpful business assistant for an e-commerce store.

Rules you MUST follow:
- Only state prices, colors, and facts that appear in the "Known facts" section below.
- If the Known facts section says no matching product was found, tell the
  user you don't have that information — never invent a price, color, or date.
- Always identify a matched product using its model name and color, such as
    "AeroRun X1 in Pink". Do not call it only "shoes".
- Do not use Markdown formatting in your response.
- Keep answers short and conversational.

Known facts:
{facts}
"""

# Recognized color words for matching queries like "black shoes" or "pink shoes".
KNOWN_COLORS = {
    "black", "white", "pink", "blue", "grey", "gray", "red", "green",
    "brown", "tan", "navy", "yellow", "purple", "orange", "beige",
}

PRODUCT_QUERY_WORDS = {
    "available", "buy", "cost", "inventory", "order", "price", "product",
    "shoes", "stock", "store", "sunglasses",
}

EXPLICIT_PRODUCT_WORDS = {"backpack", "backpacks", "shoes", "sunglasses"}


def _is_product_query(db: Session, message: str) -> bool:
    words = set(re.findall(r"[a-z0-9]+", message.lower()))
    if words & (KNOWN_COLORS | PRODUCT_QUERY_WORDS):
        return True
    if "how much" in message.lower() or "do you have" in message.lower():
        return True

    for product in db.query(Product).all():
        product_words = set(re.findall(r"[a-z0-9]+", product.name.lower()))
        if words & product_words:
            return True
    return False


def _find_product(
    db: Session, message: str, reference_product_id: int | None = None
) -> Product | None:
    """Keyword match on product name and color. Good enough for Phase 1;
    Phase 2 replaces this with a proper search_products() tool call."""
    words = re.findall(r"[a-z0-9]+", message.lower())
    words = [word for word in words if len(word) > 1]
    if not words:
        return None

    color_words = {w for w in words if w in KNOWN_COLORS}

    candidates = db.query(Product).all()
    if reference_product_id and not set(words) & EXPLICIT_PRODUCT_WORDS:
        reference_product = db.get(Product, reference_product_id)
        if reference_product:
            candidates = [
                candidate for candidate in candidates
                if candidate.name == reference_product.name
                and candidate.category == reference_product.category
            ]
    candidates = [
        candidate
        for candidate in candidates
        if set(words)
        & (
            set(re.findall(r"[a-z0-9]+", candidate.name.lower()))
            | set(re.findall(r"[a-z0-9]+", (candidate.color or "").lower()))
        )
    ]
    if not candidates:
        return None

    # If the user mentioned a color, prefer the candidate that actually has it —
    # otherwise a plain "black shoes" query could return the wrong-colored pair.
    if color_words:
        for candidate in candidates:
            if candidate.color and candidate.color.lower() in color_words:
                return candidate

    return candidates[0]


def _build_facts(db: Session, product: Product | None) -> str:
    if product is None:
        return "No matching product was found in the database for this question."

    history = (
        db.query(ProductPriceHistory)
        .filter(ProductPriceHistory.product_id == product.id)
        .order_by(ProductPriceHistory.valid_from)
        .all()
    )

    lines = [
        f"Product model: {product.name}"
        + (f"\nColor: {product.color}" if product.color else ""),
        f"Current price: {product.current_price} {product.currency}",
        f"Stock quantity: {product.stock_quantity}",
    ]
    if history:
        lines.append("Price history:")
        for h in history:
            lines.append(f"  - {h.valid_from.date()}: {h.price} {h.currency}")
    else:
        lines.append("No price history is recorded for this product.")

    return "\n".join(lines)


async def handle_chat_message(
    db: Session, message: str, reference_product_id: int | None = None
) -> tuple[str, bool | None, Product | None]:
    """Returns (reply_text, grounded, matched_product)."""
    product_query = _is_product_query(db, message)
    product = (
        _find_product(db, message, reference_product_id) if product_query else None
    )
    facts = _build_facts(db, product) if product_query else "No product lookup was requested."

    llm = get_llm_provider()
    reply = await llm.generate(
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(facts=facts),
        user_message=message,
    )
    if not reply.strip() and product is not None:
        variant = f"{product.name} - {product.color}" if product.color else product.name
        reply = (
            f"{variant} is priced at {product.current_price} {product.currency} "
            f"and has {product.stock_quantity} in stock."
        )
    return reply, product is not None if product_query else None, product
