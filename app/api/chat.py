"""
chat.py — Chat API endpoint.

Exposes:
  POST /api/chat

Receives the customer's message and optional conversation_id.
Now routes through app/agent/router.py which:
  - Configures DSPy with the right LM for this request
  - Accepts an optional per-request model override
  - Delegates to the agent loop (agent.py)

Returns:
  - reply:           the assistant's text response
  - product:         product card to display (if a specific product was found)
  - payment_method:  'esewa' or 'khalti' if an order was placed (triggers QR)
  - conversation_id: echoed back so the frontend can continue the same session
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.router import route_chat
from app.database.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["Chat"])


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    # Generate a conversation_id on the first turn; the client echoes it back
    # on every subsequent message so the agent can load its history.
    conversation_id = request.conversation_id or str(uuid.uuid4())

    try:
        reply, card_data, payment_method = await route_chat(
            db=db,
            conversation_id=conversation_id,
            message=request.message,
            model_override=request.model,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        product=card_data,        # generic card dict; field named 'product' for frontend compat
        payment_method=payment_method,
    )
