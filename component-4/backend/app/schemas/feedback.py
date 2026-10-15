import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DeliveryStatus(str, Enum):
    """Lifecycle states for technical feedback delivery to Component 3."""

    NOT_DISPATCHED = "NOT_DISPATCHED"
    PENDING_DELIVERY = "PENDING_DELIVERY"
    DISPATCHED = "DISPATCHED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


# Forbidden keys that must NEVER be included in machine-directed technical feedback
FORBIDDEN_EXPLANATION_KEYS = frozenset({
    "xai_explanation",
    "summary",
    "what_failed",
    "confirmed_observations",
    "evidence_based_interpretation",
    "recommendation",
    "recommendations",
    "suggested_investigations",
    "explanation_method",
    "provider",
    "model_name",
    "tokens_used",
    "narrative",
    "internal_reasoning",
    "executive_summary",
})


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

    # Phase 4 Milestone 1 & 2: Dispatch lifecycle, governance, & audit fields
    dispatch_attempt_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the dispatch attempt (e.g. disp-...)",
    )
    approval_status: str = Field(
        default="NOT_REQUESTED",
        description="Human approval status (NOT_REQUESTED, PENDING_APPROVAL, APPROVED, REJECTED)",
    )
    approved_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when human reviewer explicitly approved feedback dispatch",
    )
    approved_by: Optional[str] = Field(
        default=None,
        description=(
            "Identifier of the human reviewer who authorized dispatch. "
            "Note: This field is client-supplied for audit logging and is not independently authenticated."
        ),
    )
    delivery_status: str = Field(
        default=DeliveryStatus.NOT_DISPATCHED.value,
        description="Delivery state (NOT_DISPATCHED, PENDING_DELIVERY, DISPATCHED, ACKNOWLEDGED, FAILED, UNKNOWN)",
    )
    component_3_job_id: Optional[str] = Field(
        default=None,
        description="Job or task identifier returned in Component 3 acknowledgment",
    )
    error_category: Optional[str] = Field(
        default=None,
        description="Category of failure if delivery fails (e.g. COMPONENT_3_DISABLED, TIMEOUT, CONNECTION_ERROR, CLIENT_ERROR)",
    )
    sanitized_error_message: Optional[str] = Field(
        default=None,
        description="Sanitized diagnostic error excerpt, free of secrets, credentials, or internal stack traces",
    )
    attempt_count: int = Field(
        default=0,
        ge=0,
        description="Total count of outbound dispatch transmission attempts executed for this cycle",
    )
    attempt_timestamps: List[datetime] = Field(
        default_factory=list,
        description="Historical UTC timestamps of all outbound dispatch attempts",
    )
    last_attempt_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the most recent dispatch attempt was executed",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="End-to-end tracing correlation identifier (X-Correlation-ID)",
    )
    dispatched_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when HTTP dispatch to Component 3 was initiated",
    )
    acknowledged_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when Component 3 confirmed receipt of technical feedback",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of last iteration state update",
    )


class FeedbackApprovalRequest(BaseModel):
    """
    Payload for explicit human approval of technical feedback before dispatch.
    Reviewer identity is client-supplied for audit tracking and is not independently authenticated.
    """

    approver: Optional[str] = Field(
        default="human_engineer",
        description="Identifier or name of the human engineer granting approval (client-supplied, not authenticated)",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional justification or review notes from the human engineer",
    )


class FeedbackDispatchRequest(BaseModel):
    """
    Payload to request dispatch of an approved technical feedback package to Component 3.
    Reviewer identity is client-supplied for audit tracking and is not independently authenticated.
    """

    approved: bool = Field(
        default=True,
        description="Explicit human confirmation authorizing dispatch to Component 3",
    )
    approver: Optional[str] = Field(
        default="human_engineer",
        description="Identifier of the human authorizing this dispatch request (client-supplied, not authenticated)",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional dispatch context notes",
    )
    force_retry: bool = Field(
        default=False,
        description="If True, permits retrying a previously failed dispatch attempt",
    )


class FeedbackDispatchResponse(BaseModel):
    """Response returned upon attempting technical feedback dispatch to Component 3."""

    verification_run_id: str = Field(description="Associated verification run ID")
    feedback_id: str = Field(description="Unique technical feedback package ID")
    dispatch_attempt_id: str = Field(description="Unique dispatch attempt identifier")
    approval_status: str = Field(description="Approval state (e.g. APPROVED, NOT_REQUESTED)")
    delivery_status: str = Field(
        description="Delivery status (e.g. ACKNOWLEDGED, FAILED, NOT_DISPATCHED, PENDING_DELIVERY, UNKNOWN)"
    )
    component_3_acknowledged: bool = Field(description="Whether Component 3 confirmed receipt")
    component_3_job_id: Optional[str] = Field(
        default=None,
        description="Job or correction task ID assigned by Component 3",
    )
    correlation_id: str = Field(description="Correlation ID for end-to-end request tracing")
    message: str = Field(description="Human-readable outcome or status message")
    error_category: Optional[str] = Field(
        default=None,
        description="Category of error if dispatch did not succeed",
    )
    sanitized_error_message: Optional[str] = Field(
        default=None,
        description="Sanitized diagnostic failure description without secrets or internal stack traces",
    )
    attempt_count: int = Field(
        default=1,
        ge=0,
        description="Count of dispatch attempts recorded for this feedback iteration",
    )
    iteration: Optional[FeedbackIteration] = Field(
        default=None,
        description="Updated feedback iteration record with persisted state",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the dispatch event",
    )


class Component3StatusResponse(BaseModel):
    """Diagnostic status response regarding Component 3 connectivity and contract availability."""

    configured: bool = Field(description="Whether Component 3 base URL is configured")
    enabled: bool = Field(description="Whether live HTTP dispatch to Component 3 is enabled")
    base_url: str = Field(description="Configured Component 3 service base URL")
    endpoint: str = Field(description="Configured Component 3 feedback receiver endpoint")
    contract_status: str = Field(
        description="Status of Component 3 contract (e.g. UNDER_DEVELOPMENT, ACTIVE)",
    )
    dispatch_allowed: bool = Field(
        description="Whether live dispatch can be executed in the current environment",
    )
    reason: str = Field(description="Detailed explanation of integration readiness")

    # Contract Readiness Checklist criteria (Milestone 2)
    verified_receiver_url: bool = Field(
        default=False,
        description="Whether the receiver base URL has been verified as external and non-placeholder",
    )
    confirmed_endpoint: bool = Field(
        default=False,
        description="Whether the correction-feedback HTTP endpoint is confirmed on receiver",
    )
    agreed_request_schema: bool = Field(
        default=False,
        description="Whether the technical feedback request contract has been formally confirmed",
    )
    agreed_acknowledgment_schema: bool = Field(
        default=False,
        description="Whether the remote response/acknowledgment contract has been agreed",
    )
    safe_idempotency_defined: bool = Field(
        default=False,
        description="Whether idempotent receiver deduplication is verified for retries",
    )
    readiness_checklist: Dict[str, bool] = Field(
        default_factory=dict,
        description="Comprehensive integration readiness conditions required before live dispatch",
    )




