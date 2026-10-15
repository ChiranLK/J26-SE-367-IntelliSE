import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TechnicalFeedbackPayload(BaseModel):
    """
    Structured technical feedback package intended for future delivery to Component 3.
    Contains strictly evidence-based diagnostic records (no speculative root causes or human XAI narratives).
    """

    feedback_id: str = Field(
        default_factory=lambda: f"fb-{uuid.uuid4().hex[:12]}",
        description="Unique feedback package identifier (e.g. fb-...)",
    )

    verification_run_id: str = Field(description="Associated verification run identifier")
    submission_id: str = Field(description="Associated code submission identifier")
    verification_status: str = Field(
        default="FAILED",
        description="Verification run status (e.g. FAILED, ERROR)",
    )
    affected_files: List[str] = Field(
        default_factory=list,
        description="List of affected source code filenames confirmed by submission metadata",
    )
    failed_tests: List[str] = Field(
        default_factory=list,
        description="Names of failed test cases that triggered this feedback",
    )
    failed_assertions: List[str] = Field(
        default_factory=list,
        description="List of failed assertion statements extracted from pytest outputs",
    )
    value_comparisons: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Structured comparisons containing test_name, expected, and observed values when available",
    )
    error_logs: List[str] = Field(
        default_factory=list,
        description="Relevant error logs or diagnostic excerpts with size limits applied",
    )
    test_failure_details: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed test outcome objects for failed test cases",
    )
    defect_ids: List[str] = Field(
        default_factory=list,
        description="Associated defect identifiers linked to this technical feedback",
    )
    evidence_references: Dict[str, Any] = Field(
        default_factory=dict,
        description="Deterministic references to execution telemetry (total tests, exit code, duration)",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when technical feedback payload was generated",
    )
    schema_version: str = Field(
        default="1.0",
        description="Payload schema version for downstream contract stability",
    )


class TechnicalFeedbackPreviewResponse(BaseModel):
    """
    Read-only preview response indicating eligibility and containing the prepared technical feedback.
    """

    eligible: bool = Field(description="Whether the verification run is eligible for technical feedback")
    reason: str = Field(description="Deterministic explanation of eligibility decision")
    feedback: Optional[TechnicalFeedbackPayload] = Field(
        default=None,
        description="Prepared technical feedback package if eligible, otherwise None",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when eligibility was evaluated and preview generated",
    )


class FeedbackIteration(BaseModel):
    """Schema representing an iteration in the testing and feedback loop with Component 3."""

    iteration_id: str = Field(description="Unique identifier for this feedback cycle")
    iteration_number: int = Field(ge=1, description="Sequential loop iteration index (1, 2, ...)")
    verification_run_id: str = Field(description="Associated verification run identifier")
    submission_id: str = Field(description="Associated code submission identifier")
    defects_count: int = Field(default=0, description="Total defects reported in this cycle")
    defect_ids: List[str] = Field(
        default_factory=list,
        description="List of defect IDs communicated to Component 3",
    )
    status: str = Field(
        default="AWAITING_REVISION",
        description="Loop status (e.g. AWAITING_REVISION, REVISED_CODE_SUBMITTED, RESOLVED)",
    )
    component_3_acknowledged: bool = Field(
        default=False,
        description="Whether Component 3 has acknowledged receipt of defect report",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Explanatory notes regarding this feedback iteration",
    )
    payload: Optional[TechnicalFeedbackPayload] = Field(
        default=None,
        description="Associated structured technical feedback payload for this iteration",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when feedback iteration record was initiated",
    )


