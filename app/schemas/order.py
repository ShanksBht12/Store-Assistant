from datetime import datetime

from pydantic import BaseModel, Field

from app.database.models import OrderStatus


class OrderOut(BaseModel):
    id: int
    conversation_id: str | None
    product_id: int
    product_name_snapshot: str
    color: str | None
    size: str | None
    quantity: int
    unit_price: float
    total_price: float
    currency: str
    customer_name: str | None
    phone: str | None
    address: str | None
    payment_method: str | None
    status: OrderStatus
    created_at: datetime | None

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    total: int = Field(description="Total matching orders (before pagination)")
    page: int
    page_size: int
    orders: list[OrderOut]
