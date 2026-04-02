"""
api/routes/health.py — Health check endpoint.

GET /health → trả về status của tất cả services: llama-server chat/embed + Qdrant.
Dùng để readiness probe trong Docker và K8s.
"""

import httpx
import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from src.config import settings

router = APIRouter()
logger = structlog.get_logger(__name__)


class ServiceStatus(BaseModel):
    status: str  # "ok" | "error"
    detail: str = ""


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "down"
    services: dict[str, ServiceStatus]


async def _check_llamacpp(url: str, name: str) -> ServiceStatus:
    """Ping llama-server /health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Strip /v1 suffix để lấy base URL, dùng removesuffix (Python 3.9+)
            base = url.removesuffix("/v1").removesuffix("/")
            r = await client.get(f"{base}/health")
            if r.status_code == 200:
                return ServiceStatus(status="ok")
            return ServiceStatus(status="error", detail=f"HTTP {r.status_code}")
    except Exception as e:
        return ServiceStatus(status="error", detail=str(e))


async def _check_qdrant() -> ServiceStatus:
    """Ping Qdrant /healthz endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.qdrant_url}/healthz")
            if r.status_code == 200:
                return ServiceStatus(status="ok")
            return ServiceStatus(status="error", detail=f"HTTP {r.status_code}")
    except Exception as e:
        return ServiceStatus(status="error", detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check tất cả downstream services.
    Returns 200 kể cả khi services degraded (để K8s không restart liên tục).
    """
    chat_status = await _check_llamacpp(settings.llamacpp_chat_url, "chat")
    embed_status = await _check_llamacpp(settings.llamacpp_embed_url, "embed")
    qdrant_status = await _check_qdrant()

    services = {
        "llamacpp_chat": chat_status,
        "llamacpp_embed": embed_status,
        "qdrant": qdrant_status,
    }

    all_ok = all(s.status == "ok" for s in services.values())
    overall = "ok" if all_ok else "degraded"

    logger.debug("Health check", overall=overall)
    return HealthResponse(status=overall, services=services)
