"""Groq provider using Groq's OpenAI-compatible chat API."""
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
        """Phase 2: send a full message history (optionally with tool specs)
        and return the raw assistant message dict -- content, tool_calls, or
        both -- so the caller (app/agent/agent.py) can run the tool loop.
        """
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

        # Same truncation trap as generate() below: a reasoning model can burn
        # its whole token budget on hidden thinking and return neither content
        # nor tool_calls. Surface that instead of handing back a dead message.
        if finish_reason == "length" and not message.get("content") and not message.get(
            "tool_calls"
        ):
            raise RuntimeError(
                "Groq response was truncated before producing content or a "
                "tool call (finish_reason=length). Raise MAX_OUTPUT_TOKENS or "
                f"switch to a non-reasoning model. model={self.model!r}"
            )

        return message

    async def generate(self, system_prompt: str, user_message: str) -> str:
        """Phase 1-style single-shot call, kept for anything that doesn't
        need tools. Implemented on top of chat() so there's one code path."""
        message = await self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
        )
        content = message.get("content") or ""

        if not content.strip():
            raise RuntimeError(
                f"Groq returned an empty completion for model={self.model!r}."
            )

        # Keep model reasoning out of the response if the API returns it anyway.
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
        content = content.replace("**", "")
        return content.strip()