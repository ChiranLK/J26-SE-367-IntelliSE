from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/component-1", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    component: Literal["component-1"] = "component-1"
    service: Literal["requirement-engineering"] = "requirement-engineering"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report API process health only; no external services are checked."""
    return HealthResponse()
