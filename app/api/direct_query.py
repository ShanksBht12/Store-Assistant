"""
direct_query.py — POST /api/ask endpoint.

Standalone "ask anything, get Markdown back" feature.
Completely separate from the sales-agent chat flow:
  - No tools, no DB queries, no conversation memory.
  - Uses the same LLMProvider abstraction as /api/chat.
  - Returns answer in Markdown at the requested length.
  - Rate-limited per tenant using the same TenantRateLimiter as /api/chat.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.agent.direct_query import generate_direct_answer
from app.agent.rate_limiter import get_rate_limiter
from app.api.chat import _resolve_tenant
from app.database.database import get_db
from app.schemas.direct_query import DirectQueryRequest, DirectQueryResponse

router = APIRouter(tags=["Direct Query"])


@router.post("/api/ask", response_model=DirectQueryResponse)
async def ask(
    payload:      DirectQueryRequest,
    response:     Response,
    db:           Session = Depends(get_db),
    x_tenant_id:  str | None = Header(
        default=None,
        alias="X-Tenant-ID",
        description="Optional tenant identifier. Omit to use the default tenant.",
    ),
) -> DirectQueryResponse:
    """
    Answer any question directly via the LLM, formatted as Markdown.

    - No tool calls, no DB access, no conversation history.
    - Use `length` to control response size: short / medium / long.
    - Use `max_words` to set a precise word-count cap (overrides `length`).
    - Rate-limited per tenant (same limits as /api/chat).
    """
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

    # ── Generate answer ───────────────────────────────────────────────────────
    try:
        answer_markdown, length_used = await generate_direct_answer(
            question  = payload.question,
            length    = payload.length,
            max_words = payload.max_words,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return DirectQueryResponse(
        answer_markdown = answer_markdown,
        length_used     = length_used,
    )
