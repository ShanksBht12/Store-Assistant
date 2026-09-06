from datetime import datetime

from pydantic import BaseModel, Field

from app.database.models import OrderStatus


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    product_name_snapshot: str
    color: str | None
    size: str | None
    quantity: int
    unit_price: float
    line_total: float
    currency: str

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    conversation_id: str | None
    grand_total: float
    currency: str
    customer_name: str | None
    phone: str | None
    address: str | None
    payment_method: str | None
    status: OrderStatus
    created_at: datetime | None
    items: list[OrderItemOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    total: int = Field(description="Total matching orders (before pagination)")
    page: int
    page_size: int
    orders: list[OrderOut]
