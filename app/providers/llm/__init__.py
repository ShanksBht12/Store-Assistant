"""
providers/llm/__init__.py — LLM provider factory.

TWO RESOLUTION PATHS
─────────────────────
1. get_llm_provider_for_tenant(tenant)  ← preferred, called by router.py
   Resolves provider, credentials, and model from the TenantContext that was
   built for this request. If the tenant has per-tenant LLM fields set
   (llm_provider, llm_api_key, llm_api_base, llm_model), those win. If any
   field is absent, it falls back to the matching process-level env var.
   This means:
     - Different tenants can use different models, providers, or API keys.
     - Changing a tenant's LLM config via the DB takes effect on the next
       request — no process restart required.
     - A tenant with no LLM overrides behaves exactly as before.

2. get_llm_provider()                   ← backward-compat, process-global
   @lru_cached singleton built entirely from env vars. Still used by the
   DSPy startup path in main.py (dspy.configure). Nothing in the hot
   request path should call this anymore.

PROVIDER STRINGS
─────────────────
  'groq'    → GroqProvider
  'openai'  → OpenAIProvider
  'generic' → GenericOpenAIProvider   (any OpenAI-compatible endpoint)
  'mock'    → MockLLMProvider
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import get_settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.generic import GenericOpenAIProvider
from app.providers.llm.groq import GroqProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai_provider import OpenAIProvider

if TYPE_CHECKING:
    from app.config import TenantContext

settings = get_settings()


def get_llm_provider_for_tenant(tenant: "TenantContext") -> LLMProvider:
    """
    Return an LLMProvider configured for this tenant.

    Resolution order for each field (provider name, api_key, api_base, model):
      1. tenant.llm_* field (set in tenant_configs DB row)
      2. process-level env var (LLM_PROVIDER, *_API_KEY, *_API_BASE, *_MODEL)

    This function is NOT cached — it is called once per request so per-tenant
    config changes in the DB take effect immediately without a restart.
    The provider objects themselves are lightweight (no connection pool held
    on __init__), so constructing one per request is negligible overhead.
    """
    # ── Resolve provider name ─────────────────────────────────────────────────
    provider_name = (tenant.llm_provider or settings.LLM_PROVIDER).lower()

    # ── Resolve credentials falling back to env vars ──────────────────────────
    if provider_name == "groq":
        api_key  = tenant.llm_api_key  or settings.GROQ_API_KEY
        api_base = tenant.llm_api_base or settings.GROQ_API_BASE
        model    = tenant.llm_model    or settings.GROQ_MODEL
        return GroqProvider(api_key=api_key, api_base=api_base, model=model)

    if provider_name == "openai":
        api_key  = tenant.llm_api_key  or settings.OPENAI_API_KEY
        api_base = tenant.llm_api_base or settings.OPENAI_API_BASE
        model    = tenant.llm_model    or settings.OPENAI_MODEL
        return OpenAIProvider(api_key=api_key, api_base=api_base, model=model)

    if provider_name == "generic":
        api_key  = tenant.llm_api_key  or settings.GENERIC_API_KEY
        api_base = tenant.llm_api_base or settings.GENERIC_API_BASE
        model    = tenant.llm_model    or settings.GENERIC_MODEL
        return GenericOpenAIProvider(api_key=api_key, api_base=api_base, model=model)

    if provider_name == "mock":
        return MockLLMProvider()

    raise ValueError(
        f"Unknown LLM provider '{provider_name}' for tenant '{tenant.tenant_id}'. "
        "Supported: groq, openai, generic, mock."
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    """
    Process-global provider singleton built from env vars only.
    Used by the DSPy startup path (dspy.configure in main.py).
    NOT used in the hot request path — use get_llm_provider_for_tenant() there.
    """
    provider_name = settings.LLM_PROVIDER.lower()
    if provider_name == "groq":
        return GroqProvider()
    if provider_name == "openai":
        return OpenAIProvider()
    if provider_name == "generic":
        return GenericOpenAIProvider()
    if provider_name == "mock":
        return MockLLMProvider()
    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider_name}'. "
        "Supported: groq, openai, generic, mock."
    )
