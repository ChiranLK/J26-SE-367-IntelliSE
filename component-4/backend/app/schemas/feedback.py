from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


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
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when feedback iteration record was initiated",
    )


class TechnicalFeedbackPayload(BaseModel):
    """
    Internal technical feedback representation for future Component 3 integration.
    Contains strictly evidence-based diagnostic records (no XAI or speculative explanations).
    """

    verification_run_id: str = Field(description="Associated verification run identifier")
    submission_id: str = Field(description="Associated code submission identifier")
    failed_assertions: List[str] = Field(
        default_factory=list,
        description="List of failed assertion statements extracted from pytest outputs",
    )
    error_logs: List[str] = Field(
        default_factory=list,
        description="Relevant error logs or diagnostic excerpts",
    )
    affected_files: List[str] = Field(
        default_factory=list,
        description="List of affected source code filenames confirmed by submission metadata",
    )
    test_failure_details: List[dict] = Field(
        default_factory=list,
        description="Detailed test outcome objects for failed test cases",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when technical feedback payload was generated",
    )

