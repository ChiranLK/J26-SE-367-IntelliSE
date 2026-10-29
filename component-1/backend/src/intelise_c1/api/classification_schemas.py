"""Classification predictions are separate from the original extraction candidates."""
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requirement_id: str
    label: Literal["FR", "NFR"]


class ClassificationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification_id: str
    project_id: str
    extraction_run_id: str
    model_identifier: str
    model_version: str
    classified_at: AwareDatetime
    predictions: list[Prediction]
