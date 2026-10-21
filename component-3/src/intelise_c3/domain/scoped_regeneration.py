"""Machine-readable evidence for defect-feedback-driven scoped regeneration.

Nothing here asserts that a defect was repaired. A completed run is
``PATCHED_PENDING_INDEPENDENT_RETEST``: C3 changed only graph-selected modules
and verified structure and hashes, while independent Component 4 re-testing
remains ``PENDING``.
"""

from enum import StrEnum
from typing import Literal

from intelise_c3.contracts.defect_report import DefectSourceClassification
from intelise_c3.domain.generation import GeneratedArtifactType, TraceRelationType
from intelise_c3.domain.generation_context import DomainModel
from intelise_c3.domain.structural_verification import StructuralVerificationReport
from intelise_c3.domain.traceability import GraphChangeReport

IMPACT_ALGORITHM_VERSION = "C3_IMPACT_SELECTION_V1"


class ImpactSelectionStatus(StrEnum):
    SELECTED = "SELECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ImpactReasonCode(StrEnum):
    SELECTED_BY_REQUIREMENT_AND_TEST_PATH = "SELECTED_BY_REQUIREMENT_AND_TEST_PATH"
    SELECTED_BY_REQUIREMENT_AND_API_PATH = "SELECTED_BY_REQUIREMENT_AND_API_PATH"
    NOT_REACHED_BY_ANY_TYPED_PATH = "NOT_REACHED_BY_ANY_TYPED_PATH"
    NOT_ON_FAILING_TEST_OR_API_PATH = "NOT_ON_FAILING_TEST_OR_API_PATH"
    NOT_LINKED_TO_AFFECTED_REQUIREMENT = "NOT_LINKED_TO_AFFECTED_REQUIREMENT"
    CATEGORY_INCOMPATIBLE = "CATEGORY_INCOMPATIBLE"
    NOT_CORROBORATED_BY_DEFECT_LOCATION = "NOT_CORROBORATED_BY_DEFECT_LOCATION"
    LOCATION_CLAIM_NOT_SUPPORTED_BY_GRAPH = "LOCATION_CLAIM_NOT_SUPPORTED_BY_GRAPH"
    LOCATION_NOT_IN_MANIFEST = "LOCATION_NOT_IN_MANIFEST"
    REVIEW_REQUIRED_LINK_EXCLUDED = "REVIEW_REQUIRED_LINK_EXCLUDED"
    UNSUPPORTED_DEFECT_CATEGORY = "UNSUPPORTED_DEFECT_CATEGORY"
    MISSING_TRACE_LINKS = "MISSING_TRACE_LINKS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    SCOPE_TOO_BROAD = "SCOPE_TOO_BROAD"
    SELECTED_MODULE_NOT_PATCHABLE = "SELECTED_MODULE_NOT_PATCHABLE"


class EvidenceChannel(StrEnum):
    REQUIREMENT_IMPLEMENTS = "REQUIREMENT_IMPLEMENTS"
    FAILING_TEST_PATH = "FAILING_TEST_PATH"
    API_EXPOSES = "API_EXPOSES"


class ImpactPathStep(DomainModel):
    source_node_id: str
    relation_type: TraceRelationType
    target_node_id: str
    link_id: str
    mapping_rule_id: str
    evidence_refs: tuple[str, ...]


class ImpactPath(DomainModel):
    channel: EvidenceChannel
    anchor_node_id: str
    steps: tuple[ImpactPathStep, ...]


class SelectedModule(DomainModel):
    node_id: str
    file_id: str
    relative_path: str
    module_identity: str
    artifact_type: GeneratedArtifactType
    defect_ids: tuple[str, ...]
    evidence_channels: tuple[EvidenceChannel, ...]
    location_corroborated: bool
    reason_codes: tuple[ImpactReasonCode, ...]
    paths: tuple[ImpactPath, ...]


class ModuleExclusion(DomainModel):
    node_id: str
    relative_path: str
    reason_codes: tuple[ImpactReasonCode, ...]


class ExcludedLink(DomainModel):
    link_id: str
    source_node_id: str
    relation_type: TraceRelationType
    target_node_id: str
    reason_code: Literal[ImpactReasonCode.REVIEW_REQUIRED_LINK_EXCLUDED] = (
        ImpactReasonCode.REVIEW_REQUIRED_LINK_EXCLUDED
    )
    details: str


class DefectImpactResult(DomainModel):
    defect_id: str
    category: str
    status: ImpactSelectionStatus
    reason_codes: tuple[ImpactReasonCode, ...]
    selected_modules: tuple[SelectedModule, ...]
    review_candidate_paths: tuple[str, ...]
    exclusions: tuple[ModuleExclusion, ...]
    excluded_links: tuple[ExcludedLink, ...]
    notes: tuple[str, ...]


class ImpactSelectionReport(DomainModel):
    report_version: Literal["1.0"] = "1.0"
    algorithm_version: Literal["C3_IMPACT_SELECTION_V1"] = IMPACT_ALGORITHM_VERSION
    defect_report_id: str
    defect_report_sha256: str
    defect_source_classification: DefectSourceClassification
    graph_id: str
    graph_version: int
    graph_content_digest_sha256: str
    source_generation_run_id: str
    source_artifact_digest_sha256: str
    status: ImpactSelectionStatus
    reason_codes: tuple[ImpactReasonCode, ...]
    selected_modules: tuple[SelectedModule, ...]
    defects: tuple[DefectImpactResult, ...]
    automatic_scope_limit: int
    c4_claim: Literal[False] = False


class RegenerationStatus(StrEnum):
    PATCHED_PENDING_INDEPENDENT_RETEST = "PATCHED_PENDING_INDEPENDENT_RETEST"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


class RegenerationReasonCode(StrEnum):
    IMPACT_SELECTION_REVIEW_REQUIRED = "IMPACT_SELECTION_REVIEW_REQUIRED"
    SOURCE_STRUCTURALLY_INVALID = "SOURCE_STRUCTURALLY_INVALID"
    PATCH_ATTEMPTS_EXHAUSTED = "PATCH_ATTEMPTS_EXHAUSTED"
    PATCH_SYNTAX_REQUIRES_REVIEW = "PATCH_SYNTAX_REQUIRES_REVIEW"
    STRUCTURAL_VERIFICATION_FAILED = "STRUCTURAL_VERIFICATION_FAILED"
    ARTIFACT_PRESERVATION_VIOLATION = "ARTIFACT_PRESERVATION_VIOLATION"
    GRAPH_CHANGE_SCOPE_VIOLATION = "GRAPH_CHANGE_SCOPE_VIOLATION"
    INSUFFICIENT_DEFECT_CONTEXT = "INSUFFICIENT_DEFECT_CONTEXT"
    PATCH_APPLIED_STRUCTURALLY_VERIFIED = "PATCH_APPLIED_STRUCTURALLY_VERIFIED"


class PatchRejectionCode(StrEnum):
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    UNSAFE_PATCH_PATH = "UNSAFE_PATCH_PATH"
    PATCH_PATH_NOT_AUTHORIZED = "PATCH_PATH_NOT_AUTHORIZED"
    UNSAFE_PATCH_CONTENT = "UNSAFE_PATCH_CONTENT"
    UNINSPECTABLE_PATCH_SYNTAX = "UNINSPECTABLE_PATCH_SYNTAX"
    PATCH_INTERFACE_VIOLATION = "PATCH_INTERFACE_VIOLATION"
    PATCH_REMOVED_GUARD_CHECK = "PATCH_REMOVED_GUARD_CHECK"
    PATCH_NO_OP = "PATCH_NO_OP"


class PatchAttemptRecord(DomainModel):
    relative_path: str
    attempt_number: int
    accepted: bool
    rejection_code: PatchRejectionCode | None
    prompt_template_version: str
    prompt_request_sha256: str
    response_sha256: str
    model_identifier: str
    client_inference_latency_ms: float


class ModulePatchRecord(DomainModel):
    node_id: str
    file_id: str
    relative_path: str
    source_sha256: str
    new_sha256: str
    source_size_bytes: int
    new_size_bytes: int
    lines_added: int
    lines_removed: int
    attempts_used: int


class TriggerCRetrievalEvidence(DomainModel):
    """Auditable retrieval inputs used for one module repair prompt."""

    evidence_version: Literal["1.0"] = "1.0"
    module_path: str
    rag_a_backend: str
    rag_a_embedding_model: str | None
    rag_a_chunk_ids: tuple[str, ...]
    rag_b_backend: str
    rag_b_embedding_model: str | None
    rag_b_rule_ids: tuple[str, ...]
    applied_to_prompt: bool


class TriggerCPatchEvent(DomainModel):
    """Versioned Trigger-C event; it records evidence, not proof of repair."""

    event_version: Literal["1.0"] = "1.0"
    trigger: Literal["C4_DEFECT_REPORT_TRIGGER_C"] = "C4_DEFECT_REPORT_TRIGGER_C"
    defect_report_id: str
    defect_ids: tuple[str, ...]
    rtm_requirement_ids: tuple[str, ...]
    retrievals: tuple[TriggerCRetrievalEvidence, ...]
    changed_files: tuple[str, ...]
    changed_symbols: tuple[str, ...]
    changed_symbol_basis: Literal["GRAPH_CORROBORATED_C4_LOCATION_CLAIM"] = (
        "GRAPH_CORROBORATED_C4_LOCATION_CLAIM"
    )
    rationale: str
    source_artifact_digest_sha256: str
    new_artifact_digest_sha256: str
    graph_version_before: int
    graph_version_after: int


class HumanReviewPackage(DomainModel):
    """Bounded within-request failure history for C3-08 researcher review."""

    package_version: Literal["1.0"] = "1.0"
    reason_code: str
    required_action: str
    defect_report: dict[str, object]
    attempted_patches: tuple[PatchAttemptRecord, ...]
    rejection_reasons: tuple[str, ...]
    source_generation_run_id: str
    source_artifact_digest_sha256: str
    source_graph_version: int
    candidate_new_generation_run_id: str | None = None
    candidate_new_artifact_digest_sha256: str | None = None
    cross_round_history_included: Literal[False] = False


class FilePreservationEntry(DomainModel):
    relative_path: str
    file_id: str
    source_sha256: str
    new_sha256: str
    selected: bool
    byte_identical: bool


class HashPreservationReport(DomainModel):
    hash_algorithm: Literal["SHA-256"] = "SHA-256"
    unchanged_file_count: int
    changed_file_count: int
    collateral_edit_count: int
    all_unselected_files_byte_identical: bool
    entries: tuple[FilePreservationEntry, ...]


class ArtifactVersioning(DomainModel):
    source_generation_run_id: str
    new_generation_run_id: str
    source_workspace_relative_path: str
    new_workspace_relative_path: str
    source_artifact_digest_sha256: str
    new_artifact_digest_sha256: str
    source_evidence_digest_sha256: str
    new_evidence_digest_sha256: str
    source_run_preserved: Literal[True] = True


class GraphVersionEvidence(DomainModel):
    graph_id: str
    base_graph_version: int
    new_graph_version: int
    base_graph_content_digest_sha256: str
    new_graph_content_digest_sha256: str
    new_snapshot_id: str
    change_report: GraphChangeReport


class EscalationRecord(DomainModel):
    reason_code: str
    required_action: str
    attempts_made: int
    attempt_limit: int


class C4RetestHandoff(DomainModel):
    """Request for independent re-testing. It is not evidence of a repair."""

    handoff_version: Literal["1.0"] = "1.0"
    handoff_classification: Literal[
        "C3_TO_C4_RETEST_REQUEST_SIMULATED_UNTIL_C4_INTEGRATION"
    ] = "C3_TO_C4_RETEST_REQUEST_SIMULATED_UNTIL_C4_INTEGRATION"
    retest_status: Literal["PENDING"] = "PENDING"
    repair_verification: Literal[
        "NOT_ASSERTED_PENDING_INDEPENDENT_C4_RETEST"
    ] = "NOT_ASSERTED_PENDING_INDEPENDENT_C4_RETEST"
    independent_c4_evidence: Literal["NONE"] = "NONE"
    project_id: str
    defect_report_id: str
    defect_ids: tuple[str, ...]
    source_generation_run_id: str
    new_generation_run_id: str
    source_artifact_digest_sha256: str
    new_artifact_digest_sha256: str
    new_evidence_digest_sha256: str
    new_workspace_relative_path: str
    graph_id: str
    new_graph_version: int
    requirement_ids_to_retest: tuple[str, ...]
    failing_tests_to_rerun: tuple[str, ...]
    changed_modules: tuple[str, ...]
    unchanged_module_count: int
    c3_structural_overall_status: str
    required_c4_actions: tuple[str, ...]
    generated_at_utc: str


class RegenerationMetrics(DomainModel):
    total_latency_ms: float
    llm_call_count: int
    llm_inference_latency_ms_total: float
    accepted_patch_count: int
    rejected_attempt_count: int
    patch_validity_rate: float | None
    collateral_edit_count: int | None
    unchanged_files_byte_identical: bool | None
    within_request_attempt_count: int = 0
    within_request_attempt_limit: int | None = None
    repair_success: Literal["NOT_EVALUATED_REQUIRES_INDEPENDENT_C4_RETEST"] = (
        "NOT_EVALUATED_REQUIRES_INDEPENDENT_C4_RETEST"
    )


class ScopedRegenerationResult(DomainModel):
    result_version: Literal["1.0"] = "1.0"
    status: RegenerationStatus
    reason_codes: tuple[RegenerationReasonCode, ...]
    model_evidence_class: Literal[
        "REAL_LOCAL_OLLAMA", "SIMULATED_RAG_TEST_DOUBLE", "MOCKED_TEST_DOUBLE"
    ]
    impact_selection: ImpactSelectionReport
    patch_attempts: tuple[PatchAttemptRecord, ...]
    patches: tuple[ModulePatchRecord, ...]
    artifact_versioning: ArtifactVersioning | None
    preservation: HashPreservationReport | None
    structural_verification: StructuralVerificationReport | None
    graph_versioning: GraphVersionEvidence | None
    c4_retest_handoff: C4RetestHandoff | None
    escalation: EscalationRecord | None
    discarded_workspace_relative_path: str | None
    metrics: RegenerationMetrics
    repair_execution_mode: Literal[
        "AI_RAG_LOCAL_LLM",
        "SIMULATED_RAG_TEST_DOUBLE",
        "DETERMINISTIC_TEST_DOUBLE",
        "LEGACY_UNSPECIFIED",
    ] = "LEGACY_UNSPECIFIED"
    retrieval_evidence: tuple[TriggerCRetrievalEvidence, ...] = ()
    patch_event: TriggerCPatchEvent | None = None
    human_review_package: HumanReviewPackage | None = None
    c4_testing_claim: Literal[False] = False
    execution_claim: Literal["GENERATED_CODE_NOT_EXECUTED"] = (
        "GENERATED_CODE_NOT_EXECUTED"
    )


class ImpactScenarioOutcome(DomainModel):
    scenario_id: str
    expected_status: ImpactSelectionStatus
    observed_status: ImpactSelectionStatus
    expected_modules: tuple[str, ...]
    selected_modules: tuple[str, ...]
    true_positive_modules: tuple[str, ...]
    false_positive_modules: tuple[str, ...]
    false_negative_modules: tuple[str, ...]


class ImpactSelectionEvaluationReport(DomainModel):
    evaluation_version: Literal["1.0"] = "1.0"
    dataset_id: str
    dataset_version: str
    ground_truth_review_status: Literal["NOT_INDEPENDENTLY_REVIEWED"]
    scenario_count: int
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float
    recall: float
    f1_score: float
    decision_agreement_count: int
    outcomes: tuple[ImpactScenarioOutcome, ...]
    algorithm_output_claim: Literal["CALCULATED_NOT_BENCHMARKED"] = (
        "CALCULATED_NOT_BENCHMARKED"
    )
