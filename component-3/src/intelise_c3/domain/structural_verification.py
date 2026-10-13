"""Machine-readable results for deterministic design-to-code verification."""

from enum import StrEnum
from typing import Literal

from intelise_c3.domain.generation_context import DomainModel, SourceContractVersions


class StructuralFindingStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class StructuralFindingCategory(StrEnum):
    DESIGN = "DESIGN"
    MODULE = "MODULE"
    FLOW = "FLOW"
    API = "API"
    UI = "UI"
    REPOSITORY = "REPOSITORY"
    DATABASE = "DATABASE"
    ARCHITECTURE = "ARCHITECTURE"
    LIMITATION = "LIMITATION"


class StructuralVerificationFinding(DomainModel):
    finding_id: str
    rule_id: str
    category: StructuralFindingCategory
    status: StructuralFindingStatus
    message: str
    affected_module_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    uml_ids: tuple[str, ...] = ()
    evidence_paths: tuple[str, ...] = ()
    expected: tuple[str, ...] = ()
    observed: tuple[str, ...] = ()
    remediation: str | None = None


class StructuralVerificationSummary(DomainModel):
    pass_count: int
    fail_count: int
    review_required_count: int


class StructuralVerificationReport(DomainModel):
    report_version: Literal["1.0"] = "1.0"
    rule_set_version: Literal["C3_TASK_MVP_STRUCTURAL_RULES_V1"] = (
        "C3_TASK_MVP_STRUCTURAL_RULES_V1"
    )
    generation_run_id: str
    project_id: str
    srs_version: str
    uml_version: str
    source_contract_versions: SourceContractVersions
    requirement_ids: tuple[str, ...]
    uml_ids: tuple[str, ...]
    artifact_digest_sha256: str
    evidence_digest_sha256: str
    design_context_sha256: str
    verified_at_utc: str
    overall_status: StructuralFindingStatus
    summary: StructuralVerificationSummary
    findings: tuple[StructuralVerificationFinding, ...]
    execution_claim: Literal["STATIC_INSPECTION_ONLY_NOT_EXECUTED"] = (
        "STATIC_INSPECTION_ONLY_NOT_EXECUTED"
    )
    component4_claim: Literal[False] = False
