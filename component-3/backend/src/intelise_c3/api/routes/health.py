"""Service liveness endpoint."""

from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Stable response contract for the Component 3 liveness endpoint."""

    service_name: Literal["intelise-component-3"]
    status: Literal["healthy"]
    api_version: Literal["v1"]


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check Component 3 API liveness",
)
async def health() -> HealthResponse:
    """Report API liveness without contacting Ollama or other components."""
    return HealthResponse(
        service_name="intelise-component-3",
        status="healthy",
        api_version="v1",
    )
