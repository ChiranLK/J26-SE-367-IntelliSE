import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """Empirical fact and concrete evidence extracted directly from test execution outcomes."""

    test_name: str = Field(description="Name of the test case")
    defect_id: Optional[str] = Field(default=None, description="Linked defect report ID")
    failure_category: Optional[str] = Field(
        default=None,
        description="Category of failure (e.g. ASSERTION_FAILURE, RUNTIME_EXCEPTION, TIMEOUT_ERROR)",
    )
    assertion_or_exception: Optional[str] = Field(
        default=None,
        description="Exact assertion failure statement or exception message",
    )
    expected_value: Optional[str] = Field(
        default=None,
        description="Expected value extracted from assertion diff or test oracle",
    )
    observed_value: Optional[str] = Field(
        default=None,
        description="Observed value produced by the submitted code",
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Source code file path identified in defect analysis",
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Line number in source code if localized without speculation",
    )
    traceback_excerpt: Optional[str] = Field(
        default=None,
        description="Bounded diagnostic traceback excerpt",
    )


class CorrectionRecommendation(BaseModel):
    """Structured recommendation for the human engineer regarding returning code to Component 3."""

    action: str = Field(
        description="Recommended action (e.g. RETURN_TO_COMPONENT_3, ACCEPT_VERIFICATION, RETRY_INFRASTRUCTURE, AWAIT_EXECUTION)",
    )
    recommended: bool = Field(
        description="Whether Component 4 recommends returning the implementation to Component 3 for repair",
    )
    reason: str = Field(
        description="Detailed, evidence-grounded justification for the recommendation",
    )
    target_audience: str = Field(
        default="Human Engineer / Reviewer",
        description="Intended recipient of this recommendation (strictly human; never dispatched to Component 3)",
    )


class XaiExplanationResponse(BaseModel):
    """
    Human-facing Explainable AI (XAI) explanation response.
    Designed strictly for human engineers and reviewers to understand verification results.
    Kept completely decoupled from the structured technical feedback payload sent to Component 3.
    """

    explanation_id: str = Field(
        default_factory=lambda: f"xai-{uuid.uuid4().hex[:12]}",
        description="Unique explanation package identifier",
    )
    verification_run_id: str = Field(description="Associated verification run identifier")
    submission_id: str = Field(description="Associated code submission identifier")
    verification_status: str = Field(description="Verification run status (e.g. FAILED, PASSED, ERROR, PENDING)")
    eligible: bool = Field(description="Whether the run is eligible for a full corrective explanation")
    eligibility_reason: str = Field(description="Deterministic reason explaining eligibility evaluation")

    # 1. Executive Summary
    summary: str = Field(description="High-level human-readable overview of verification findings")

    # 2. What failed?
    what_failed: List[str] = Field(
        default_factory=list,
        description="Concise list of specific tests, assertions, or operations that failed",
    )

    # 3. What evidence supports the failure? (Confirmed observations)
    confirmed_observations: List[EvidenceItem] = Field(
        default_factory=list,
        description="Concrete, empirical observations extracted directly from pytest execution results",
    )

    # 4. Why is the observed behavior inconsistent with authorized tests? (Evidence-based interpretation)
    evidence_based_interpretation: str = Field(
        description="Evidence-grounded interpretation of why observed outputs diverge from test expectations",
    )

    # 5. Why does Component 4 recommend returning implementation to Component 3?
    recommendation: CorrectionRecommendation = Field(
        description="Recommendation regarding routing this code back to Component 3 for corrective iteration",
    )

    # 6. What should be investigated or corrected?
    suggested_investigations: List[str] = Field(
        default_factory=list,
        description="Actionable pointers for investigation and repair grounded strictly in observed evidence",
    )

    # Metadata & Telemetry references
    evidence_references: Dict[str, Any] = Field(
        default_factory=dict,
        description="Deterministic references to defect IDs, test counts, and exit codes",
    )
    explanation_method: str = Field(
        default="deterministic_evidence_v1",
        description="Methodology or engine used (e.g. deterministic_evidence_v1; not claimed to be LLM)",
    )
    provider: str = Field(
        default="deterministic_evidence_v1",
        description="Provider identifier for explainability generation",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when explanation was synthesized",
    )
    schema_version: str = Field(
        default="1.0",
        description="Schema version for forward compatibility",
    )
