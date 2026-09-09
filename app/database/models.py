"""
models.py — All SQLAlchemy database table definitions.

Tables defined here:
  products               — the product catalog (name, brand, price, stock, image, category, color)
  product_price_history  — price change log per product, used to show price trends
  conversation_states    — persisted chat history per session so the agent remembers past messages
  orders                 — one row per customer order (customer info, payment, status, grand total)
  order_items            — one row per product line inside an order (name, qty, unit price, line total)
  tenant_configs         — per-tenant config: phone regex, payment methods, currency, prompt template
  store_info             — single-row mutable store facts (name, location, contact, hours, policies)
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


class TenantConfig(Base):
    """
    Per-tenant configuration: one row per tenant (default tenant id='default').

    Holds all the business-specific, region-specific settings that vary between
    deployments — phone validation rules, accepted payment methods, product
    taxonomy description, currency, locale, and the base prompt template.

    The agent resolves the active tenant at request time via get_tenant_context()
    in config.py and passes it into tools and the prompt renderer, so nothing
    business-specific is compiled into source code.

    Columns:
      tenant_id        — unique string key, e.g. 'default', 'style-store', 'acme-retail'
      display_name     — human-readable tenant name, e.g. 'Style Store'
      phone_regex      — Python regex for valid customer phone numbers, e.g. '^9[678]\\d{8}$'
      phone_hint       — human-readable hint shown when phone is invalid
      payment_methods  — JSON list of accepted payment method strings (lowercase),
                         e.g. ["esewa", "khalti", "cash on delivery", "cod"]
      digital_payments — JSON list of payment methods that trigger a QR code,
                         e.g. ["esewa", "khalti"]
      currency         — ISO currency code, e.g. 'NPR', 'USD', 'EUR'
      locale           — BCP-47 locale string, e.g. 'ne-NP', 'en-US'
      product_taxonomy — free-text description of product categories for the prompt
      prompt_template  — Jinja2-style prompt template; use {{ variable }} slots for
                         tenant-specific values. If empty, the global PromptVersion
                         active text is used as-is.
      is_active        — 1 = this tenant is currently active, 0 = disabled
      created_at       — when this row was created
      updated_at       — last update timestamp
    """
    __tablename__ = "tenant_configs"

    tenant_id        = Column(String, primary_key=True, index=True)
    display_name     = Column(String, nullable=False, default="My Store")
    phone_regex      = Column(String, nullable=False, default=r"^\+?\d{7,15}$")
    phone_hint       = Column(String, nullable=False,
                              default="Please enter a valid phone number.")
    payment_methods  = Column(JSON, nullable=False,
                              default=lambda: ["card", "cash on delivery"])
    digital_payments = Column(JSON, nullable=False,
                              default=lambda: [])
    currency         = Column(String, nullable=False, default="USD")
    locale           = Column(String, nullable=False, default="en-US")
    product_taxonomy = Column(String, nullable=True)
    prompt_template  = Column(String, nullable=True)
    is_active        = Column(Integer, nullable=False, default=1)
    created_at       = Column(DateTime, default=_utcnow)
    updated_at       = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class StoreInfo(Base):
    """
    Single-row table holding all mutable store facts (name, location, contact,
    hours, policies, etc.).  The agent fetches this via the get_store_info tool
    instead of reading a hardcoded string, so changing any value here is
    instantly reflected in chatbot responses without a code change.

    Only one row is expected (id=1).  The seed inserts it on first startup.
    Update via PUT /api/store.
    """
    __tablename__ = "store_info"

    id            = Column(Integer, primary_key=True, default=1)
    store_name    = Column(String, nullable=False, default="Style Store")
    location      = Column(String, nullable=True)
    phone         = Column(String, nullable=True)
    email         = Column(String, nullable=True)
    instagram     = Column(String, nullable=True)
    opening_hours = Column(String, nullable=True)
    return_policy = Column(String, nullable=True)
    exchange_policy = Column(String, nullable=True)
    delivery_info = Column(String, nullable=True)
    extra_notes   = Column(String, nullable=True)   # any other free-text facts
    updated_at    = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class PromptVersion(Base):
    """
    Versioned history of the LLM system prompt, scoped per tenant.

    Each row stores a complete snapshot of the system prompt text for a
    specific tenant. Exactly one row per tenant has is_active=1 — that is
    the prompt the agent loads at runtime for that tenant. This means multiple
    business personas can run from the same deployment simultaneously, each
    with its own independent prompt version history.

    Columns:
      tenant_id     — which tenant this version belongs to (FK → tenant_configs)
      version       — auto-incrementing integer label per tenant (1, 2, 3, …)
      label         — short human-readable name, e.g. "v1-initial", "v2-dspy-optimized"
      prompt_text   — full system prompt string (may contain {{ slots }})
      notes         — free-text change notes
      is_active     — 1 = currently active for this tenant (one active per tenant)
      created_by    — who/what created it ("admin", "dspy-bootstrap", etc.)
      created_at    — when it was created
    """
    __tablename__ = "prompt_versions"

    id          = Column(Integer, primary_key=True, index=True)
    tenant_id   = Column(String, nullable=False, index=True, default="default")
    version     = Column(Integer, nullable=False, index=True)
    label       = Column(String, nullable=False)
    prompt_text = Column(String, nullable=False)
    notes       = Column(String, nullable=True)
    is_active   = Column(Integer, default=0, nullable=False)  # 1 = active for this tenant
    created_by  = Column(String, nullable=True, default="admin")
    created_at  = Column(DateTime, default=_utcnow)
