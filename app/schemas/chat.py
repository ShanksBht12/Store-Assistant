from pydantic import BaseModel, Field

from app.schemas.product import ProductOut


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    reference_product_id: int | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    grounded: bool | None = Field(
        default=None,
        description="True if the reply was generated from real database data "
        "rather than the LLM answering from its own knowledge; null for casual chat."
    )
    product: ProductOut | None = Field(
        default=None,
        description="The product the agent matched against the database, if any "
        "— the frontend renders this as a product card.",
    )
