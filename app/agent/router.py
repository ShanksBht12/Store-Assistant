"""
router.py — Agent router: resolves the LLM, the tenant, and the tool registry,
then delegates to the business-agnostic agent loop.

WHAT THIS FILE DOES
  1. Picks the right DSPy LM for the request (env default or per-request override).
  2. Resolves the active TenantContext from the DB.
  3. Instantiates the correct ToolRegistry for that tenant's business type.
     Currently always RetailToolRegistry — future tenants with a different
     business type would get a different registry here based on tenant config.
  4. Calls handle_chat_message() with both, inside a dspy.context() scope.

WHY THE REGISTRY IS CONSTRUCTED HERE (not in agent.py)
  agent.py is business-agnostic — it must not import RetailToolRegistry or
  any retail ORM. The router is the composition root: it knows about both the
  core loop (agent.py) and the available adapters (*_registry.py), and wires
  them together based on configuration.

ADDING A NEW BUSINESS TYPE
  1. Write app/agent/agency_registry.py implementing ToolRegistry.
  2. Add a `business_type` field to TenantConfig (e.g. "retail", "agency").
  3. Add a branch here: if tenant.business_type == "agency": registry = AgencyToolRegistry(tenant)
  agent.py, prompt.py, and the LLM provider layer stay completely unchanged.

MODEL SELECTION PRIORITY (highest → lowest):
  1. Request-level override  — caller sends {"model": "anthropic/claude-3-5-sonnet"}
  2. Environment default     — LLM_PROVIDER + matching key/base in .env
"""
from __future__ import annotations

import dspy
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from app.agent.agent import handle_chat_message
from app.agent.retail_registry import RetailToolRegistry
from app.config import get_settings, get_tenant_context

settings = get_settings()


# ── DSPy LM cache ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=16)
def _build_dspy_lm(model: str, api_base: str | None, api_key: str | None) -> dspy.LM:
    """Build and cache a dspy.LM for a given model + endpoint combination."""
    kwargs: dict[str, Any] = {
        "model":      model,
        "max_tokens": settings.MAX_OUTPUT_TOKENS,
        "cache":      False,
    }
    if api_base:
        kwargs["api_base"] = api_base
    if api_key:
        kwargs["api_key"] = api_key
    return dspy.LM(**kwargs)


def _resolve_lm(model_override: str | None = None) -> dspy.LM:
    """Return the right dspy.LM for this request."""
    if model_override:
        prefix = model_override.split("/")[0].lower() if "/" in model_override else ""
        if prefix == "groq":
            return _build_dspy_lm(model_override, settings.GROQ_API_BASE, settings.GROQ_API_KEY)
        if prefix in ("openai", "gpt"):
            return _build_dspy_lm(model_override, settings.OPENAI_API_BASE, settings.OPENAI_API_KEY)
        if prefix == "ollama":
            ollama_base = settings.GENERIC_API_BASE or "http://localhost:11434/v1"
            return _build_dspy_lm(model_override, ollama_base, "none")
        return _build_dspy_lm(
            model_override,
            settings.GENERIC_API_BASE or None,
            settings.GENERIC_API_KEY or None,
        )

    provider = settings.LLM_PROVIDER.lower()
    if provider == "groq":
        return _build_dspy_lm(f"groq/{settings.GROQ_MODEL}", settings.GROQ_API_BASE, settings.GROQ_API_KEY)
    if provider == "openai":
        return _build_dspy_lm(f"openai/{settings.OPENAI_MODEL}", settings.OPENAI_API_BASE, settings.OPENAI_API_KEY)
    if provider == "generic":
        return _build_dspy_lm(settings.GENERIC_MODEL, settings.GENERIC_API_BASE or None, settings.GENERIC_API_KEY or None)
    return _build_dspy_lm("openai/gpt-4o-mini", None, "mock-key")


# ── Public entry point ────────────────────────────────────────────────────────

async def route_chat(
    db:             Session,
    conversation_id: str,
    message:        str,
    model_override: str | None = None,
    tenant_id:      str = "default",
) -> tuple[str, dict | None, str | None]:
    """
    Main router function called by the API endpoint (chat.py).

    Steps:
      1. Resolve DSPy LM for this request.
      2. Resolve TenantContext (drives prompt rendering + phone/payment rules).
      3. Instantiate the correct ToolRegistry for this tenant's business type.
         Currently always RetailToolRegistry; extend here for future adapters.
      4. Apply LM as a task-scoped dspy.context() (async-safe).
      5. Delegate to handle_chat_message() with registry + tenant injected.

    Returns (reply_text, card_data_or_None, payment_method_or_None).
    """
    lm     = _resolve_lm(model_override)
    tenant = get_tenant_context(tenant_id)

    # ── Registry selection ────────────────────────────────────────────────────
    # This is the composition root for business-type adapters.
    # To add a new business type, add a branch here keyed on a tenant config
    # field (e.g. tenant.business_type) and return the matching registry.
    registry = RetailToolRegistry(tenant)

    with dspy.context(lm=lm):
        return await handle_chat_message(
            db=db,
            conversation_id=conversation_id,
            message=message,
            registry=registry,
            tenant=tenant,
        )
