import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.agent import handle_chat_message
from app.database.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["Chat"])


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    # Generate a conversation_id on first turn; the client echoes it back
    # on every subsequent message so the agent can load its history.
    conversation_id = request.conversation_id or str(uuid.uuid4())

    try:
        reply, product, payment_method = await handle_chat_message(db, conversation_id, request.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        product=product,
        payment_method=payment_method,
    )
