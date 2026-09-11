"""
main.py — FastAPI application entry point.

Responsibilities:
  - Creates the FastAPI app instance
  - Registers CORS middleware (allows the frontend dev server to call the API)
  - Mounts all API routers
  - Creates DB tables on startup and seeds initial data

Start the server with:
    uvicorn app.main:app --reload

NOTE: DSPy (dspy.configure, _resolve_lm) has been removed. The agent loop
uses the LLMProvider ABC directly — there is one model-selection path.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api import chat, orders, prompts, store
from app.api.direct_query import router as direct_query_router
from app.config import get_settings
from app.database.database import Base, engine

settings = get_settings()

Base.metadata.create_all(bind=engine)

# ── Startup seeds ─────────────────────────────────────────────────────────────
from app.agent.prompt import PromptRegistry
from app.database.seed import seed_store_info, seed_tenant_config
PromptRegistry.seed_initial()
seed_store_info()
seed_tenant_config()

app = FastAPI(
    title="Store Assistant API",
    description=(
        "Backend for the Store Assistant — an AI-powered retail chatbot.\n\n"
        "**Chat** — send a message and receive a reply from the AI agent.\n\n"
        "**Orders** — admin endpoints to list, view, and update order status."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
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
app.include_router(direct_query_router)


@app.options("/api/chat")
async def chat_preflight() -> Response:
    return Response(status_code=200)
