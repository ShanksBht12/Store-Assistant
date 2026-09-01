from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api import chat, orders
from app.config import get_settings
from app.database.database import Base, engine

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


@app.options("/api/chat")
async def chat_preflight() -> Response:
    return Response(status_code=200)
