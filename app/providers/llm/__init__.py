"""
providers/llm/__init__.py — LLM provider factory.

Reads the LLM_PROVIDER setting from the environment (.env) and returns
the matching provider instance:
  'groq'    → GroqProvider         (default — uses GROQ_API_KEY)
  'openai'  → OpenAIProvider       (uses OPENAI_API_KEY)
  'generic' → GenericOpenAIProvider (uses GENERIC_API_KEY/BASE/MODEL — works with
               any OpenAI-compatible endpoint: OpenRouter, Ollama, Mistral, Together, etc.)
  'mock'    → MockLLMProvider      (no API key needed, returns canned responses for testing)

Usage: from app.providers.llm import get_llm_provider
"""

from functools import lru_cache

from app.config import get_settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.generic import GenericOpenAIProvider
from app.providers.llm.groq import GroqProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai_provider import OpenAIProvider

settings = get_settings()


@lru_cache
def get_llm_provider() -> LLMProvider:
    """
    Provider factory — the ONLY place that knows about concrete provider classes.
    Everything else depends on the LLMProvider interface.

    @lru_cache means the provider is instantiated once per process.
    Changing LLM_PROVIDER in .env requires a server restart to take effect.
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