"""
models.py — All SQLAlchemy database table definitions.

Tables defined here:
  products               — the product catalog (name, brand, price, stock, image, category, color)
  product_price_history  — price change log per product, used to show price trends
  conversation_states    — persisted chat history per session so the agent remembers past messages
  orders                 — one row per customer order (customer info, payment, status, grand total)
  order_items            — one row per product line inside an order (name, qty, unit price, line total)
  prompt_versions        — versioned history of the LLM system prompt; one row is marked active
  OrderStatus            — enum: pending_payment / paid / cancelled
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import relationship

from app.database.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, index=True, nullable=False)
    brand = Column(String, index=True, nullable=True)
    description = Column(String, nullable=True)
    category = Column(String, index=True, nullable=True)
    color = Column(String, index=True, nullable=True)
    image_url = Column(String, nullable=True)
    current_price = Column(Float, nullable=False)
    currency = Column(String, default="NPR", nullable=False)
    stock_quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    price_history = relationship(
        "ProductPriceHistory", back_populates="product", cascade="all, delete-orphan"
    )


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    price = Column(Float, nullable=False)
    currency = Column(String, default="NPR", nullable=False)
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    product = relationship("Product", back_populates="price_history")


class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CANCELLED = "cancelled"


class ConversationState(Base):
    """One row per conversation/session. Stores the full running message
    history (system/user/assistant/tool turns) as JSON so the agent has
    real memory across HTTP requests -- without this, every call starts a
    brand new conversation with no memory of what was said a turn ago."""

    __tablename__ = "conversation_states"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    messages = Column(JSON, nullable=False, default=list)
    last_product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class Order(Base):
    """One order per customer checkout session. Contains customer details
    and overall status. Line items are in OrderItem (one row per product)."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversation_states.id"), nullable=True)
    grand_total = Column(Float, nullable=False, default=0.0)
    currency = Column(String, default="NPR", nullable=False)
    customer_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    payment_method = Column(String, nullable=True)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING_PAYMENT)
    created_at = Column(DateTime, default=_utcnow)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """One row per product line in an order."""

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    product_name_snapshot = Column(String, nullable=False)
    color = Column(String, nullable=True)
    size = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    currency = Column(String, default="NPR", nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class PromptVersion(Base):
    """
    Versioned history of the LLM system prompt.

    Each row stores a complete snapshot of the system prompt text with
    metadata. Exactly one row has is_active=True — that is the prompt the
    agent loads at runtime. Changing the active prompt requires setting
    is_active=False on the current active row and is_active=True on the
    new one (handled atomically by the registry and admin API).

    Columns:
      version       — auto-incrementing integer label (1, 2, 3, …)
      label         — short human-readable name, e.g. "v1-initial", "v2-dspy-optimized"
      prompt_text   — full system prompt string
      notes         — free-text change notes, e.g. "Added sizing guidance"
      is_active     — True for the currently deployed prompt (only one at a time)
      created_by    — who created this version (e.g. "admin", "dspy-bootstrap")
      created_at    — when it was created
    """
    __tablename__ = "prompt_versions"

    id         = Column(Integer, primary_key=True, index=True)
    version    = Column(Integer, nullable=False, index=True)
    label      = Column(String, nullable=False)
    prompt_text = Column(String, nullable=False)
    notes      = Column(String, nullable=True)
    is_active  = Column(Integer, default=0, nullable=False)  # 1 = active, 0 = inactive
    created_by = Column(String, nullable=True, default="admin")
    created_at = Column(DateTime, default=_utcnow)
