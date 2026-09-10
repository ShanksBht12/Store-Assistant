"""
Centralized configuration, loaded from environment variables.
Nothing sensitive (API keys, DB passwords) is ever hard-coded here.

Provider quick-reference
  LLM_PROVIDER=groq     → GroqProvider     (GROQ_API_KEY, GROQ_MODEL)
  LLM_PROVIDER=openai   → OpenAIProvider   (OPENAI_API_KEY, OPENAI_MODEL, OPENAI_API_BASE)
  LLM_PROVIDER=generic  → GenericOpenAIProvider — works with ANY OpenAI-compatible endpoint:
                           GENERIC_API_KEY, GENERIC_API_BASE, GENERIC_MODEL
                           e.g. OpenRouter, Ollama, Mistral, Together AI, Anthropic via proxy
  LLM_PROVIDER=mock     → MockLLMProvider  (no key needed, for local testing)

Router / per-request model override
  Send {"model": "anthropic/claude-3-5-sonnet"} in the chat request body to
  override the default model for that turn only (router.py handles this).
"""
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, List

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


class Settings:
    # ── Provider selection ────────────────────────────────────────────────────
    LLM_PROVIDER: str = (
        _env("LLM_PROVIDER")
        or ("openai" if _env("OPENAI_API_KEY") else "mock")
    ).strip().lower()
    DATABASE_PROVIDER: str = _env("DATABASE_PROVIDER", "sqlite")

    # ── Groq ──────────────────────────────────────────────────────────────────
    GROQ_API_KEY:  str = _env("GROQ_API_KEY", "")
    GROQ_API_BASE: str = _env("GROQ_API_BASE", "https://api.groq.com/openai/v1")
    GROQ_MODEL:    str = _env("GROQ_MODEL", "qwen/qwen3.6-27b")

    # ── OpenAI (also works for OpenRouter when OPENAI_API_BASE is set) ────────
    OPENAI_API_KEY:  str = _env("OPENAI_API_KEY", "")
    OPENAI_API_BASE: str = _env("OPENAI_API_BASE", "https://api.openai.com/v1")
    OPENAI_MODEL:    str = _env("OPENAI_MODEL", "gpt-4o-mini")

    # ── Generic — any OpenAI-compatible endpoint ──────────────────────────────
    # Examples:
    #   OpenRouter:  GENERIC_API_BASE=https://openrouter.ai/api/v1
    #                GENERIC_MODEL=anthropic/claude-3-5-sonnet
    #   Ollama:      GENERIC_API_BASE=http://localhost:11434/v1
    #                GENERIC_API_KEY=none
    #                GENERIC_MODEL=ollama/llama3.2
    #   Mistral:     GENERIC_API_BASE=https://api.mistral.ai/v1
    #                GENERIC_MODEL=mistral/mistral-large-latest
    GENERIC_API_KEY:     str = _env("GENERIC_API_KEY", "")
    GENERIC_API_BASE:    str = _env("GENERIC_API_BASE", "")
    GENERIC_MODEL:       str = _env("GENERIC_MODEL", "")
    # Optional JSON dict of extra headers, e.g. '{"HTTP-Referer":"http://localhost:8000"}'
    GENERIC_EXTRA_HEADERS: str = _env("GENERIC_EXTRA_HEADERS", "")

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = _env("DATABASE_URL", "sqlite:///./app.db")

    # ── Token limits ─────────────────────────────────────────────────────────
    MAX_INPUT_TOKENS:  int = int(_env("MAX_INPUT_TOKENS",  "4000"))
    MAX_OUTPUT_TOKENS: int = int(_env("MAX_OUTPUT_TOKENS", "1000"))

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str  = _env("APP_NAME", "ai-business-agent")
    DEBUG:    bool = _env("DEBUG", "true").lower() == "true"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ── TenantContext ─────────────────────────────────────────────────────────────
# Resolved at request time from the tenant_configs DB table.
# Passed into tools and the prompt renderer so all region/business-specific
# config comes from here, not from module-level constants in tools.py.

@dataclass
class TenantContext:
    tenant_id:           str
    display_name:        str
    phone_regex:         str
    phone_hint:          str
    payment_methods:     List[str]
    digital_payments:    List[str]
    currency:            str
    locale:              str
    product_taxonomy:    str
    prompt_template:     str | None
    requests_per_minute: int = 20    # 0 = unlimited
    requests_per_day:    int = 1000  # 0 = unlimited
    # Per-tenant LLM overrides — None means fall back to process-level env vars
    llm_provider:        str | None = None
    llm_api_key:         str | None = None
    llm_api_base:        str | None = None
    llm_model:           str | None = None
    # Which ToolRegistry adapter to use — resolved by registry_factory.build_registry()
    registry_type:       str = "retail"


def _BUILTIN_DEFAULT() -> "TenantContext":
    """Return the built-in generic TenantContext used when no DB row exists."""
    return TenantContext(
        tenant_id            = "default",
        display_name         = "My Store",
        phone_regex          = r"^\+?\d{7,15}$",
        phone_hint           = "Please enter a valid phone number (7–15 digits).",
        payment_methods      = ["card", "cash on delivery"],
        digital_payments     = [],
        currency             = "USD",
        locale               = "en-US",
        product_taxonomy     = "",
        prompt_template      = None,
        requests_per_minute  = 20,
        requests_per_day     = 1000,
        llm_provider         = None,
        llm_api_key          = None,
        llm_api_base         = None,
        llm_model            = None,
        registry_type        = "retail",
    )


def _row_to_context(row: Any) -> "TenantContext":
    """Convert a TenantConfig ORM row to a TenantContext dataclass."""
    return TenantContext(
        tenant_id            = row.tenant_id,
        display_name         = row.display_name,
        phone_regex          = row.phone_regex,
        phone_hint           = row.phone_hint,
        payment_methods      = list(row.payment_methods or []),
        digital_payments     = list(row.digital_payments or []),
        currency             = row.currency,
        locale               = row.locale,
        product_taxonomy     = row.product_taxonomy or "",
        prompt_template      = row.prompt_template,
        requests_per_minute  = row.requests_per_minute,
        requests_per_day     = row.requests_per_day,
        llm_provider         = row.llm_provider,
        llm_api_key          = row.llm_api_key,
        llm_api_base         = row.llm_api_base,
        llm_model            = row.llm_model,
        registry_type        = row.registry_type or "retail",
    )


def find_tenant_context(tenant_id: str) -> "TenantContext | None":
    """
    Look up TenantContext for the given tenant_id from the database.

    Returns None if:
      - the DB is unavailable
      - no row exists for tenant_id
      - the row exists but is_active=0

    Does NOT fall back to a built-in default — the caller decides what to
    do when None is returned (raise 404, use a default, etc.).

    Use this when you need an unambiguous found/not-found signal, e.g. at
    the API boundary where a missing tenant should be a 404, not a silent
    fallback to the generic config.
    """
    try:
        from app.database.database import SessionLocal
        from app.database.models import TenantConfig
        db = SessionLocal()
        try:
            row = db.get(TenantConfig, tenant_id)
            if row and row.is_active:
                return _row_to_context(row)
            return None
        finally:
            db.close()
    except Exception:
        return None


def get_tenant_context(tenant_id: str = "default") -> "TenantContext":
    """
    Load TenantContext for the given tenant_id from the database.
    Falls back to the built-in default if the DB is unavailable or the
    row does not exist — so the system always has a working configuration.

    Use this for internal callers (router.py, PromptRegistry) where a
    safe fallback is acceptable. For API-boundary lookup where a missing
    tenant should produce a 404, use find_tenant_context() instead.
    """
    result = find_tenant_context(tenant_id)
    if result is not None:
        return result
    return _BUILTIN_DEFAULT()
