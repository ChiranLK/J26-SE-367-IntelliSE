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


class InferenceProvenance(BaseModel):
    """Trustworthy provenance exposing whether genuine LLM inference occurred or fallback was used."""

    provider: str = Field(description="Inference provider (e.g. 'ollama', 'deterministic')")
    model: Optional[str] = Field(default=None, description="Model identifier if LLM was invoked (e.g. 'qwen2.5-coder:3b')")
    genuine_inference: bool = Field(default=False, description="True if real model inference was executed successfully")
    fallback_used: bool = Field(default=False, description="True if fallback to deterministic evidence was triggered")
    fallback_reason: Optional[str] = Field(default=None, description="Detailed reason why fallback was used if applicable")
    duration_ms: Optional[float] = Field(default=None, description="Inference execution latency in milliseconds")


class DeliveryGateStatus(BaseModel):
    """Evaluation status of the mandatory 3-phase delivery gate for user-facing XAI."""

    verification_passed: bool = Field(description="True if test suite passed completely with zero failed assertions")
    governance_approved: bool = Field(description="True if deployment-readiness governance policies approved the artifact")
    delivery_confirmed: bool = Field(description="True if successful downstream delivery has been explicitly confirmed")
    delivery_id: Optional[str] = Field(default=None, description="Delivery confirmation identifier if confirmed")
    delivered_at: Optional[datetime] = Field(default=None, description="Timestamp of confirmed delivery")
    delivered_artifact_checksum: Optional[str] = Field(default=None, description="SHA-256 digest of delivered code artifact")
    is_simulation: bool = Field(default=False, description="True if delivery was confirmed via testing simulation")
    gate_verdict: str = Field(
        description="Gate decision: CONFIRMED_PRODUCTION_DELIVERY, SIMULATED_DELIVERY, PENDING_DELIVERY_CONFIRMATION, BLOCKED_UNAUTHORIZED_DELIVERY, BLOCKED_VERIFICATION_FAILED, BLOCKED_GOVERNANCE_REJECTED, PENDING_VERIFICATION, BLOCKED_INFRASTRUCTURE_ERROR, BLOCKED_VERSION_MISMATCH, BLOCKED_HASH_MISMATCH, CONFIRMED_DELIVERED",
    )
    verdict_reason: str = Field(description="Evidence-grounded rationale for the delivery gate verdict")


class ModuleResponsibilityItem(BaseModel):
    """Specification of a module or source file's architectural responsibility."""

    module_name: str = Field(description="Name or identifier of the module")
    file_path: str = Field(description="Source file path relative to submission workspace")
    primary_responsibility: str = Field(description="Primary architectural responsibility grounded in source code")
    exported_symbols: List[str] = Field(default_factory=list, description="Top-level functions and classes exposed by the module")
    line_count: int = Field(description="Physical source code line count")


class FunctionExplanationItem(BaseModel):
    """Detailed explanation of an important function or method grounded in AST structure."""

    function_name: str = Field(description="Name of the function")
    signature: str = Field(description="Exact parameter signature extracted from AST")
    file_path: str = Field(description="Source file containing the function")
    line_number: int = Field(description="Starting line number in physical source code")
    end_line_number: Optional[int] = Field(default=None, description="Ending line number in physical source code")
    summary_beginner: str = Field(description="Non-technical plain language explanation of function purpose")
    technical_behavior: str = Field(description="Detailed technical description of execution logic, arguments, and return types")
    parameters: List[Dict[str, Any]] = Field(default_factory=list, description="Structured parameter metadata")
    return_type: Optional[str] = Field(default=None, description="Return type or description")
    verified_by_tests: List[str] = Field(default_factory=list, description="Associated test cases verifying this function's behavior")


class DesignDecisionItem(BaseModel):
    """Architectural decision or algorithm choice identified with code-level evidence."""

    topic: str = Field(description="Design topic (e.g., 'Tax Calculation Algorithm', 'Data Normalization Strategy')")
    decision: str = Field(description="Architectural or algorithmic choice made")
    rationale: str = Field(description="Evidence-grounded justification derived from specifications and code structure")
    evidence_in_code: str = Field(description="Specific code patterns or constructs supporting this observation")
    traceability_seam: Optional[str] = Field(default=None, description="Associated requirement ID or test seam")


class BeginnerExplanation(BaseModel):
    """Beginner-friendly explanation layer designed for users with limited technical knowledge."""

    overview: str = Field(description="High-level plain English summary of what the software is and does")
    what_it_does: str = Field(description="Explanation of software functionality without technical jargon")
    how_to_use: str = Field(description="Step-by-step non-programmer guide to using the software")
    key_capabilities: List[str] = Field(default_factory=list, description="Bullet points of verified practical capabilities")
    safety_and_boundaries: str = Field(description="Plain-language description of verified safety boundaries and limits")


class TechnicalExplanation(BaseModel):
    """Detailed engineering explanation layer designed for software engineers and maintainers."""

    architecture_overview: str = Field(description="Structural architecture, module relationships, and execution flow")
    module_responsibilities: List[ModuleResponsibilityItem] = Field(default_factory=list, description="Module decomposition")
    important_functions: List[FunctionExplanationItem] = Field(default_factory=list, description="Component-level function details")
    api_and_data_flow: str = Field(description="API contracts, input/output data structures, and pipeline flow")
    algorithms_and_design_decisions: List[DesignDecisionItem] = Field(default_factory=list, description="Algorithms and rationale")
    setup_and_usage: str = Field(description="Runtime environment prerequisites, import statements, and code snippets")
    known_limitations_and_scope: str = Field(description="Explicit verification boundaries and untested edge cases")


class PostDeliveryExplanation(BaseModel):
    """Comprehensive post-delivery software understanding explanation package."""

    explanation_id: str = Field(
        default_factory=lambda: f"pdx-{uuid.uuid4().hex[:12]}",
        description="Unique explanation identifier",
    )
    verification_run_id: str = Field(description="Associated verification run identifier")
    submission_id: str = Field(description="Delivered code submission identifier")
    software_name: str = Field(description="Human-readable title of delivered software")
    software_overview: str = Field(description="1. Software overview")
    architecture_explanation: str = Field(description="2. Architecture explanation")
    module_responsibilities: List[ModuleResponsibilityItem] = Field(default_factory=list, description="3. Module and component responsibilities")
    important_functions: List[FunctionExplanationItem] = Field(default_factory=list, description="4. Important functions and their behavior")
    api_and_data_flow: str = Field(description="5. API and data-flow explanations")
    algorithms_and_design_decisions: List[DesignDecisionItem] = Field(default_factory=list, description="6. Relevant algorithms and design decisions")
    setup_and_usage: str = Field(description="7. Setup and usage instructions")
    limitations_and_verification_scope: str = Field(description="8. Known limitations and verification scope")
    beginner_level: BeginnerExplanation = Field(description="Beginner-friendly explanation layer")
    technical_level: TechnicalExplanation = Field(description="Technical engineering explanation layer")
    verified_test_count: int = Field(default=0, description="Number of authorized tests verifying this software")
    sanitized_secrets_count: int = Field(default=0, description="Count of potential credentials/secrets redacted for safety")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of synthesis",
    )


class XaiExplanationResponse(BaseModel):
    """
    Human-facing Explainable AI (XAI) explanation response.
    Designed to help end users and engineers understand delivered software or delivery gate status.
    Kept completely decoupled from the structured technical feedback payload sent to Component 3.
    """

    explanation_id: str = Field(
        default_factory=lambda: f"xai-{uuid.uuid4().hex[:12]}",
        description="Unique explanation package identifier",
    )
    verification_run_id: str = Field(description="Associated verification run identifier")
    submission_id: str = Field(description="Associated code submission identifier")
    verification_status: str = Field(description="Verification run status (e.g. FAILED, PASSED, ERROR, PENDING)")
    eligible: bool = Field(description="Whether the run is eligible for a full post-delivery code explanation")
    eligibility_reason: str = Field(description="Deterministic reason explaining eligibility evaluation")

    # Delivery Gate & Post-Delivery Explanation
    delivery_gate: Optional[DeliveryGateStatus] = Field(
        default=None,
        description="Status of the 3-phase delivery gate (verification passed, governance cleared, delivery confirmed)",
    )
    delivery_status: Optional[str] = Field(
        default=None,
        description="High-level gate decision (e.g., CONFIRMED_DELIVERED, PENDING_DELIVERY_CONFIRMATION, BLOCKED_VERIFICATION_FAILED)",
    )
    post_delivery_explanation: Optional[PostDeliveryExplanation] = Field(
        default=None,
        description="Rich post-delivery code understanding package (available exclusively upon confirmed delivery)",
    )

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
    inference_provenance: Optional[InferenceProvenance] = Field(
        default=None,
        description="Trustworthy provenance detailing whether genuine LLM inference occurred or fallback was used",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when explanation was synthesized",
    )
    schema_version: str = Field(
        default="1.0",
        description="Schema version for forward compatibility",
    )
