from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service Health Check")
async def health_check() -> Dict[str, Any]:
    """
    Returns the operational status of Component 4 backend.
    Includes active storage backend information and environment status.
    """
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "storage_backend": settings.STORAGE_BACKEND,
        "is_ephemeral_storage": settings.STORAGE_BACKEND.lower() == "memory",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 1 - Backend Foundation",
    }
