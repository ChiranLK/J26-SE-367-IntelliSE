"""Bounded provider output and server-owned extraction metadata."""
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceSpan(StrictModel):
    quote: str = Field(min_length=1, max_length=4000, description="Exact unchanged substring from the original discussion.")
    start: int = Field(ge=0, description="Inclusive zero-based Unicode character offset into discussion_text.")
    end: int = Field(gt=0, description="Exclusive Unicode character offset; discussion_text[start:end] must equal quote.")


class CandidateInput(StrictModel):
    requirement_text: str = Field(min_length=1, max_length=2000, description="One atomic obligation, preserving permissions, negation, conditions and constraints.")
    evidence: list[EvidenceSpan] = Field(min_length=1, max_length=8, description="Supporting spans, including relevant conditions and contextual restrictions.")
    actor: str | None = Field(max_length=200, description="Explicit actor as an exact evidence substring, or null if unstated.")
    action: str | None = Field(max_length=500, description="Explicit action as an exact evidence substring, or null if unstated.")


class ExtractionOutput(StrictModel):
    candidates: list[CandidateInput] = Field(max_length=100)


class RequirementCandidate(CandidateInput):
    requirement_id: str
    review_status: Literal["unreviewed"] = "unreviewed"


class ExtractionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    project_id: str
    source_discussion_hash: str
    created_at: AwareDatetime
    model_identifier: str
    prompt_version: str
    candidates: list[RequirementCandidate]
