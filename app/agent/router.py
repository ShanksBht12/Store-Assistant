"""
router.py — Agent router: resolves tenant + LLM provider + tool registry,
then delegates to the business-agnostic agent loop.

WHAT THIS FILE DOES
  1. Resolves TenantContext from the DB for the active tenant.
  2. Resolves the LLMProvider for that tenant via get_llm_provider_for_tenant().
     Resolution order: tenant DB fields (llm_provider/api_key/api_base/model)
     → process-level env vars. No per-request model override exists — the model
     is always determined server-side from tenant configuration.
  3. Instantiates the correct ToolRegistry for that tenant's business type.
  4. Delegates to handle_chat_message() with all three injected.

WHY THE REGISTRY AND PROVIDER ARE CONSTRUCTED HERE (not in agent.py)
  agent.py is business-agnostic — it must not import RetailToolRegistry,
  any retail ORM, or any concrete LLM provider. The router is the composition
  root: it knows about all concrete implementations and wires them together
  based on tenant configuration.

ADDING A NEW BUSINESS TYPE
  1. Write app/agent/agency_registry.py implementing ToolRegistry.
  2. Add a `business_type` field to TenantConfig.
  3. Add a branch here: if tenant.business_type == "agency": registry = AgencyToolRegistry(tenant)
  agent.py, prompt.py, and the LLM provider layer stay completely unchanged.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.agent import handle_chat_message
from app.agent.retail_registry import RetailToolRegistry
from app.config import get_tenant_context
from app.providers.llm import get_llm_provider_for_tenant


async def route_chat(
    db:              Session,
    conversation_id: str,
    message:         str,
    tenant_id:       str = "default",
) -> tuple[str, dict | None, str | None]:
    """
    Main router function called by the API endpoint (chat.py).

    Steps:
      1. Resolve TenantContext (prompt rendering, phone/payment rules, LLM config).
      2. Resolve LLMProvider for this tenant (tenant DB config → env var fallback).
      3. Instantiate the correct ToolRegistry for this tenant's business type.
      4. Delegate to handle_chat_message() with all three injected.

    Returns (reply_text, card_data_or_None, payment_method_or_None).
    """
    tenant   = get_tenant_context(tenant_id)
    llm      = get_llm_provider_for_tenant(tenant)
    registry = RetailToolRegistry(tenant)

    return await handle_chat_message(
        db              = db,
        conversation_id = conversation_id,
        message         = message,
        registry        = registry,
        tenant          = tenant,
        llm             = llm,
    )
