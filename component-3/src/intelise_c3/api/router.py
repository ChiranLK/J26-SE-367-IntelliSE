"""Top-level API router composition."""

from fastapi import APIRouter

from intelise_c3.api.routes.design_selection import router as design_selection_router
from intelise_c3.api.routes.generation import router as generation_router
from intelise_c3.api.routes.health import router as health_router
from intelise_c3.api.routes.input_validation import router as input_validation_router
from intelise_c3.api.routes.structural_verification import (
    router as structural_verification_router,
)
from intelise_c3.api.routes.traceability import router as traceability_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(input_validation_router)
api_router.include_router(design_selection_router)
api_router.include_router(generation_router)
api_router.include_router(traceability_router)
api_router.include_router(structural_verification_router)
