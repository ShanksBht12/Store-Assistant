"""
retail_registry.py — Retail-store adapter implementing ToolRegistry.

This is the ONLY file that knows about:
  - Product / Order ORM models
  - search_products, create_order, check_stock, get_product, etc.
  - Product card display logic (which tool results trigger a card)
  - Order confirmation formatting
  - eSewa/Khalti QR triggering

agent.py imports nothing from here directly — it receives a RetailToolRegistry
instance injected by router.py and talks to it only through the ToolRegistry
Protocol defined in registry.py.

To add a new business type (marketing agency, booking platform, …):
  1. Create a new *_registry.py that implements ToolRegistry.
  2. Instantiate it in router.py based on tenant config.
  3. agent.py, prompt.py, and the LLM provider layer stay unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.agent.tools import build_tools
from app.database.models import Order, OrderItem, Product

if TYPE_CHECKING:
    from app.config import TenantContext


class RetailToolRegistry:
    """
    Retail adapter: wraps the existing tools.py tool set behind ToolRegistry.

    All retail-specific post-call logic that used to live in agent.py
    (_extract_product_and_payment, order confirmation formatting, product
    card display rules) now lives here.
    """

    def __init__(self, tenant: "TenantContext") -> None:
        self._tenant = tenant
        self._tools, self._specs = build_tools(tenant)

    # ── ToolRegistry interface ───────────────────────────────────────────────

    @property
    def tool_specs(self) -> list[dict[str, Any]]:
        return self._specs

    def run_tool(
        self,
        db: Session,
        name: str,
        arguments: dict[str, Any],
        conversation_id: str,
    ) -> dict[str, Any]:
        """
        Execute the named retail tool. Injects conversation_id into
        create_order arguments — the only retail tool that needs it.
        """
        if name == "create_order":
            arguments = {**arguments, "conversation_id": conversation_id}

        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool '{name}'"}
        try:
            return tool.run(db, **arguments)
        except TypeError as exc:
            return {"error": f"Bad arguments for '{name}': {exc}"}

    def extract_turn_extras(
        self,
        db: Session,
        tool_calls_made: list[dict[str, Any]],
    ) -> tuple[dict | None, str | None]:
        """
        Retail card-display logic: decide whether to show a product card and
        which payment method (if any) triggered a QR code this turn.

        Returns (card_data_dict_or_None, payment_method_or_None).
        card_data is the full product dict the frontend renders as a card.
        """
        digital = {m.lower() for m in self._tenant.digital_payments}
        product: Product | None = None
        payment_method: str | None = None

        for call in tool_calls_made:
            name      = call["name"]
            arguments = call.get("arguments", {})
            result    = call.get("result", {})

            if name == "search_products":
                products_data = result.get("products", [])
                if not products_data:
                    continue
                first     = products_data[0]
                query_arg = arguments.get("query") or ""
                color_arg = arguments.get("color") or ""

                # LLM sometimes bakes color into query string instead of
                # using the separate color param — detect and normalise.
                if not color_arg and first.get("color") and query_arg:
                    if first["color"].lower() in query_arg.lower():
                        color_arg = first["color"]

                if len(products_data) == 1:
                    p = db.get(Product, first["id"])
                    if p:
                        product = p
                elif color_arg and _is_specific_hit(query_arg, first.get("name", "")):
                    p = db.get(Product, first["id"])
                    if p:
                        product = p
                elif (
                    not color_arg
                    and len(products_data) <= 3
                    and _is_specific_hit(query_arg, first.get("name", ""))
                ):
                    p = db.get(Product, first["id"])
                    if p:
                        product = p

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

            elif name in ("create_order", "update_order_payment"):
                if "order_id" in result:
                    raw_pm    = result.get("payment_method", "")
                    normalised = raw_pm.strip().lower()
                    payment_method = normalised if normalised in digital else None
                product = None  # never show a product card on order/payment turns

        card_data = _product_to_dict(product) if product else None
        return card_data, payment_method

    def build_order_confirmation(
        self,
        tool_calls_made: list[dict[str, Any]],
        digital_payments: set[str],
    ) -> tuple[str | None, str | None]:
        """
        Build a deterministic order confirmation string from create_order /
        update_order_payment results so the LLM doesn't have to format
        order IDs, totals, and item lines (too error-prone).

        Returns (confirmation_text_or_None, payment_method_or_None).
        """
        confirmations: list[str] = []
        final_payment: str | None = None

        for call_rec in tool_calls_made:
            name   = call_rec["name"]
            result = call_rec["result"]

            if name == "create_order" and "order_id" in result:
                pm         = result.get("payment_method", "")
                pm_lower   = pm.strip().lower()
                grand_total = result.get("grand_total", 0)
                currency    = result.get("currency", "NPR")
                order_id    = result["order_id"]
                items_list  = result.get("items", [])

                item_lines = []
                for it in items_list:
                    pname = it.get("product_name", "item")
                    qty   = it.get("quantity", 1)
                    lt    = it.get("line_total", 0)
                    size  = it.get("size")
                    sz    = f" size {size}" if size else ""
                    item_lines.append(f"{pname}{sz} x{qty} = {lt:,.0f} {currency}")

                if pm_lower in digital_payments:
                    payment_note   = f"The {pm} QR code is displayed in the chat — scan it to complete your payment."
                    final_payment  = pm_lower
                else:
                    payment_note = "Please have cash ready upon delivery."

                summary = ", ".join(item_lines) if item_lines else "your items"
                confirmations.append(
                    f"Order ID: {order_id}. "
                    f"Items: {summary}. "
                    f"Grand total: {grand_total:,.0f} {currency}. "
                    f"Payment: {pm}. {payment_note}"
                )

            elif name == "update_order_payment" and "order_id" in result:
                pm        = result.get("payment_method", "")
                pm_lower  = pm.strip().lower()
                order_id  = result["order_id"]
                total     = result.get("total_price", 0)
                currency  = result.get("currency", "NPR")

                if pm_lower in digital_payments:
                    payment_note  = f"The {pm} QR code is now displayed in the chat — scan it to complete your payment."
                    final_payment = pm_lower
                else:
                    payment_note = "Please have cash ready upon delivery."

                confirmations.append(
                    f"Payment method for Order {order_id} updated to {pm}. "
                    f"Total: {total:,.0f} {currency}. {payment_note}"
                )

        if not confirmations:
            return None, None

        return f"Your order is confirmed! {' '.join(confirmations)}", final_payment


# ── Private helpers ───────────────────────────────────────────────────────────

def _is_specific_hit(query: str, product_name: str) -> bool:
    """Return True if the product name closely matches the search query.
    Used to decide whether a multi-result search should show a card."""
    if not query:
        return False
    stop = {"and", "or", "&", "the", "a", "an", "for", "in", "with", "of"}
    q_words = [
        w.strip(".,;:").lower()
        for w in query.split()
        if w.strip(".,;:").lower() not in stop and len(w.strip(".,;:")) >= 2
    ]
    if not q_words:
        return False
    name_lower = product_name.lower()
    matches = sum(1 for w in q_words if w in name_lower)
    return matches / len(q_words) >= 0.6


def _product_to_dict(product: Product) -> dict[str, Any]:
    """Serialise a Product ORM row to the card dict the frontend expects."""
    return {
        "id":             product.id,
        "sku":            product.sku,
        "name":           product.name,
        "brand":          product.brand,
        "description":    product.description,
        "category":       product.category,
        "color":          product.color,
        "image_url":      product.image_url,
        "current_price":  product.current_price,
        "currency":       product.currency,
        "stock_quantity": product.stock_quantity,
    }
