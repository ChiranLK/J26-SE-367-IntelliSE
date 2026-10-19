"""Immutable artifact and evidence manifest for the FR-C3-03/04 MVP."""

from enum import StrEnum
from typing import Literal

from intelise_c3.domain.generation_context import (
    DomainModel,
    NormalizedRequirementUmlAnchor,
    NormalizedUiArtifact,
    SourceContractVersions,
)
from intelise_c3.domain.llm import LLMInferenceMetadata


class ArtifactOrigin(StrEnum):
    TEMPLATE = "TEMPLATE"
    LOCAL_LLM = "LOCAL_LLM"


class GeneratedArtifactType(StrEnum):
    DOCUMENTATION = "DOCUMENTATION"
    CONFIGURATION = "CONFIGURATION"
    FRONTEND = "FRONTEND"
    API = "API"
    CONTROLLER = "CONTROLLER"
    BUSINESS_LOGIC = "BUSINESS_LOGIC"
    REPOSITORY = "REPOSITORY"
    DATABASE = "DATABASE"
    TEST = "TEST"


class TraceEntityType(StrEnum):
    GENERATION_RUN = "GENERATION_RUN"
    REQUIREMENT = "REQUIREMENT"
    UML_ELEMENT = "UML_ELEMENT"
    UML_ANCHOR = "UML_ANCHOR"
    UI_ARTIFACT = "UI_ARTIFACT"
    FILE = "FILE"
    API_OPERATION = "API_OPERATION"
    DATABASE_TABLE = "DATABASE_TABLE"
    DATABASE_COLUMN = "DATABASE_COLUMN"
    TEST_SEAM = "TEST_SEAM"


class TraceRelationType(StrEnum):
    DERIVED_FROM = "DERIVED_FROM"
    IMPLEMENTS = "IMPLEMENTS"
    EXPOSES = "EXPOSES"
    DEFINES = "DEFINES"
    PERSISTS_TO = "PERSISTS_TO"
    VERIFIED_BY = "VERIFIED_BY"


class TraceResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


class TraceReviewStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class SourceIdentitySnapshot(DomainModel):
    project_id: str
    srs_version: str
    uml_version: str
    generation_context_version: str
    design_context_version: str
    source_contract_versions: SourceContractVersions
    requirement_ids: tuple[str, ...]
    uml_ids: tuple[str, ...]
    design_anchor_ids: tuple[str, ...]
    requirement_uml_anchors: tuple[NormalizedRequirementUmlAnchor, ...]
    ui_artifacts: tuple[NormalizedUiArtifact, ...]
    c1_approval_provenance_ref: str
    c1_validation_report_ref: str
    c2_validation_report_ref: str


class StackApprovalEvidence(DomainModel):
    classification: Literal["CALLER_ASSERTED_PROVISIONAL_APPROVAL"] = (
        "CALLER_ASSERTED_PROVISIONAL_APPROVAL"
    )
    status: str
    approval_reference: str
    approved_by: str
    acknowledged_provisional_policy: bool
    authenticity_verified: Literal[False] = False


class GeneratedFileRecord(DomainModel):
    file_id: str
    relative_path: str
    module_identity: str
    artifact_type: GeneratedArtifactType
    origin: ArtifactOrigin
    sha256: str
    size_bytes: int
    requirement_ids: tuple[str, ...] = ()
    uml_ids: tuple[str, ...] = ()
    design_anchor_ids: tuple[str, ...] = ()
    ui_artifact_ids: tuple[str, ...] = ()
    api_operation_ids: tuple[str, ...] = ()
    database_entity_ids: tuple[str, ...] = ()
    test_seam_ids: tuple[str, ...] = ()
    # Added after manifest v2.0 was introduced. Optional keeps historical
    # manifests parseable; new generation runs always populate it.
    created_in_generation_run_id: str | None = None


class ApiOperationIdentity(DomainModel):
    operation_id: str
    method: str
    route_path: str
    request_schema: str | None = None
    success_response_schema: str | None = None
    success_status: int


class ApiArtifactReference(DomainModel):
    reference_id: str
    definition_path: str
    operations: tuple[ApiOperationIdentity, ...]


class DatabaseColumnIdentity(DomainModel):
    column_id: str
    name: str
    data_type: str
    nullable: bool
    primary_key: bool = False


class DatabaseTableIdentity(DomainModel):
    table_id: str
    name: str
    columns: tuple[DatabaseColumnIdentity, ...]


class DatabaseArtifactReference(DomainModel):
    reference_id: str
    script_path: str
    persistence_mode: Literal["SCRIPT_ONLY"] = "SCRIPT_ONLY"
    runtime_repository_mode: Literal["IN_MEMORY"] = "IN_MEMORY"
    tables: tuple[DatabaseTableIdentity, ...]


class TestSeamReference(DomainModel):
    reference_id: str
    module_path: str
    seam_type: Literal["INJECTED_REPOSITORY"] = "INJECTED_REPOSITORY"
    description: str


class TraceLinkProvenance(DomainModel):
    evidence_kind: Literal[
        "SOURCE_C2_ANCHOR",
        "DETERMINISTIC_MAPPING_RULE",
        "UNRESOLVED_SOURCE_REFERENCE",
    ]
    mapping_rule_id: str
    evidence_refs: tuple[str, ...]
    details: str


class TraceabilityLink(DomainModel):
    link_id: str
    source_entity_type: TraceEntityType
    source_id: str
    relation_type: TraceRelationType
    target_entity_type: TraceEntityType
    target_id: str
    resolution_status: TraceResolutionStatus
    review_status: TraceReviewStatus
    provenance: TraceLinkProvenance
    # Optional only for historical manifest compatibility.
    created_in_generation_run_id: str | None = None


class TraceabilityEvidence(DomainModel):
    mapping_policy_version: str
    requirement_uml_anchors: tuple[NormalizedRequirementUmlAnchor, ...]
    ui_artifacts: tuple[NormalizedUiArtifact, ...]
    links: tuple[TraceabilityLink, ...]


class CanonicalInputHashes(DomainModel):
    generation_context_sha256: str
    design_context_sha256: str
    stack_selection_report_sha256: str
    approval_input_sha256: str
    prompt_text_sha256: str | None
    prompt_request_sha256: str | None


class RagModuleRetrieval(DomainModel):
    module_path: str
    task: str
    stack: str
    layer: str
    retrieved_rule_ids: tuple[str, ...]
    applied_to_prompt: bool


class RagRetrievalEvidence(DomainModel):
    evidence_version: Literal["1.0"] = "1.0"
    enabled: bool
    backend: Literal["off", "filter", "chroma"]
    embedding_model: str | None
    rule_corpus_sha256: str | None
    retrievals: tuple[RagModuleRetrieval, ...]


class RunEvidence(DomainModel):
    evidence_schema_version: Literal["1.0"] = "1.0"
    canonicalization: Literal["C3_CANONICAL_JSON_V1"] = "C3_CANONICAL_JSON_V1"
    hash_algorithm: Literal["SHA-256"] = "SHA-256"
    input_hashes: CanonicalInputHashes
    prompt_template_version: str | None
    generator_version: str
    template_set_version: str
    rag: RagRetrievalEvidence | None = None
    evidence_digest_sha256: str
    authenticity_claim: Literal[False] = False


class GenerationManifest(DomainModel):
    manifest_version: Literal["2.0"] = "2.0"
    generation_run_id: str
    generated_at_utc: str
    generation_mode: str
    source: SourceIdentitySnapshot
    selected_stack_id: str
    selected_frontend: str
    selected_backend: str
    stack_approval: StackApprovalEvidence
    files: tuple[GeneratedFileRecord, ...]
    api_references: tuple[ApiArtifactReference, ...]
    database_references: tuple[DatabaseArtifactReference, ...]
    test_seams: tuple[TestSeamReference, ...]
    traceability: TraceabilityEvidence
    llm_inference: LLMInferenceMetadata | None
    artifact_digest_sha256: str
    run_evidence: RunEvidence
    execution_status: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"
    trust_boundary: str


class GenerationRunResult(DomainModel):
    workspace_relative_path: str
    manifest_relative_path: str
    manifest: GenerationManifest
