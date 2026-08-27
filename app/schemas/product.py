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
