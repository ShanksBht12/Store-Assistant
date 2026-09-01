"""
Centralized configuration, loaded from environment variables.
Nothing sensitive (API keys, DB passwords) is ever hard-coded here.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


class Settings:
    # --- Providers ---
    LLM_PROVIDER: str = (
        _env("LLM_PROVIDER")
        or ("openai" if _env("OPENAI_API_KEY") else "mock")
    ).strip().lower()
    DATABASE_PROVIDER: str = _env("DATABASE_PROVIDER", "sqlite")

    # --- Groq ---
    GROQ_API_KEY: str = _env("GROQ_API_KEY", "")
    GROQ_API_BASE: str = _env("GROQ_API_BASE", "https://api.groq.com/openai/v1")
    GROQ_MODEL: str = _env("GROQ_MODEL", "qwen/qwen3.6-27b")

    # --- OpenAI ---
    OPENAI_API_KEY: str = _env("OPENAI_API_KEY", "")
    OPENAI_API_BASE: str = _env("OPENAI_API_BASE", "https://api.openai.com/v1")
    OPENAI_MODEL: str = _env("OPENAI_MODEL", "gpt-4o-mini")

    # --- Database ---
    DATABASE_URL: str = _env("DATABASE_URL", "sqlite:///./app.db")

    # --- Token guardrails (enforced fully starting Phase 7, but the
    # config keys exist from Phase 1 so nothing needs to change later) ---
    MAX_INPUT_TOKENS: int = int(_env("MAX_INPUT_TOKENS", "4000"))
    MAX_OUTPUT_TOKENS: int = int(_env("MAX_OUTPUT_TOKENS", "1000"))

    # --- App ---
    APP_NAME: str = _env("APP_NAME", "ai-business-agent")
    DEBUG: bool = _env("DEBUG", "true").lower() == "true"


@lru_cache
def get_settings() -> Settings:
    return Settings()
