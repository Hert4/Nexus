"""
main.py — FastAPI application entry point.

Khởi tạo app, đăng ký routers, middleware, và lifespan events.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import agents, chat, documents, feedback, health
from src.config import settings
from src.observability.logging import setup_logging
from src.observability.metrics import setup_metrics

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    setup_logging(settings.log_level)
    logger.info("Nexus AI starting", env=settings.app_env)
    yield
    logger.info("Nexus AI shutting down")


app = FastAPI(
    title="Nexus AI",
    description="Local AI Assistant — RAG + Agents via llama.cpp",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ────────────────────────────────────────────────────────
setup_metrics(app)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, tags=["health"])
app.include_router(chat.router, prefix="/v1", tags=["chat"])
app.include_router(documents.router, prefix="/v1", tags=["documents"])
app.include_router(agents.router, prefix="/v1", tags=["agents"])
app.include_router(feedback.router, prefix="/v1", tags=["feedback"])
