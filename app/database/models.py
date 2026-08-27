"""
Phase 1 database models: products + product_price_history.

CRM/HRM/omnichannel tables are added in later phases per the
project's development order — keeping this file scoped to what
Phase 1 actually needs avoids a giant premature schema.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
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
