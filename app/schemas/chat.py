"""
schemas/chat.py — Pydantic models for the chat API request and response.

  ChatRequest   — what the frontend sends: message text + optional conversation_id
                  + optional model override for per-request model selection
  ChatResponse  — what the API returns: reply text, optional rich card data,
                  optional payment QR method, conversation_id

NOTE: `card_data` replaces the old `product` field. It is a generic dict so
the schema is not coupled to the retail domain — a marketing agency adapter
can return campaign data, a booking adapter can return booking summaries, etc.
The frontend maps the dict to the appropriate UI component based on its shape.
For backward compatibility, the field is still serialised as `product` in the
JSON response so existing frontend code continues to work unchanged.
"""
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message:         str        = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    model:           str | None = Field(
        default=None,
        description=(
            "Optional per-request model override. Pass any LiteLLM model string "
            "to use a different model for this turn only. Examples: "
            "'anthropic/claude-3-5-sonnet', 'groq/llama-3.1-70b', 'ollama/llama3.2'. "
            "Omit to use the server's default (LLM_PROVIDER in .env)."
        ),
    )


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
