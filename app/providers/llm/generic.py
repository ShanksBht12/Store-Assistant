"""
providers/llm/generic.py — Universal OpenAI-compatible LLM provider.

Works with ANY model that exposes an OpenAI-compatible /chat/completions endpoint.
This includes (but is not limited to):

  - OpenRouter  → set API_BASE=https://openrouter.ai/api/v1
                  then MODEL can be "anthropic/claude-3-5-sonnet",
                  "google/gemini-flash-1.5", "meta-llama/llama-3.1-70b", etc.
  - Ollama      → set API_BASE=http://localhost:11434/v1, MODEL=llama3.2
  - Together AI → set API_BASE=https://api.together.xyz/v1
  - Mistral     → set API_BASE=https://api.mistral.ai/v1
  - Anthropic   → via OpenRouter (native Anthropic API is NOT OpenAI-compatible)
  - Any other provider that mirrors the OpenAI chat completions spec

Configure via .env:
  LLM_PROVIDER=generic
  GENERIC_API_KEY=<your key>
  GENERIC_API_BASE=<endpoint base URL>
  GENERIC_MODEL=<model string, e.g. "anthropic/claude-3-5-sonnet">
  GENERIC_EXTRA_HEADERS={"HTTP-Referer":"http://localhost:8000"}  # optional JSON
"""
import json
from typing import Any

import httpx

from app.config import get_settings
from app.providers.llm.base import LLMProvider


class GenericOpenAIProvider(LLMProvider):
    """
    Drop-in provider for any OpenAI-compatible endpoint.
    Only chat() needs to be implemented — generate() and _clean_content()
    are inherited from LLMProvider for free.
    """

    def __init__(self):
        s = get_settings()
        if not s.GENERIC_API_KEY:
            raise RuntimeError(
                "GENERIC_API_KEY is not set. Add it to your .env file.\n"
                "If your endpoint requires no key (e.g. local Ollama), set GENERIC_API_KEY=none"
            )
        if not s.GENERIC_API_BASE:
            raise RuntimeError("GENERIC_API_BASE is not set. Add the endpoint base URL to your .env file.")
        if not s.GENERIC_MODEL:
            raise RuntimeError("GENERIC_MODEL is not set. Add the model name to your .env file.")

        self.api_key   = s.GENERIC_API_KEY
        self.base_url  = s.GENERIC_API_BASE.rstrip("/")
        self.model     = s.GENERIC_MODEL
        self.max_tokens = s.MAX_OUTPUT_TOKENS

        # Optional extra headers (e.g. OpenRouter requires HTTP-Referer)
        try:
            self.extra_headers: dict[str, str] = (
                json.loads(s.GENERIC_EXTRA_HEADERS) if s.GENERIC_EXTRA_HEADERS else {}
            )
        except json.JSONDecodeError:
            self.extra_headers = {}

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            # "none" is a sentinel value for keyless local servers (Ollama)
            **({"Authorization": f"Bearer {self.api_key}"} if self.api_key.lower() != "none" else {}),
            **self.extra_headers,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if not response.is_success:
                    try:
                        detail = response.json()
                    except Exception:
                        detail = response.text
                    raise RuntimeError(
                        f"Generic LLM API error: {response.status_code} — {detail}\n"
                        f"endpoint={self.base_url}, model={self.model}"
                    )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Generic LLM HTTP error: {exc}") from exc
        return response.json()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model":      self.model,
            "messages":   messages,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"]       = tools
            payload["tool_choice"] = "auto"

        data   = await self._post(payload)
        choice = data["choices"][0]
        finish = choice.get("finish_reason")
        msg    = choice["message"]

        if finish == "length" and not msg.get("content") and not msg.get("tool_calls"):
            raise RuntimeError(
                f"Generic LLM response truncated (finish_reason=length). "
                f"Raise MAX_OUTPUT_TOKENS. model={self.model!r}"
            )
        return msg
