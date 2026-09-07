"""
schemas/product.py — Pydantic models for product data returned by the API.

  ProductOut           — full product detail sent to the frontend for the product card
                         (id, sku, name, brand, category, color, image_url, price, stock)
  ProductPriceHistoryOut — price history for a product including all past price entries
  PriceHistoryEntry    — a single historical price point (date + price)
"""

from datetime import datetime

from pydantic import BaseModel


class PriceHistoryEntry(BaseModel):
    date: datetime
    price: float
    currency: str

    class Config:
        from_attributes = True


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    brand: str | None
    description: str | None
    category: str | None
    color: str | None
    image_url: str | None
    current_price: float
    currency: str
    stock_quantity: int

    class Config:
        from_attributes = True


class ProductPriceHistoryOut(BaseModel):
    product_id: int
    product_name: str
    current_price: float
    currency: str
    history: list[PriceHistoryEntry]
