from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from app.schemas.common import TestType, VerificationStatus
from app.schemas.defect_report import DefectReport
from app.schemas.delivery import DeliveryConfirmation
from app.schemas.feedback import FeedbackIteration
from app.schemas.test_result import TestResult


class VerificationRunCreate(BaseModel):
    """Payload to initiate a new verification run for an existing submission."""

    submission_id: str = Field(
        min_length=1,
        description="ID of the code submission to verify",
    )
    triggered_by: str = Field(
        default="manual",
        description="Source entity that triggered the run (e.g. 'manual', 'component_3_pipeline')",
    )
    test_types: List[TestType] = Field(
        default_factory=lambda: [TestType.UNIT],
        description="Requested test types for this verification run",
    )
    trusted_test_cases: Optional[str] = Field(
        default=None,
        description="Explicitly authorized pytest test code or oracle for this run",
    )


class VerificationRunExecute(BaseModel):
    """Payload to trigger execution of a pending verification run."""

    trusted_test_cases: Optional[str] = Field(
        default=None,
        description="Optional explicit trusted pytest test code / oracle overriding or complementing submission test code",
    )


class VerificationStatusResponse(BaseModel):
    """Lightweight response indicating the current status of a verification run."""

    id: str = Field(description="Unique verification run identifier")
    submission_id: str = Field(description="Associated submission identifier")
    status: VerificationStatus = Field(description="Current status (PENDING, RUNNING, PASSED, FAILED, ERROR)")
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if run status is ERROR",
    )
    created_at: datetime = Field(description="Run creation timestamp")
    updated_at: datetime = Field(description="Run last update timestamp")


class VerificationRunResponse(BaseModel):
    """Full detail response for a verification run."""

    id: str = Field(description="Unique verification run identifier (e.g. run-...)")
    submission_id: str = Field(description="Associated submission identifier")
    status: VerificationStatus = Field(
        default=VerificationStatus.PENDING,
        description="Current verification status",
    )
    triggered_by: str = Field(default="manual", description="Triggering agent or entity")
    requested_test_types: List[TestType] = Field(
        default_factory=list,
        description="Test types requested for this run",
    )
    test_results: List[TestResult] = Field(
        default_factory=list,
        description="Individual test outcomes (populated when test agents execute in Phase 2)",
    )
    defect_reports: List[DefectReport] = Field(
        default_factory=list,
        description="Structured defects communicated to Component 3",
    )
    feedback_iterations: List[FeedbackIteration] = Field(
        default_factory=list,
        description="Feedback loop history with Component 3",
    )
    execution_telemetry: Optional[dict] = Field(
        default_factory=dict,
        description="Runtime container execution telemetry",
    )
    test_suite_id: Optional[str] = Field(
        default=None,
        description="Associated trusted test suite identifier",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Diagnostic details if status is ERROR",
    )
    delivery_confirmation: Optional[DeliveryConfirmation] = Field(
        default=None,
        description="Confirmed downstream delivery record for the verified artifact (prerequisite gate for post-delivery XAI)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC last update timestamp",
    )

    @model_validator(mode="after")
    def validate_passed_status_requires_evidence(self) -> "VerificationRunResponse":
        """Enforces that a verification run cannot be marked PASSED without test results."""
        if self.status == VerificationStatus.PASSED and not self.test_results:
            raise ValueError(
                "Verification run cannot be marked PASSED without real test evidence."
            )
        return self

    @property
    def defects(self) -> List[DefectReport]:
        return self.defect_reports


class VerificationRunListResponse(BaseModel):
    """Paginated or listed view of verification runs."""

    total: int = Field(description="Total count of verification runs")
    items: List[VerificationRunResponse] = Field(description="List of verification runs")
