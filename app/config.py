"""
Centralized configuration, loaded from environment variables.
Nothing sensitive (API keys, DB passwords) is ever hard-coded here.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Providers ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
    DATABASE_PROVIDER: str = os.getenv("DATABASE_PROVIDER", "sqlite")

    # --- Grok / xAI ---
    GROK_API_KEY: str = os.getenv("GROK_API_KEY", "")
    GROK_API_BASE: str = os.getenv("GROK_API_BASE", "https://api.x.ai/v1")
    GROK_MODEL: str = os.getenv("GROK_MODEL", "grok-4")

    # --- Groq ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_API_BASE: str = os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")

        # --- OpenAI ---
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    # --- Token guardrails (enforced fully starting Phase 7, but the
    # config keys exist from Phase 1 so nothing needs to change later) ---
    MAX_INPUT_TOKENS: int = int(os.getenv("MAX_INPUT_TOKENS", "4000"))
    MAX_OUTPUT_TOKENS: int = int(os.getenv("MAX_OUTPUT_TOKENS", "1000"))

    # --- App ---
    APP_NAME: str = os.getenv("APP_NAME", "ai-business-agent")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"


@lru_cache
def get_settings() -> Settings:
    return Settings()
