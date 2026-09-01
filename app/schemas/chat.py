from pydantic import BaseModel, Field

from app.schemas.product import ProductOut


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    product: ProductOut | None = Field(
        default=None,
        description="The product the agent last interacted with, if any — "
        "the frontend renders this as a product card.",
    )
    payment_method: str | None = Field(
        default=None,
        description="Set to 'esewa' or 'khalti' after a successful create_order "
        "call — tells the frontend to render the matching payment QR code.",
    )
