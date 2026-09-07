"""
providers/llm/groq.py — Groq LLM provider.

Sends chat messages to Groq's OpenAI-compatible API (llama-3, mixtral, etc.)
and parses the response including any tool/function calls the model makes.
Uses GROQ_API_KEY and GROQ_MODEL from the environment.

This is the default provider used in production.
"""

import re
from typing import Any

import httpx

from app.config import get_settings
from app.providers.llm.base import LLMProvider

settings = get_settings()


class GroqProvider(LLMProvider):
    def __init__(self):
        if not settings.GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file -- "
                "never hard-code it in source."
            )
        self.api_key = settings.GROQ_API_KEY
        self.base_url = settings.GROQ_API_BASE
        self.model = settings.GROQ_MODEL

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Private helper (leading underscore = not part of the public
        interface, an internal implementation detail of THIS provider only).
        Nothing outside this class should ever call _post() directly --
        that's encapsulation: the HTTP/auth mechanics are hidden behind
        chat(), which is the only thing the rest of the app is allowed to
        depend on."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Groq API request failed: {exc}") from exc
        return response.json()

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """This is the ONE method LLMProvider actually requires. Everything
        else this class needs (generate(), the empty-completion check) is
        inherited from the base class -- we don't redefine it here, which is
        exactly what stops that logic from being duplicated per-provider."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": settings.MAX_OUTPUT_TOKENS,
            "reasoning_format": "hidden",
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        data = await self._post(payload)
        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason")
        message = choice["message"]

        # Reasoning models can burn their whole token budget on hidden
        # "thinking" and return neither content nor a tool call. Surface
        # that clearly instead of handing the base class a dead message it
        # has no way to explain.
        if finish_reason == "length" and not message.get("content") and not message.get(
            "tool_calls"
        ):
            raise RuntimeError(
                "Groq response was truncated before producing content or a "
                "tool call (finish_reason=length). Raise MAX_OUTPUT_TOKENS or "
                f"switch to a non-reasoning model. model={self.model!r}"
            )

        return message

    def _clean_content(self, content: str) -> str:
        """Groq-specific post-processing only -- this is the hook the base
        class's generate() calls. Nothing else in this class needs to
        change if this logic ever changes; nothing outside this class needs
        to know this logic exists at all. That's encapsulation: the
        Groq-specific quirk (occasionally leaking hidden reasoning, or
        markdown bold despite being told not to) is contained to exactly
        the one place that knows about it."""
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
        content = content.replace("**", "")
        return content