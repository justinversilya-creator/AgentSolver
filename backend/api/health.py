# backend/api/health.py
from fastapi import APIRouter

from backend.config import APP_VERSION, get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "agentsolve-api",
        "version": APP_VERSION,
        "demo_mode": settings.demo_mode,
        "make": {
            "configured": settings.make_configured,
            "reachability_checked": False,
        },
    }