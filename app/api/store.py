"""
store.py — Store information API.

Exposes:
  GET /api/store   — retrieve the current store info (used by the agent tool and admin UI)
  PUT /api/store   — update any store field; changes are reflected in the chatbot immediately
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import StoreInfo
from app.schemas.store import StoreInfoOut, StoreInfoUpdate

router = APIRouter(prefix="/api/store", tags=["Store"])


def _get_or_404(db: Session) -> StoreInfo:
    row = db.get(StoreInfo, 1)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Store info not found. Run seed_store_info() to initialise it.",
        )
    return row


@router.get("", response_model=StoreInfoOut)
def get_store_info(db: Session = Depends(get_db)):
    """Return the store's contact details, hours, and policies."""
    return _get_or_404(db)


@router.put("", response_model=StoreInfoOut)
def update_store_info(body: StoreInfoUpdate, db: Session = Depends(get_db)):
    """
    Update any subset of store fields.
    Changes take effect on the very next chatbot turn — no restart needed.
    """
    row = _get_or_404(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
