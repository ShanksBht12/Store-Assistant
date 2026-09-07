"""
schemas/chat.py — Pydantic models for the chat API request and response.

  ChatRequest   — what the frontend sends: message text + optional conversation_id
                  + optional model override for per-request model selection
  ChatResponse  — what the API returns: reply text, optional product card,
                  optional payment QR method, conversation_id
"""

from pydantic import BaseModel, Field

from app.schemas.product import ProductOut


class ChatRequest(BaseModel):
    message:         str       = Field(..., min_length=1, max_length=4000)
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
    product:         ProductOut | None = Field(
        default=None,
        description="The product the agent last interacted with, if any — "
        "the frontend renders this as a product card.",
    )
    payment_method:  str | None = Field(
        default=None,
        description="Set to 'esewa' or 'khalti' after a successful create_order "
        "call — tells the frontend to render the matching payment QR code.",
    )
