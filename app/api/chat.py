"""
chat.py — Chat API endpoint.

Exposes:
  POST /api/chat

Request flow:
  1. Identify the tenant from the X-Tenant-ID request header.
     Falls back to "default" when the header is absent, so single-tenant
     deployments need no configuration change.
     Returns HTTP 404 if the header is present but names an unknown/inactive tenant.
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

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.agent.rate_limiter import get_rate_limiter
from app.agent.router import route_chat
from app.config import find_tenant_context, get_tenant_context
from app.database.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["Chat"])


def _resolve_tenant(
    x_tenant_id: str | None,
    db: Session,
):
    """
    Resolve TenantContext from the X-Tenant-ID header.

    - Header absent → use get_tenant_context("default") with its built-in
      fallback, so single-tenant deployments work with no configuration.
    - Header present → use find_tenant_context() which returns None when
      the row is missing or inactive. That produces an unambiguous 404
      rather than silently falling back to a generic config.
    """
    if not x_tenant_id:
        # No header — safe fallback path for single-tenant deploys
        return get_tenant_context("default")

    tenant_id = x_tenant_id.strip()
    tenant = find_tenant_context(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant '{tenant_id}' not found or inactive.",
        )
    return tenant


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    request:      ChatRequest,
    response:     Response,
    db:           Session = Depends(get_db),
    x_tenant_id:  str | None = Header(
        default=None,
        alias="X-Tenant-ID",
        description=(
            "Optional tenant identifier. Omit for single-tenant deployments "
            "(resolves to the 'default' tenant). Supply to route the request "
            "to a specific tenant's configuration, prompt, and LLM credentials."
        ),
    ),
):
    # ── Resolve tenant ────────────────────────────────────────────────────────
    tenant = _resolve_tenant(x_tenant_id, db)

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
