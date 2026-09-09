"""
main.py — FastAPI application entry point.

Responsibilities:
  - Creates the FastAPI app instance
  - Registers CORS middleware (allows the frontend dev server to call the API)
  - Mounts the /api/chat and /api/orders routers
  - Serves the compiled React frontend (frontend/dist/) as static files
    so the whole app (API + UI) runs from a single server process

Start the server with:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import dspy

from app.api import chat, orders, prompts, store
from app.config import get_settings
from app.agent.router import _resolve_lm
from app.database.database import Base, engine

settings = get_settings()

Base.metadata.create_all(bind=engine)

# ── Configure DSPy once at startup from the main thread ──────────────────────
# dspy.configure() must be called from the main thread/task exactly once.
# After this, every async request uses dspy.context(lm=...) to override
# the LM per-task without touching the global state.
try:
    default_lm = _resolve_lm()          # reads LLM_PROVIDER + credentials from .env
    dspy.configure(lm=default_lm)
except Exception as _e:
    # If credentials are missing (e.g. running without .env), skip DSPy config.
    # The agent falls back to raw LLM output when DSPy is unconfigured.
    pass

# ── Seed initial prompt version if table is empty ────────────────────────────
from app.agent.prompt import PromptRegistry
from app.database.seed import seed_store_info, seed_tenant_config
PromptRegistry.seed_initial()
seed_store_info()
seed_tenant_config()

settings = get_settings()

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Store Assistant API",
    description=(
        "Backend for the Store Assistant — an AI-powered shoe store chatbot. "
        "\n\n"
        "**Chat** — send a message and receive a reply from the AI agent.\n\n"
        "**Orders** — admin endpoints to list, view, and update order status."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,  # disable the redundant ReDoc UI
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(chat.router)
app.include_router(orders.router)
app.include_router(prompts.router)
app.include_router(store.router)


@app.options("/api/chat")
async def chat_preflight() -> Response:
    return Response(status_code=200)
