"""
Phase 2 tool registry.

Each tool is:
  - a JSON-schema "spec" dict (OpenAI/Groq function-calling format) sent to
    the model so it knows what's available and what arguments to pass
  - a plain Python function taking (db: Session, **arguments) that returns
    a JSON-serializable result

The model decides which tool(s) to call and with what arguments -- we no
longer guess intent with regex (that was Phase 1's `_is_product_query` /
`_find_product`). We just execute exactly what the model asked for and feed
the real DB result back to it, so it can't invent facts it wasn't given.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import Product, ProductPriceHistory


def search_products(
    db: Session,
    query: str | None = None,
    color: str | None = None,
    category: str | None = None,
    max_results: int = 5,
) -> dict[str, Any]:
    """Search the product catalog by name/brand/category keyword and/or color."""
    q = db.query(Product)
    if query:
        like = f"%{query}%"
        q = q.filter(
            or_(
                Product.name.ilike(like),
                Product.brand.ilike(like),
                Product.category.ilike(like),
            )
        )
    if color:
        q = q.filter(Product.color.ilike(f"%{color}%"))
    if category:
        q = q.filter(Product.category.ilike(f"%{category}%"))

    products = q.order_by(Product.id).limit(max_results).all()
    return {
        "count": len(products),
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "brand": p.brand,
                "color": p.color,
                "category": p.category,
                "price": p.current_price,
                "currency": p.currency,
                "stock_quantity": p.stock_quantity,
            }
            for p in products
        ],
    }


def get_price_history(db: Session, product_id: int) -> dict[str, Any]:
    """Return the recorded price history for a specific product id."""
    product = db.get(Product, product_id)
    if product is None:
        return {"error": f"No product found with id {product_id}"}

    history = (
        db.query(ProductPriceHistory)
        .filter(ProductPriceHistory.product_id == product_id)
        .order_by(ProductPriceHistory.valid_from)
        .all()
    )
    return {
        "product_id": product_id,
        "product_name": product.name,
        "current_price": product.current_price,
        "currency": product.currency,
        "history": [
            {
                "date": h.valid_from.date().isoformat(),
                "price": h.price,
                "currency": h.currency,
            }
            for h in history
        ],
    }


def check_stock(db: Session, product_id: int) -> dict[str, Any]:
    """Return live stock quantity for a specific product id."""
    product = db.get(Product, product_id)
    if product is None:
        return {"error": f"No product found with id {product_id}"}
    return {
        "product_id": product_id,
        "product_name": product.name,
        "stock_quantity": product.stock_quantity,
        "in_stock": product.stock_quantity > 0,
    }


# --- OpenAI/Groq-format tool specs sent to the model -----------------------

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Search the store's product catalog by keyword (matches name, "
                "brand, or category), optionally filtered by color or category. "
                "Use this whenever the user asks about a product, wants "
                "recommendations, or asks what's available -- never guess or "
                "invent product details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text keyword, e.g. product name, brand, or type ('shoes', 'AeroRun').",
                    },
                    "color": {
                        "type": "string",
                        "description": "Filter by color, e.g. 'black'.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category, e.g. 'Shoes', 'Sunglasses'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max number of matches to return. Default 5.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_history",
            "description": "Get the recorded price history for one specific product, by its id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "The product's database id.",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_stock",
            "description": "Check live stock quantity for one specific product, by its id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "The product's database id.",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
]

TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "search_products": search_products,
    "get_price_history": get_price_history,
    "check_stock": check_stock,
}