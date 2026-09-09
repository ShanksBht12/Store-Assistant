"""
providers/llm/__init__.py — LLM provider factory.

RESOLUTION
──────────
get_llm_provider_for_tenant(tenant) is the single entry point for the
request path. It resolves provider, credentials, and model from the
TenantContext built for the active request:

  Resolution order for each field:
    1. tenant.llm_* (set in tenant_configs DB row)
    2. Process-level env var (LLM_PROVIDER, *_API_KEY, *_API_BASE, *_MODEL)

  This means different tenants can use different models, providers, or API
  keys. Changing tenant config in the DB takes effect on the next request —
  no process restart needed. A tenant with no overrides uses the env defaults.

  This function is NOT cached — constructed once per request. Provider
  objects are lightweight (no persistent connection on __init__).

PROVIDER STRINGS
─────────────────
  'groq'    → GroqProvider
  'openai'  → OpenAIProvider
  'generic' → GenericOpenAIProvider   (any OpenAI-compatible endpoint)
  'mock'    → MockLLMProvider
"""
from __future__ import annotations

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
    """
    provider_name = (tenant.llm_provider or settings.LLM_PROVIDER).lower()

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
