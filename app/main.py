from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, health, products
from app.config import get_settings
from app.database.database import Base, engine

settings = get_settings()

# Phase 1: create tables on startup if they don't exist yet.
# (A real migration tool like Alembic is a good Phase-2+ addition.)
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

# Allow the Vite dev server (frontend/) to call this API in local development.
# Tighten this list before deploying anywhere public.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(products.router)


@app.get("/")
def root():
    return {"message": f"{settings.APP_NAME} is running. See /docs for the API."}
