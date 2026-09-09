"""
schemas/chat.py — Pydantic models for the chat API request and response.

  ChatRequest   — what the frontend sends: message text + optional conversation_id
  ChatResponse  — what the API returns: reply text, optional rich card data,
                  optional payment QR method, conversation_id

NOTE: `card_data` replaces the old `product` field. It is a generic dict so
the schema is not coupled to the retail domain. The frontend maps it to the
appropriate UI component based on its shape. Serialised as `product` in the
JSON response for frontend backward compatibility.

Model selection is server-side only, resolved from the tenant's configuration
(TenantContext.llm_model → env var fallback). There is no per-request model
override — the caller cannot change the model via the API.
"""
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message:         str        = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    reply:           str
    # Generic card data — serialised as "product" for frontend backward compat.
    # Shape is determined by the active ToolRegistry adapter (retail → product
    # dict; agency → campaign dict; etc.).
    product:         dict[str, Any] | None = Field(
        default=None,
        description="Rich card data for the frontend to render. Shape depends on "
        "the active business-type adapter (retail: product dict; agency: campaign dict).",
    )
    payment_method:  str | None = Field(
        default=None,
        description="Lowercase payment method string when a digital payment was "
        "confirmed this turn — tells the frontend to render the matching QR code.",
    )
