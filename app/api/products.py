from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Product, ProductPriceHistory
from app.schemas.product import ProductOut, ProductPriceHistoryOut

router = APIRouter(tags=["products"])


@router.get("/api/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/api/products/{product_id}/price-history", response_model=ProductPriceHistoryOut)
def get_price_history(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    history = (
        db.query(ProductPriceHistory)
        .filter(ProductPriceHistory.product_id == product_id)
        .order_by(ProductPriceHistory.valid_from)
        .all()
    )

    return ProductPriceHistoryOut(
        product_id=product.id,
        product_name=product.name,
        current_price=product.current_price,
        currency=product.currency,
        history=[
            {"date": h.valid_from, "price": h.price, "currency": h.currency} for h in history
        ],
    )
