"""
router.py — Agent router: resolves tenant + LLM provider + tool registry,
then delegates to the business-agnostic agent loop.

WHAT THIS FILE DOES
  1. Resolves TenantContext from the DB for the active tenant.
  2. Resolves the LLMProvider for that tenant via get_llm_provider_for_tenant().
     Resolution order: tenant DB fields (llm_provider/api_key/api_base/model)
     → process-level env vars. No per-request model override exists — the model
     is always determined server-side from tenant configuration.
  3. Resolves the ToolRegistry for that tenant via build_registry(tenant).
     The registry type is stored in tenant_configs.registry_type in the DB,
     so switching a tenant to a different business type is a DB update only —
     no code change, no restart.
  4. Delegates to handle_chat_message() with all three injected.

WHY THE REGISTRY AND PROVIDER ARE CONSTRUCTED HERE (not in agent.py)
  agent.py is business-agnostic — it must not import any concrete registry,
  retail ORM, or LLM provider. The router is the composition root: it wires
  together the correct implementations based on tenant configuration.

ADDING A NEW BUSINESS TYPE
  1. Write app/agent/<type>_registry.py implementing ToolRegistry.
  2. Register it in app/agent/registry_factory._REGISTRY_MAP.
  3. Set registry_type='<type>' on the tenant row in the DB.
  agent.py, prompt.py, and the LLM provider layer stay completely unchanged.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.agent import handle_chat_message
from app.agent.registry_factory import build_registry
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
      2. Resolve LLMProvider — tenant DB config → env var fallback.
      3. Resolve ToolRegistry — determined by tenant_configs.registry_type in DB.
      4. Delegate to handle_chat_message() with all three injected.

    Returns (reply_text, card_data_or_None, payment_method_or_None).
    """
    tenant   = get_tenant_context(tenant_id)
    llm      = get_llm_provider_for_tenant(tenant)
    registry = build_registry(tenant)

    return await handle_chat_message(
        db              = db,
        conversation_id = conversation_id,
        message         = message,
        registry        = registry,
        tenant          = tenant,
        llm             = llm,
    )
