from functools import lru_cache

from app.config import get_settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.groq import GroqProvider
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai_provider import OpenAIProvider

settings = get_settings()


@lru_cache
def get_llm_provider() -> LLMProvider:
    """
    Provider factory. This is the ONLY place that knows about concrete
    provider classes — everything else depends on LLMProvider.

    @lru_cache means this only actually runs once per process -- the same
    provider instance is reused on every call rather than reconstructed per
    request. That also means changing LLM_PROVIDER in .env requires a
    restart to take effect; it won't hot-swap mid-run.
    """
    provider_name = settings.LLM_PROVIDER.lower()

    if provider_name == "groq":
        return GroqProvider()
    if provider_name == "openai":
        return OpenAIProvider()
    if provider_name == "mock":
        return MockLLMProvider()

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider_name}'. Supported: groq, openai, mock."
    )