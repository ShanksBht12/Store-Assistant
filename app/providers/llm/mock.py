"""
Mock provider — deterministic, no network calls. Useful for tests
and for running the app without a GROK_API_KEY.
"""
from app.providers.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    async def generate(self, system_prompt: str, user_message: str) -> str:
        return (
            "[mock-llm] Based on the provided context:\n\n"
            f"{system_prompt}\n\n"
            f"(In response to: {user_message!r})"
        )
