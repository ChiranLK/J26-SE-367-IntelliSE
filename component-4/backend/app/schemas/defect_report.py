from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import DefectSeverity


class DefectReport(BaseModel):
    """Structured defect report generated when verification checks detect failures."""

    defect_id: str = Field(description="Unique defect identifier (e.g. def-...)")
    requirement_id: Optional[str] = Field(
        default=None,
        description="Associated requirement ID that the defect violates",
    )
    title: str = Field(description="Concise description of the defect")
    severity: DefectSeverity = Field(
        default=DefectSeverity.MEDIUM,
        description="Severity classification of the defect",
    )
    description: str = Field(description="Detailed explanation of the failure mode")
    file_path: Optional[str] = Field(
        default=None,
        description="Relative file path where defect was identified",
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Line number if localized to a specific source line",
    )
    suggested_fix: Optional[str] = Field(
        default=None,
        description="High-level suggestion for Component 3 correction (Component 4 does not modify code)",
    )
    xai_explanation: Optional[str] = Field(
        default=None,
        description="Conditional explainable AI feedback generated in later phases",
    )
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when defect report was generated",
    )

    # Phase 2C Milestone 1: Evidence-based defect analysis fields
    verification_run_id: Optional[str] = Field(
        default=None,
        description="Verification run identifier associated with this defect",
    )
    submission_id: Optional[str] = Field(
        default=None,
        description="Submission identifier associated with this defect",
    )
    failed_test: Optional[str] = Field(
        default=None,
        description="Exact name of the failed test case",
    )
    failure_category: Optional[str] = Field(
        default=None,
        description="Category of failure: ASSERTION_FAILURE, RUNTIME_EXCEPTION, TIMEOUT_ERROR, SYNTAX_ERROR",
    )
    assertion_or_exception: Optional[str] = Field(
        default=None,
        description="Extracted assertion error statement or exception class and message",
    )
    expected_value: Optional[str] = Field(
        default=None,
        description="Reliably extracted expected value from assertion diff, if available",
    )
    actual_value: Optional[str] = Field(
        default=None,
        description="Reliably extracted actual value from assertion diff, if available",
    )
    traceback_excerpt: Optional[str] = Field(
        default=None,
        description="Relevant diagnostic traceback excerpt without fabricated frames",
    )
    evidence_references: dict = Field(
        default_factory=dict,
        description="Deterministic references to test execution evidence (test ID, exit codes, metrics)",
    )


class DefectReportListResponse(BaseModel):
    """List response model for defect reports."""

    total: int = Field(description="Total count of defect reports")
    items: List[DefectReport] = Field(description="List of defect reports")

