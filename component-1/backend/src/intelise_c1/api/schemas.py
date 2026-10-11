"""Typed API response contracts."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    component: Literal["component-1"] = "component-1"
    service: Literal["requirement-engineering"] = "requirement-engineering"
