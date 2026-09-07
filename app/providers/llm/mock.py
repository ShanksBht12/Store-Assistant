"""
providers/llm/mock.py — Mock LLM provider for testing.

Returns deterministic, canned responses without making any network calls.
Useful for:
  - Running the app locally without a valid API key
  - Writing automated tests that don't depend on external services
  - Debugging the agent loop without burning API credits

Activate by setting LLM_PROVIDER=mock in your .env file.
"""
from typing import Any

from app.providers.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Return a simple assistant reply without invoking any external service."""
        user_text = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_text = str(msg.get("content", ""))
                break

        content = (
            "[mock-llm] Based on the provided context:\n\n"
            f"{messages[-1].get('content', '') if messages else ''}\n\n"
            f"(In response to: {user_text!r})"
        )
        return {"role": "assistant", "content": content}

    async def generate(self, system_prompt: str, user_message: str) -> str:
        return (
            "[mock-llm] Based on the provided context:\n\n"
            f"{system_prompt}\n\n"
            f"(In response to: {user_message!r})"
        )
