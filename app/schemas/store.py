"""
schemas/store.py — Pydantic models for the store info API.

  StoreInfoOut    — full store info returned by GET /api/store
  StoreInfoUpdate — partial update body for PUT /api/store
"""
from datetime import datetime

from pydantic import BaseModel


class StoreInfoOut(BaseModel):
    id:               int
    store_name:       str
    location:         str | None
    phone:            str | None
    email:            str | None
    instagram:        str | None
    opening_hours:    str | None
    return_policy:    str | None
    exchange_policy:  str | None
    delivery_info:    str | None
    extra_notes:      str | None
    updated_at:       datetime | None

    class Config:
        from_attributes = True


class StoreInfoUpdate(BaseModel):
    """All fields optional — only supplied fields are updated."""
    store_name:       str | None = None
    location:         str | None = None
    phone:            str | None = None
    email:            str | None = None
    instagram:        str | None = None
    opening_hours:    str | None = None
    return_policy:    str | None = None
    exchange_policy:  str | None = None
    delivery_info:    str | None = None
    extra_notes:      str | None = None
