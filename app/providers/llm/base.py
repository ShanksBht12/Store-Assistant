"""
Abstract interface every LLM provider must implement.

The agent layer depends ONLY on this interface, never on a concrete
provider -- swapping LLM_PROVIDER in the environment should require
zero changes above this file.

DESIGN NOTE (Template Method pattern):
Only `chat()` is abstract. That's the one thing that's genuinely different
between providers -- Groq, OpenAI, Anthropic, etc. all format requests and
tool-calling differently, so each provider MUST write its own `chat()`.

Everything else is the SAME regardless of provider: turn a chat() result
into a plain string, check for an empty completion, raise a clear error.
That logic used to live inside GroqProvider.generate() -- which meant every
new provider added later would have to copy-paste that whole method, and
any future bugfix to it would need to be applied N times, once per
provider, with no guarantee they'd stay in sync. Putting it here ONCE means:
  - a new provider only has to implement chat() (one method, not two)
  - the empty-completion safety check applies uniformly, automatically,
    to every provider without anyone having to remember to add it
  - if a provider needs its own post-processing (e.g. Groq stripping
    hidden <think> tags), it overrides the small `_clean_content()` hook
    instead of re-writing the whole method
"""
from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """
        Send a full message history (optionally with tool specs) to the
        provider's chat API and return the raw assistant message dict
        exactly as the provider returned it -- content, tool_calls, or both.

        This is the ONLY method a concrete provider is required to write.
        `generate()` below is built on top of it and is inherited for free.
        """
        raise NotImplementedError

    async def generate(self, system_prompt: str, user_message: str) -> str:
        """
        Convenience wrapper for simple, tool-free, single-shot calls (e.g.
        Phase 1's "facts in, sentence out" usage). This is CONCRETE, not
        abstract -- it lives here so every provider gets it automatically
        by implementing chat(). Do not override this in a provider; if a
        provider needs different cleanup behavior, override
        `_clean_content()` instead, so the empty-completion check below
        still runs for every provider, not just the ones that remember to
        include it.
        """
        message = await self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
        )
        content = message.get("content") or ""
        content = self._clean_content(content)

        if not content.strip():
            # This is the exact bug that used to silently return "" to the
            # user as a blank chat bubble. Enforcing it here means it's
            # impossible for any provider -- current or future -- to skip it.
            raise RuntimeError(f"{type(self).__name__} returned an empty completion.")

        return content.strip()

    def _clean_content(self, content: str) -> str:
        """
        Extension point (not abstract -- has a safe no-op default) for
        provider-specific text cleanup, e.g. stripping hidden reasoning
        tags a particular model tends to leak. Override this in a subclass
        instead of duplicating all of generate() just to change this one
        step -- that's the encapsulation your supervisor's asking about:
        the varying behavior is isolated to one small, overridable method.
        """
        return content