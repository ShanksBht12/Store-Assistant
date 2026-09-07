"""
router.py — Agent router: acknowledges the request, picks the right LLM
configuration, configures DSPy, and hands off to the agent loop.

WHY A ROUTER?
  Instead of the API endpoint calling handle_chat_message() directly with
  a hard-wired provider, the router sits in between and:
    1. Acknowledges the incoming request (validates, logs, enriches).
    2. Selects the model configuration — either from the request itself
       (if the caller supplies a model override) or from the environment
       defaults (LLM_PROVIDER / GENERIC_MODEL etc.).
    3. Configures DSPy's global LM to match the chosen model so the
       SalesAgentModule in prompt.py always uses the right backend.
    4. Delegates to handle_chat_message() in agent.py.

MODEL SELECTION PRIORITY (highest → lowest):
  1. Request-level override  — caller sends {"model": "anthropic/claude-3-5-sonnet"}
  2. Conversation-level      — first message in the session locked the model
  3. Environment default     — LLM_PROVIDER + matching key/base in .env

ADDING A NEW MODEL:
  No code changes needed. Just set in .env (or send in the request body):
    model=openai/gpt-4o          → native OpenAI
    model=groq/llama-3.1-70b     → Groq
    model=anthropic/claude-3-5-sonnet  → via OpenRouter
    model=ollama/llama3.2        → local Ollama
  The router maps the model string to the correct provider credentials
  via _resolve_lm() below.
"""
from __future__ import annotations

import dspy
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from app.agent.agent import handle_chat_message
from app.config import get_settings
from app.database.models import Product

settings = get_settings()


# ── DSPy LM cache ─────────────────────────────────────────────────────────────
# DSPy LM objects are somewhat expensive to construct (they validate the model
# string via LiteLLM). Cache by model string so we don't rebuild on every turn.

@lru_cache(maxsize=16)
def _build_dspy_lm(model: str, api_base: str | None, api_key: str | None) -> dspy.LM:
    """
    Build and cache a dspy.LM for a given model + endpoint combination.

    DSPy uses LiteLLM under the hood, which accepts model strings in the form
    "provider/model-name" (e.g. "openai/gpt-4o", "groq/llama-3.1-70b").
    For custom endpoints (Ollama, OpenRouter) we pass api_base and api_key
    as extra kwargs that LiteLLM forwards.
    """
    kwargs: dict[str, Any] = {
        "model":      model,
        "max_tokens": settings.MAX_OUTPUT_TOKENS,
        "cache":      False,   # disable DSPy's built-in cache (we manage our own history)
    }
    if api_base:
        kwargs["api_base"] = api_base
    if api_key:
        kwargs["api_key"] = api_key
    return dspy.LM(**kwargs)


def _resolve_lm(model_override: str | None = None) -> dspy.LM:
    """
    Given an optional per-request model override, return the right dspy.LM.

    Priority:
      1. model_override (from the request body)
      2. Environment-configured defaults (LLM_PROVIDER → groq/openai/generic)
    """
    if model_override:
        # Caller supplied an explicit model string like "anthropic/claude-3-5-sonnet"
        # or "ollama/llama3.2". We use the GENERIC credentials (api_base/api_key)
        # as the default auth, unless the model prefix already implies a known provider.
        prefix = model_override.split("/")[0].lower() if "/" in model_override else ""

        if prefix == "groq":
            return _build_dspy_lm(model_override, settings.GROQ_API_BASE, settings.GROQ_API_KEY)
        if prefix in ("openai", "gpt"):
            return _build_dspy_lm(model_override, settings.OPENAI_API_BASE, settings.OPENAI_API_KEY)
        if prefix == "ollama":
            # Ollama runs locally, no key needed
            ollama_base = settings.GENERIC_API_BASE or "http://localhost:11434/v1"
            return _build_dspy_lm(model_override, ollama_base, "none")
        # Everything else (anthropic via OpenRouter, mistral, together, etc.)
        return _build_dspy_lm(
            model_override,
            settings.GENERIC_API_BASE or None,
            settings.GENERIC_API_KEY or None,
        )

    # No override — use the environment-configured provider
    provider = settings.LLM_PROVIDER.lower()
    if provider == "groq":
        model = f"groq/{settings.GROQ_MODEL}"
        return _build_dspy_lm(model, settings.GROQ_API_BASE, settings.GROQ_API_KEY)
    if provider == "openai":
        model = f"openai/{settings.OPENAI_MODEL}"
        return _build_dspy_lm(model, settings.OPENAI_API_BASE, settings.OPENAI_API_KEY)
    if provider == "generic":
        return _build_dspy_lm(
            settings.GENERIC_MODEL,
            settings.GENERIC_API_BASE or None,
            settings.GENERIC_API_KEY or None,
        )
    # mock / fallback — use a cheap model so DSPy doesn't error during import
    return _build_dspy_lm("openai/gpt-4o-mini", None, "mock-key")


# ── Public entry point ────────────────────────────────────────────────────────

async def route_chat(
    db: Session,
    conversation_id: str,
    message: str,
    model_override: str | None = None,
) -> tuple[str, Product | None, str | None]:
    """
    Main router function. Called by the API endpoint (chat.py) instead of
    calling handle_chat_message() directly.

    Steps:
      1. Resolve the DSPy LM for this request.
      2. Apply it as a task-scoped DSPy context (dspy.context) so it is safe
         in async FastAPI — dspy.configure() is global and can only be called
         from the main thread; dspy.context() is per-task and thread-safe.
      3. Delegate to the agent loop inside that context.
      4. Return (reply, product, payment_method) unchanged.

    Args:
        db:              SQLAlchemy session (injected by FastAPI).
        conversation_id: UUID string identifying the conversation.
        message:         The customer's latest message.
        model_override:  Optional model string ("anthropic/claude-3-5-sonnet",
                         "ollama/llama3.2", etc.). Overrides the .env default
                         for this turn only.

    Returns:
        Tuple of (reply_text, product_or_None, payment_method_or_None)
        — same as handle_chat_message().
    """
    # ── Step 1: resolve DSPy LM for this request ──────────────────────────────
    lm = _resolve_lm(model_override)

    # ── Step 2: apply LM as a task-scoped context (async-safe) ───────────────
    # dspy.configure() is global and raises a warning when called from async
    # tasks other than the one that first called it.
    # dspy.context() is a synchronous context manager that overrides the LM
    # for the duration of this block only — it sets a thread-local, not global
    # state, so it is safe to call from any async task.
    with dspy.context(lm=lm):
        return await handle_chat_message(db, conversation_id, message)
