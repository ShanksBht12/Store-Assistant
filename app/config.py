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
from typing import List

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


def get_tenant_context(tenant_id: str = "default") -> "TenantContext":
    """
    Load TenantContext for the given tenant_id from the database.
    Falls back to a safe built-in default if the DB is unavailable or the
    row does not exist — so the system always has a working configuration.

    Call this once per request in router.py and pass the result into the
    agent and tools. Do NOT cache the result long-term; tenant config can
    be updated at runtime via the DB without a restart.
    """
    try:
        from app.database.database import SessionLocal
        from app.database.models import TenantConfig
        db = SessionLocal()
        try:
            row = db.get(TenantConfig, tenant_id)
            if row and row.is_active:
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
                )
        finally:
            db.close()
    except Exception:
        pass  # DB unavailable — fall through to built-in default

    # ── Built-in fallback (generic, no region assumptions) ────────────────────
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
    )
