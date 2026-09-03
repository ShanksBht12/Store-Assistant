"""OpenAI provider using OpenAI's native chat completions API.

Note: OpenAI's API shape is what Groq's is modeled after, so this file
looks a lot like groq.py -- but they are separate services with separate
keys. An OPENAI_API_KEY will never work against Groq's endpoint and
vice versa, even though the request/response JSON looks almost identical.
"""
from typing import Any

import httpx

from app.config import get_settings
from app.providers.llm.base import LLMProvider

class OpenAIProvider(LLMProvider):
    # extends LLMProvider -- this is what makes it "an LLMProvider" as far
    # as agent.py/orchestrator.py are concerned. They never import THIS
    # class by name; they only ever call get_llm_provider(), which decides
    # whether to hand back this or GroqProvider.

    def __init__(self):
        # Read settings inside __init__ so the cached singleton is resolved
        # at instantiation time (after .env is fully loaded), not at module
        # import time.
        s = get_settings()

        # Fail loudly and immediately if the key is missing, rather than
        # letting the app start and only discovering the problem on the
        # first real chat request.
        if not s.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your .env file -- "
                "never hard-code it in source."
            )
        self.api_key = s.OPENAI_API_KEY
        # https://openrouter.ai/api/v1 when using OpenRouter, or
        # https://api.openai.com/v1 for native OpenAI -- kept as a setting
        # so you can switch providers without touching code.
        self.base_url = s.OPENAI_API_BASE.rstrip("/")
        # e.g. "openai/gpt-4o-mini" for OpenRouter, "gpt-4o-mini" for native OpenAI.
        self.model = s.OPENAI_MODEL
        self.max_output_tokens = s.MAX_OUTPUT_TOKENS
        # Detect whether we're talking to OpenRouter so we can add the
        # required HTTP-Referer header (OpenRouter returns 401 without it).
        self._is_openrouter = "openrouter.ai" in self.base_url

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Leading underscore = private to this class. Nothing outside
        # OpenAIProvider should ever call _post() directly -- the rest of
        # the app is only allowed to depend on chat() (see base.py's notes
        # on encapsulation).
        headers = {
            # OpenAI (and OpenRouter) authenticate via a Bearer token.
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self._is_openrouter:
            # OpenRouter requires HTTP-Referer; without it the request is
            # rejected with 401. X-Title is optional but helps identify
            # your app in the OpenRouter dashboard.
            headers["HTTP-Referer"] = "http://localhost:8000"
            headers["X-Title"] = "ai-business-agent"
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
                # Raises an httpx.HTTPStatusError for any 4xx/5xx response
                # (e.g. 401 = bad/wrong-service key, 429 = rate limited) so
                # it gets caught and re-raised below with more context,
                # instead of silently continuing with a broken `response`.
                if not response.is_success:
                    # Log the full body so we can see exactly what OpenRouter rejected
                    try:
                        detail = response.json()
                    except Exception:
                        detail = response.text
                    raise RuntimeError(
                        f"OpenAI API request failed: {response.status_code} — {detail}"
                    )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"OpenAI API request failed: {exc}") from exc
        return response.json()

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """The one method LLMProvider requires. generate() is inherited from
        the base class -- same as GroqProvider, we don't redefine it here."""
        payload: dict[str, Any] = {
            "model": self.model,
            # `messages` is the full running conversation (system + user +
            # assistant + tool turns) that agent.py built and loaded from
            # ConversationState -- this class doesn't know or care about
            # that history logic, it just forwards whatever it's given.
            "messages": messages,
            "max_tokens": self.max_output_tokens,
            # No "reasoning_format" key here -- that's a Groq-specific
            # param for their reasoning models (deepseek-r1-distill-*,
            # qwen-qwq-*). OpenAI's API doesn't know this field; sending it
            # would likely cause a 400 error, so it's simply omitted rather
            # than copied over from groq.py.
        }
        if tools:
            # Only attach tools/tool_choice when tools were actually passed
            # in -- sending an empty tools list to some APIs behaves
            # differently than omitting the key entirely, so this keeps the
            # payload minimal for tool-free calls (e.g. generate()'s
            # single-shot usage, which calls chat() with no tools arg).
            payload["tools"] = tools
            # "auto" = let the model itself decide whether to call a tool
            # or just answer directly, per turn.
            payload["tool_choice"] = "auto"

        data = await self._post(payload)
        # OpenAI (like Groq) can return multiple candidate completions in
        # `choices`; we only ever request/use the first one.
        choice = data["choices"][0]
        # "stop" = finished normally. "length" = got cut off because it hit
        # max_tokens mid-response. "tool_calls" = it stopped to call a tool.
        finish_reason = choice.get("finish_reason")
        # The actual assistant turn -- may have "content" (plain text),
        # "tool_calls" (a list of functions it wants to call), or both.
        message = choice["message"]

        # Defensive check: if it got cut off (finish_reason == "length")
        # AND produced neither text nor a tool call, there's nothing useful
        # to hand back -- raise clearly instead of returning an empty
        # message that generate()/agent.py would have to guess about.
        if finish_reason == "length" and not message.get("content") and not message.get(
            "tool_calls"
        ):
            raise RuntimeError(
                "OpenAI response was truncated before producing content or a "
                f"tool call (finish_reason=length). Raise MAX_OUTPUT_TOKENS. "
                f"model={self.model!r}"
            )

        # Handed back as-is to agent.py, which reads .get("content") and
        # .get("tool_calls") itself -- this class doesn't interpret the
        # message any further than the truncation check above.
        return message

    # No _clean_content() override here. That's intentional, not an
    # oversight: _clean_content() is the hook base.py's generate() calls to
    # let a provider do its own post-processing (see groq.py, which
    # overrides it to strip hidden <think> tags). OpenAI's standard chat
    # models don't leak that kind of artifact, so the base class's no-op
    # default (just returns the content unchanged) is already correct --
    # there's nothing OpenAI-specific to add.