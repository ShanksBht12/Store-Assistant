import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.orchestrator import handle_chat_message
from app.database.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        reply, grounded, product = await handle_chat_message(
            db, request.message, request.reference_product_id
        )
    except RuntimeError as exc:
        # LLM/provider failure — fail gracefully, never fabricate an answer.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        conversation_id=request.conversation_id or str(uuid.uuid4()),
        reply=reply,
        grounded=grounded,
        product=product,
    )
