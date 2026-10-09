"""Component 01 availability endpoint."""

from fastapi import APIRouter

from intelise_c1.api.schemas import HealthResponse

api_router = APIRouter(prefix="/api/v1/component-1")


@api_router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Report application availability only; no database or AI readiness checks."""
    return HealthResponse()
