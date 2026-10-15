"""Typed, versioned living-traceability graph domain models."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from intelise_c3.domain.generation import (
    TraceLinkProvenance,
    TraceRelationType,
    TraceResolutionStatus,
    TraceReviewStatus,
)
from intelise_c3.domain.generation_context import DomainModel, SourceContractVersions


class GraphNodeType(StrEnum):
    REQUIREMENT = "REQUIREMENT"
    UML_ELEMENT = "UML_ELEMENT"
    DESIGN_ANCHOR = "DESIGN_ANCHOR"
    CODE_MODULE = "CODE_MODULE"
    API_OPERATION = "API_OPERATION"
    DATABASE_ARTIFACT = "DATABASE_ARTIFACT"
    TEST_HOOK = "TEST_HOOK"
    UI_ARTIFACT = "UI_ARTIFACT"


class GraphLifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class RequirementCoverageStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "UNRESOLVED"


class GraphSourceIdentity(DomainModel):
    project_id: str
    srs_version: str
    uml_version: str
    generation_context_version: str
    design_context_version: str
    source_contract_versions: SourceContractVersions
    requirement_ids: tuple[str, ...]
    uml_ids: tuple[str, ...]


class TraceGraphNode(DomainModel):
    node_id: str
    node_type: GraphNodeType
    source_identity: str
    label: str
    attributes: dict[str, str | int | bool | None] = Field(default_factory=dict)
    lifecycle_status: GraphLifecycleStatus = GraphLifecycleStatus.ACTIVE
    retired_in_graph_version: int | None = None


class TraceGraphLink(DomainModel):
    link_id: str
    logical_link_id: str
    source_node_id: str
    relation_type: TraceRelationType
    target_node_id: str
    resolution_status: TraceResolutionStatus
    review_status: TraceReviewStatus
    provenance: TraceLinkProvenance
    lifecycle_status: GraphLifecycleStatus = GraphLifecycleStatus.ACTIVE
    retired_in_graph_version: int | None = None
    retirement_reason: str | None = None


class RequirementCoverage(DomainModel):
    requirement_id: str
    status: RequirementCoverageStatus
    implementing_node_ids: tuple[str, ...]
    verifying_node_ids: tuple[str, ...]
    unresolved_link_ids: tuple[str, ...]


class TraceabilityDiagnostics(DomainModel):
    dangling_node_ids: tuple[str, ...]
    unresolved_link_ids: tuple[str, ...]
    missing_evidence: tuple[str, ...]


class TraceabilityCoverageReport(DomainModel):
    policy_version: Literal["C3_COVERAGE_POLICY_V1"] = "C3_COVERAGE_POLICY_V1"
    requirements: tuple[RequirementCoverage, ...]
    verified_count: int
    partial_count: int
    unresolved_count: int
    diagnostics: TraceabilityDiagnostics


class TraceGraphBuild(DomainModel):
    graph_schema_version: Literal["1.0"] = "1.0"
    relation_direction_policy_version: Literal[
        "C3_GRAPH_RELATION_DIRECTION_V1"
    ] | None = None
    graph_id: str
    generation_run_id: str
    source: GraphSourceIdentity
    artifact_digest_sha256: str
    evidence_digest_sha256: str
    manifest_sha256: str
    nodes: tuple[TraceGraphNode, ...]
    links: tuple[TraceGraphLink, ...]
    coverage: TraceabilityCoverageReport
    graph_content_digest_sha256: str


class TraceGraphSnapshot(TraceGraphBuild):
    snapshot_id: str
    graph_version: int
    persisted_at_utc: str


class ArtifactChangeClassification(DomainModel):
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]


class SourceVersionTransitionEvidence(DomainModel):
    classification: Literal["CALLER_ASSERTED_RESEARCH_APPROVAL"] = (
        "CALLER_ASSERTED_RESEARCH_APPROVAL"
    )
    approval_reference: str
    approved_by: str
    acknowledges_source_version_change: Literal[True]
    authenticity_verified: Literal[False] = False


class GraphChangeReport(DomainModel):
    report_version: Literal["1.0"] = "1.0"
    graph_id: str
    base_graph_version: int
    candidate_generation_run_id: str
    artifacts: ArtifactChangeClassification
    added_node_ids: tuple[str, ...]
    removed_node_ids: tuple[str, ...]
    changed_node_ids: tuple[str, ...]
    unchanged_node_ids: tuple[str, ...]
    added_link_ids: tuple[str, ...]
    retired_link_ids: tuple[str, ...]
    preserved_link_ids: tuple[str, ...]
    revalidated_link_ids: tuple[str, ...]
    source_version_changed: bool
    source_transition_evidence: SourceVersionTransitionEvidence | None = None


class GraphUpdateResult(DomainModel):
    snapshot: TraceGraphSnapshot
    change_report: GraphChangeReport


class GroundTruthLink(DomainModel):
    source_node_id: str
    relation_type: TraceRelationType
    target_node_id: str


class ResearchGroundTruth(DomainModel):
    dataset_id: str
    dataset_version: str
    authorship: Literal["RESEARCHER_CURATED"] = "RESEARCHER_CURATED"
    researcher_reference: str
    in_scope_node_ids: tuple[str, ...]
    expected_links: tuple[GroundTruthLink, ...]


class TraceabilityEvaluationReport(DomainModel):
    evaluation_version: Literal["1.1"] = "1.1"
    graph_id: str
    graph_version: int
    ground_truth_dataset_id: str
    ground_truth_dataset_version: str
    ground_truth_authorship: Literal["RESEARCHER_CURATED"]
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float
    recall: float
    f1_score: float
    algorithm_output_claim: Literal["CALCULATED_NOT_BENCHMARKED"] = (
        "CALCULATED_NOT_BENCHMARKED"
    )
