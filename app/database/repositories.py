"""
repositories.py — Data access layer for the agent and tools.

WHY THIS EXISTS
  Tools and the retail registry used to import SQLAlchemy ORM models directly
  and call db.query() / db.get() inside their business logic. That couples the
  "what data do I need" question to the "how is it stored" answer, so swapping
  the database, changing the schema, or adding a cache requires touching every
  tool that queries a model.

  The repository pattern fixes this:
    Tool → Repository method → ORM / DB
              ↑
        (swappable seam)

  Tools and registries call repository methods with plain Python types.
  The repository owns every ORM import and every db.query() call for its model.
  Swapping SQLAlchemy for a REST API or a different DB only requires changing
  the repository — tools stay untouched.

REPOSITORIES
  ProductRepository     — search, get by id, price history
  OrderRepository       — create, get by id/phone, update payment, best sellers
  StoreInfoRepository   — get the single store info row
  ConversationRepository — load and save conversation message history
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.database.models import (
    ConversationState,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductPriceHistory,
    StoreInfo,
)


# ── Product ───────────────────────────────────────────────────────────────────

class ProductRepository:
    """All read/write operations on the products and price-history tables."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, product_id: int) -> Product | None:
        return self._db.get(Product, product_id)

    def get_by_name_exact(self, name: str) -> Product | None:
        return self._db.query(Product).filter(Product.name.ilike(name.strip())).first()

    def search(
        self,
        remaining_query: str | None,
        resolved_color: str | None,
        resolved_category: str | None,
        narrow_word: str | None,
        max_results: int = 20,
    ) -> list[Product]:
        """
        Full-text + filter product search.  All ORM filter logic lives here —
        callers pass plain Python values and receive plain ORM objects.
        """
        q = self._db.query(Product)

        if remaining_query:
            stop_words = {"and", "or", "&", "the", "a", "an", "for", "in", "with", "of"}
            tokens = [
                t.strip(".,;:")
                for t in remaining_query.split()
                if t.strip(".,;:").lower() not in stop_words and t.strip(".,;:")
            ]
            if tokens:
                token_filters = []
                for token in tokens:
                    like = f"%{token}%"
                    token_filters.append(Product.name.ilike(like))
                    token_filters.append(Product.brand.ilike(like))
                    if len(token) >= 4:
                        token_filters.append(Product.category.ilike(like))
                        token_filters.append(Product.description.ilike(like))
                q = q.filter(or_(*token_filters))
                full_like = f"%{remaining_query}%"
                q = q.order_by(
                    case(
                        (Product.name.ilike(full_like), 0),
                        (Product.brand.ilike(full_like), 1),
                        else_=2,
                    ),
                    Product.id,
                )
            else:
                q = q.order_by(Product.id)
        else:
            q = q.order_by(Product.id)

        if resolved_color:
            q = q.filter(Product.color.ilike(f"%{resolved_color}%"))

        if resolved_category:
            _EXACT = {
                "Men's Tops", "Men's Bottoms", "Men's Outerwear",
                "Women's Tops", "Women's Bottoms", "Women's Dresses", "Women's Outerwear",
                "Kids Boys", "Kids Girls",
                "Bags & Backpacks", "Hats & Caps", "Socks & Underwear",
                "Sunglasses", "Watches", "Sportswear",
                "Running", "Casual", "Training", "Basketball", "Trail",
                "Hiking", "Formal", "Sandal",
            }
            if resolved_category in _EXACT:
                q = q.filter(Product.category == resolved_category)
            else:
                q = q.filter(Product.category.ilike(f"%{resolved_category}%"))

        if narrow_word:
            narrow_like = f"%{narrow_word}%"
            q = q.filter(
                or_(Product.name.ilike(narrow_like), Product.description.ilike(narrow_like))
            )

        return q.limit(max_results).all()

    def get_price_history(self, product_id: int) -> list[ProductPriceHistory]:
        return (
            self._db.query(ProductPriceHistory)
            .filter(ProductPriceHistory.product_id == product_id)
            .order_by(ProductPriceHistory.valid_from)
            .all()
        )

    def decrement_stock(self, product: Product, qty: int) -> None:
        product.stock_quantity -= qty
        self._db.add(product)


# ── Order ─────────────────────────────────────────────────────────────────────

class OrderRepository:
    """All read/write operations on orders and order_items tables."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, order_id: int) -> Order | None:
        return self._db.get(Order, order_id)

    def get_by_phone(self, phone_digits: str, limit: int = 10) -> list[Order]:
        return (
            self._db.query(Order)
            .filter(Order.phone == phone_digits)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .all()
        )

    def create(
        self,
        conversation_id: str | None,
        grand_total: float,
        currency: str,
        customer_name: str,
        phone: str,
        address: str,
        payment_method: str,
        items: list[dict],          # list of resolved item dicts from CreateOrderTool
    ) -> Order:
        """
        Persist one Order + its OrderItem rows atomically.
        `items` is the resolved list built by CreateOrderTool before calling here.
        Each entry: { product, qty, size, color, unit_price, line_total, currency }
        """
        order = Order(
            conversation_id = conversation_id,
            grand_total     = grand_total,
            currency        = currency,
            customer_name   = customer_name,
            phone           = phone,
            address         = address,
            payment_method  = payment_method,
            status          = OrderStatus.PENDING_PAYMENT,
        )
        self._db.add(order)
        self._db.flush()  # get order.id before inserting items

        for r in items:
            product = r["product"]
            oi = OrderItem(
                order_id              = order.id,
                product_id            = product.id,
                product_name_snapshot = product.name,
                color                 = r["color"],
                size                  = r["size"],
                quantity              = r["qty"],
                unit_price            = r["unit_price"],
                line_total            = r["line_total"],
                currency              = r["currency"],
            )
            self._db.add(oi)
            product.stock_quantity -= r["qty"]
            self._db.add(product)

        self._db.commit()
        self._db.refresh(order)
        return order

    def update_payment_method(self, order: Order, payment_method: str) -> Order:
        order.payment_method = payment_method
        self._db.add(order)
        self._db.commit()
        self._db.refresh(order)
        return order

    def is_pending(self, order: Order) -> bool:
        """Return True if the order is in pending_payment status."""
        return order.status == OrderStatus.PENDING_PAYMENT

    def get_best_sellers(self, limit: int = 5) -> list[Any]:
        return (
            self._db.query(
                OrderItem.product_name_snapshot,
                OrderItem.color,
                func.sum(OrderItem.quantity).label("total_sold"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .filter(Order.status != OrderStatus.CANCELLED)
            .group_by(OrderItem.product_name_snapshot, OrderItem.color)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
            .all()
        )


# ── Store info ────────────────────────────────────────────────────────────────

class StoreInfoRepository:
    """Read the single StoreInfo row."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self) -> StoreInfo | None:
        return self._db.get(StoreInfo, 1)


# ── Conversation ──────────────────────────────────────────────────────────────

class ConversationRepository:
    """Load and save conversation message history (ConversationState rows)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_or_create(
        self,
        conversation_id: str,
        initial_messages: list[dict],
    ) -> ConversationState:
        """Return the existing state, or create a new one with initial_messages."""
        state = self._db.get(ConversationState, conversation_id)
        if state is None:
            state = ConversationState(
                id       = conversation_id,
                messages = initial_messages,
            )
            self._db.add(state)
            self._db.commit()
        return state

    def save_messages(
        self,
        state: ConversationState,
        messages: list[dict],
        max_history: int = 60,
    ) -> None:
        """Persist updated message history, trimming old turns if needed."""
        system = messages[:1]
        rest   = messages[1:]
        if len(rest) > max_history:
            rest = rest[-max_history:]
        state.messages = system + rest
        self._db.add(state)
        self._db.commit()
