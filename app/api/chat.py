"""
chat.py — Chat API endpoint.

Exposes:
  POST /api/chat

Request flow:
  1. Resolve TenantContext for this request (default tenant for now; extend
     to header/JWT-based tenant resolution for true multi-tenancy).
  2. Enforce per-tenant rate limits (requests_per_minute, requests_per_day)
     from TenantContext. Returns HTTP 429 with a Retry-After header if exceeded.
  3. Route through router.py → agent loop → ToolRegistry → LLM.

Returns:
  - reply:           the assistant's text response
  - product:         rich card data for the frontend (shape depends on adapter)
  - payment_method:  lowercase payment method if a digital order was placed
  - conversation_id: echoed back so the frontend can continue the same session
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.agent.rate_limiter import get_rate_limiter
from app.agent.router import route_chat
from app.config import get_tenant_context
from app.database.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["Chat"])


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    request:  ChatRequest,
    response: Response,
    db:       Session = Depends(get_db),
):
    # ── Resolve tenant ────────────────────────────────────────────────────────
    # Currently always "default". To support multiple tenants, extract a
    # tenant_id from a request header (e.g. X-Tenant-ID) or a JWT claim here.
    tenant = get_tenant_context("default")

    # ── Per-tenant rate limiting ──────────────────────────────────────────────
    limiter = get_rate_limiter()
    allowed, retry_after = limiter.check(
        tenant_id           = tenant.tenant_id,
        requests_per_minute = tenant.requests_per_minute,
        requests_per_day    = tenant.requests_per_day,
    )
    if not allowed:
        response.headers["Retry-After"] = str(retry_after)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded for tenant '{tenant.tenant_id}'. "
                f"Please retry after {retry_after} second(s)."
            ),
        )

    # ── Route to agent ────────────────────────────────────────────────────────
    conversation_id = request.conversation_id or str(uuid.uuid4())

    try:
        reply, card_data, payment_method = await route_chat(
            db              = db,
            conversation_id = conversation_id,
            message         = request.message,
            model_override  = request.model,
            tenant_id       = tenant.tenant_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        conversation_id = conversation_id,
        reply           = reply,
        product         = card_data,
        payment_method  = payment_method,
    )
