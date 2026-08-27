from functools import lru_cache

from app.config import get_settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.groq import GroqProvider
from app.providers.llm.mock import MockLLMProvider

settings = get_settings()


@lru_cache
def get_llm_provider() -> LLMProvider:
    """
    Provider factory. This is the ONLY place that knows about concrete
    provider classes — everything else depends on LLMProvider.
    """
    provider_name = settings.LLM_PROVIDER.lower()

    if provider_name == "groq":
        return GroqProvider()
    if provider_name == "mock":
        return MockLLMProvider()

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider_name}'. Supported: groq, mock."
    )
