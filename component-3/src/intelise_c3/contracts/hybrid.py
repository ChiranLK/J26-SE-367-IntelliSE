"""Versioned (2.0) machine-readable contracts for the hybrid generation pipeline.

These are C3-side *proposed* transport contracts. C1, C2 and C4 own their
semantics; C3 only validates shape, versions, approval/release status and
provenance presence. Reference strings are opaque provenance: their presence
does not authenticate an upstream decision. ``evidence_class`` makes simulated
fixtures explicit so they can never masquerade as real upstream output.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from intelise_c3.contracts.stack_selection import StackSelectionCriteria

Identifier = Annotated[
    str, StringConstraints(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:#-]*$")
]
Text = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
UtcTimestamp = Annotated[str, StringConstraints(min_length=10, max_length=40)]


class HybridContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceClass(StrEnum):
    """Where an upstream/downstream document really came from."""

    SIMULATED_FIXTURE = "SIMULATED_FIXTURE"
    UPSTREAM_COMPONENT_OUTPUT = "UPSTREAM_COMPONENT_OUTPUT"


class InputClassification(StrEnum):
    VALIDATED_CONTRACT_INPUT = "VALIDATED_CONTRACT_INPUT"
    PROVISIONAL_DEMO_INPUT = "PROVISIONAL_DEMO_INPUT"


class C1ApprovalStatusV2(StrEnum):
    CLIENT_APPROVED = "CLIENT_APPROVED"
    PENDING_CLIENT_APPROVAL = "PENDING_CLIENT_APPROVAL"
    REJECTED = "REJECTED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class C2ReleaseStatusV2(StrEnum):
    VALIDATED = "VALIDATED"
    DRAFT = "DRAFT"
    FAILED = "FAILED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class ConstraintKind(StrEnum):
    REQUIRED = "REQUIRED"
    RANGE = "RANGE"
    PATTERN = "PATTERN"
    ENUM_FROM_POLICY = "ENUM_FROM_POLICY"
    UNIQUE_WITHIN_REQUEST = "UNIQUE_WITHIN_REQUEST"


class RequirementConstraint(HybridContractModel):
    """Structured acceptance constraint supplied by C1 (proposed field, pending C1 confirmation)."""

    constraint_id: Identifier
    target: Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")]
    kind: ConstraintKind
    minimum: int | None = None
    maximum: int | None = None
    pattern: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None

    @model_validator(mode="after")
    def _kind_fields(self) -> "RequirementConstraint":
        if self.kind is ConstraintKind.RANGE and (self.minimum is None or self.maximum is None or self.minimum > self.maximum):
            raise ValueError("RANGE constraints need minimum <= maximum.")
        if self.kind is ConstraintKind.PATTERN and not self.pattern:
            raise ValueError("PATTERN constraints need a pattern.")
        return self


class C1RequirementV2(HybridContractModel):
    requirement_id: Identifier
    requirement_version: Annotated[int, Field(ge=1, strict=True)]
    requirement_type: Literal["FR", "NFR"]
    title: Annotated[str, StringConstraints(min_length=1, max_length=240)]
    statement: Text
    approval_status: C1ApprovalStatusV2
    constraints: tuple[RequirementConstraint, ...] = ()


class C1Provenance(HybridContractModel):
    source_system: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    source_document_ref: Identifier
    quality_report_ref: Identifier
    classification_report_ref: Identifier


class C1PackageV2(HybridContractModel):
    contract_version: Literal["2.0"]
    evidence_class: EvidenceClass
    project_id: Identifier
    srs_version: Identifier
    approval_status: C1ApprovalStatusV2
    approval_reference: Identifier
    approved_by: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    approved_at_utc: UtcTimestamp
    provenance: C1Provenance
    requirements: Annotated[tuple[C1RequirementV2, ...], Field(min_length=1, max_length=200)]


class UmlArtifactV2(HybridContractModel):
    uml_id: Identifier
    diagram_type: Literal["CLASS", "USE_CASE"]
    name: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    plantuml_source: Annotated[str, StringConstraints(min_length=1, max_length=40000)]


class UiComponentKind(StrEnum):
    DYNAMIC_ROWS = "DYNAMIC_ROWS"
    TEXT_INPUT = "TEXT_INPUT"
    NUMBER_INPUT = "NUMBER_INPUT"
    SELECT = "SELECT"
    CHECKBOX = "CHECKBOX"
    BUTTON = "BUTTON"
    RESULT_PANEL = "RESULT_PANEL"
    LIST = "LIST"
    DISCLOSURE = "DISCLOSURE"
    ERROR_SUMMARY = "ERROR_SUMMARY"


class UiComponentV2(HybridContractModel):
    component_id: Identifier
    kind: UiComponentKind
    label: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    binds_to: Annotated[str, StringConstraints(min_length=1, max_length=160)] | None = None


class UiScreenV2(HybridContractModel):
    screen_id: Identifier
    title: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    requirement_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    components: Annotated[tuple[UiComponentV2, ...], Field(min_length=1, max_length=60)]


class RequirementUmlAnchorV2(HybridContractModel):
    anchor_id: Identifier
    requirement_id: Identifier
    uml_id: Identifier
    uml_element: Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]


class C2ValidationReports(HybridContractModel):
    semantic_report_ref: Identifier
    syntax_report_ref: Identifier
    ui_report_ref: Identifier


class C2PackageV2(HybridContractModel):
    contract_version: Literal["2.0"]
    evidence_class: EvidenceClass
    project_id: Identifier
    srs_version: Identifier
    uml_version: Identifier
    release_status: C2ReleaseStatusV2
    released_at_utc: UtcTimestamp
    validation_reports: C2ValidationReports
    uml_artifacts: Annotated[tuple[UmlArtifactV2, ...], Field(min_length=1, max_length=20)]
    ui_specification: Annotated[tuple[UiScreenV2, ...], Field(min_length=1, max_length=20)]
    requirement_uml_anchors: Annotated[tuple[RequirementUmlAnchorV2, ...], Field(min_length=1, max_length=400)]


class HumanOverrideScope(StrEnum):
    C2_NEEDS_HUMAN_REVIEW_RELEASE = "C2_NEEDS_HUMAN_REVIEW_RELEASE"


class HumanOverride(HybridContractModel):
    """Explicit, version-bound and auditable override. FAILED inputs can never be overridden."""

    override_id: Identifier
    scope: HumanOverrideScope
    reason: Annotated[str, StringConstraints(min_length=10, max_length=600)]
    approved_by: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    approval_reference: Identifier
    bound_project_id: Identifier
    bound_srs_version: Identifier
    bound_uml_version: Identifier
    approved_at_utc: UtcTimestamp


class HybridInputPackage(HybridContractModel):
    contract_version: Literal["2.0"]
    input_classification: InputClassification
    c1: C1PackageV2
    c2: C2PackageV2
    human_override: HumanOverride | None = None


class PolicyAcceptance(HybridContractModel):
    """Explicit acceptance of a KB domain policy, bound to its exact version and digest."""

    policy_id: Identifier
    policy_version: Identifier
    policy_digest_sha256: Sha256Hex
    accepted_by: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    acceptance_reference: Identifier
    acknowledges_sample_status: bool


class HybridGenerationRequest(HybridContractModel):
    package: HybridInputPackage
    policy_acceptance: PolicyAcceptance | None = None
    # Evidence-bearing criteria for the reused FR-C3-02 stack scorer. When omitted,
    # the existing SIMULATED researcher criteria are used and labelled as such.
    stack_criteria: StackSelectionCriteria | None = None
    workspace_name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=64)] = "gpa-hybrid"
    allow_llm_for_unsupported: bool = False
    # Explicit opt-in: TeamSocLo writes be.service and be.validation (chosen by the rules) instead of templates.
    # Accepted only after JS-safety, interface and Docker-sandbox benchmark checks; otherwise generation stops for human review.
    llm_backend_logic: bool = False
    # Explicit opt-in: TeamSocLo writes the UI files (two parallel calls) instead of templates; trusted scaffold stays templated.
    # Accepted only after the frontend policy, a no-network vite build and the jsdom UI benchmark pass; otherwise human review.
    llm_frontend: bool = False


class RequirementChangeRequest(HybridContractModel):
    """An approved C1/C2 change applied to an existing run by scoped regeneration."""

    base_generation_run_id: Identifier
    package: HybridInputPackage
    policy_acceptance: PolicyAcceptance | None = None
    approved_dependency_modules: tuple[Identifier, ...] = ()


# --- Component 4 contracts -------------------------------------------------


class C4DefectCategory(StrEnum):
    BUSINESS_LOGIC = "BUSINESS_LOGIC"
    VALIDATION = "VALIDATION"
    API_CONTRACT = "API_CONTRACT"
    DATA_ACCESS = "DATA_ACCESS"
    UI_BEHAVIOR = "UI_BEHAVIOR"


class C4Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class C4DefectFeedback(HybridContractModel):
    report_id: Identifier
    report_version: Literal["2.0"]
    evidence_class: EvidenceClass
    project_id: Identifier
    generation_run_id: Identifier
    artifact_digest_sha256: Sha256Hex
    module_id: Identifier
    module_digest_sha256: Sha256Hex
    failing_test_id: Identifier
    test_seam_id: Identifier
    category: C4DefectCategory
    severity: C4Severity
    observed_evidence: Text
    inferred_cause: Text
    proposed_repair_scope: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=6)]
    traceability_refs: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=20)]
    reported_at_utc: UtcTimestamp


class C4DefectSubmission(HybridContractModel):
    report: C4DefectFeedback
    approved_dependency_modules: tuple[Identifier, ...] = ()


class ReadinessStatus(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"


class SemanticPreservation(StrEnum):
    PRESERVED = "PRESERVED"
    VIOLATED = "VIOLATED"
    UNRESOLVED = "UNRESOLVED"
    NOT_ASSESSED = "NOT_ASSESSED"


class ConvergenceState(StrEnum):
    CONVERGED = "CONVERGED"
    NON_CONVERGENT = "NON_CONVERGENT"
    NOT_ASSESSED = "NOT_ASSESSED"


class ModuleDigest(HybridContractModel):
    module_id: Identifier
    module_digest_sha256: Sha256Hex


class C4ReadinessSignal(HybridContractModel):
    signal_id: Identifier
    signal_version: Literal["2.0"]
    evidence_class: EvidenceClass
    project_id: Identifier
    generation_run_id: Identifier
    artifact_digest_sha256: Sha256Hex
    modules: Annotated[tuple[ModuleDigest, ...], Field(min_length=1, max_length=60)]
    status: ReadinessStatus
    issued_at_utc: UtcTimestamp
    revoked: bool
    revocation_reason: Annotated[str, StringConstraints(max_length=400)] | None = None
    semantic_preservation: SemanticPreservation
    convergence: ConvergenceState
    evidence_refs: tuple[Identifier, ...] = ()


class DeploymentGateRequest(HybridContractModel):
    generation_run_id: Identifier
    readiness_signal: C4ReadinessSignal | None = None


class HybridLlmTrialRequest(HybridContractModel):
    """Ask OpenRouter to write one module that a template already produced, for comparison only."""

    generation_run_id: Identifier
    module_id: Literal["be.service"] = "be.service"
    bypass_cache: bool = False


class HybridPreviewRequest(HybridContractModel):
    generation_run_id: Identifier


class HybridPreviewStopRequest(HybridContractModel):
    preview_id: Identifier
