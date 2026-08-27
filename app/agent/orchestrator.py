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
    "shoes", "stock", "store", "sunglasses", "running", "casual", "formal",
}

EXPLICIT_PRODUCT_WORDS = {"backpack", "backpacks", "shoes", "sunglasses"}
PROGRAMMING_WORDS = {"code", "coding", "python", "program", "programming", "script"}
FINANCIAL_GIFT_WORDS = {
    "broke", "cash", "food", "girlfriend", "gift", "money", "starving",
}
CATALOG_QUERY_PHRASES = (
    "what products", "what are the products", "what shoes", "shoe types",
    "products you have", "what can i buy", "what do you sell", "show all",
    "list products",
)


def _special_response(message: str) -> str | None:
    words = set(re.findall(r"[a-z0-9]+", message.lower()))

    if words & PROGRAMMING_WORDS:
        return (
            "I'm here to help with our store's products, prices, stock, and orders. "
            "I can't provide Python code, but I can help you find a product or "
            "answer a store-related question."
        )

    if words & FINANCIAL_GIFT_WORDS and (
        "girlfriend" in words or "gift" in words or "food" in words
    ):
        return (
            "I'm sorry you're under that kind of pressure. Please prioritize food "
            "and essentials before buying a gift. A thoughtful no-cost gift could "
            "be a handwritten note, a playlist, a favorite meal when you can, or "
            "time spent together. Being honest with your girlfriend about your "
            "situation is more valuable than spending money you do not have."
        )

    return None


def _price_claim_response(
    db: Session, message: str, reference_product_id: int | None
) -> tuple[str, Product] | None:
    if not reference_product_id or not re.search(
        r"\b(?:bought|buy|paid|price|cost)\b", message.lower()
    ):
        return None

    amount_match = re.search(r"\b(\d+(?:[,.]\d+)?)\s*(?:rs|npr|rupees?)?\b", message.lower())
    product = db.get(Product, reference_product_id)
    if not amount_match or not product:
        return None

    claimed_amount = float(amount_match.group(1).replace(",", ""))
    history = (
        db.query(ProductPriceHistory)
        .filter(ProductPriceHistory.product_id == product.id)
        .all()
    )
    recorded_prices = {product.current_price} | {entry.price for entry in history}
    variant = f"{product.name} - {product.color}" if product.color else product.name

    if claimed_amount in recorded_prices:
        response = (
            f"Yes, {variant} was recorded at {claimed_amount:g} {product.currency} "
            "at one point."
        )
    else:
        lowest = min(recorded_prices) if recorded_prices else product.current_price
        response = (
            f"I couldn't verify a recorded price of {claimed_amount:g} "
            f"{product.currency} for {variant}. The lowest price in our records "
            f"is {lowest:g} {product.currency}."
        )

    return response, product


def _catalog_response(db: Session, message: str) -> str | None:
    normalized = message.lower()
    words = set(re.findall(r"[a-z0-9]+", normalized))
    is_catalog_request = (
        any(phrase in normalized for phrase in CATALOG_QUERY_PHRASES)
        or ("product" in words and "have" in words)
        or ("products" in words and "buy" in words)
        or ("shoes" in words and "types" in words)
    )
    if not is_catalog_request:
        return None

    products = db.query(Product).order_by(Product.brand, Product.name, Product.color).all()
    if not products:
        return "I do not have any products in the catalog right now."

    lines = [f"We currently have {len(products)} products available:"]
    for product in products:
        brand = (
            f"{product.brand} "
            if product.brand and not product.name.lower().startswith(product.brand.lower())
            else ""
        )
        color = f" ({product.color})" if product.color else ""
        lines.append(
            f"- {brand}{product.name}{color}: "
            f"{product.current_price:g} {product.currency}, "
            f"{product.stock_quantity} in stock"
        )
    return "\n".join(lines)


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
            | set(re.findall(r"[a-z0-9]+", (candidate.brand or "").lower()))
            | set(re.findall(r"[a-z0-9]+", (candidate.category or "").lower()))
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
        + (f"\nBrand: {product.brand}" if product.brand else "")
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
    special_response = _special_response(message)
    if special_response:
        return special_response, None, None

    price_claim = _price_claim_response(db, message, reference_product_id)
    if price_claim:
        reply, product = price_claim
        return reply, True, product

    catalog_response = _catalog_response(db, message)
    if catalog_response:
        return catalog_response, True, None

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
