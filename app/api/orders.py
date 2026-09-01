"""
Admin orders API.

Endpoints:
  GET /api/orders          — paginated list with optional filters
  GET /api/orders/{id}     — single order detail
  PATCH /api/orders/{id}/status — update order status (paid / cancelled)
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Order, OrderStatus, Product
from app.schemas.order import OrderListResponse, OrderOut

router = APIRouter(tags=["Orders"])


@router.get("/api/orders", response_model=OrderListResponse)
def list_orders(
    db: Session = Depends(get_db),
    status: OrderStatus | None = Query(default=None, description="Filter by status"),
    search: str | None = Query(default=None, description="Search by customer name or phone"),
    from_date: datetime | None = Query(default=None, description="Orders created on or after this datetime (ISO 8601)"),
    to_date: datetime | None = Query(default=None, description="Orders created on or before this datetime (ISO 8601)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    q = db.query(Order)

    if status:
        q = q.filter(Order.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (Order.customer_name.ilike(like)) | (Order.phone.ilike(like))
        )
    if from_date:
        q = q.filter(Order.created_at >= from_date)
    if to_date:
        q = q.filter(Order.created_at <= to_date)

    total = q.count()
    orders = (
        q.order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return OrderListResponse(
        total=total,
        page=page,
        page_size=page_size,
        orders=orders,
    )


@router.get("/api/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")
    return order


@router.patch("/api/orders/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: int,
    status: OrderStatus,
    db: Session = Depends(get_db),
):
    """
    Update an order's status. Restores stock when cancelling a
    pending_payment order so inventory stays accurate.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")

    if order.status == status:
        return order  # no-op

    # Restore stock if we're cancelling an order that hadn't been paid yet
    if status == OrderStatus.CANCELLED and order.status == OrderStatus.PENDING_PAYMENT:
        product = db.get(Product, order.product_id)
        if product:
            product.stock_quantity += order.quantity
            db.add(product)

    order.status = status
    db.add(order)
    db.commit()
    db.refresh(order)
    return order
