"""Top-level API router composition."""

from fastapi import APIRouter

from intelise_c3.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
