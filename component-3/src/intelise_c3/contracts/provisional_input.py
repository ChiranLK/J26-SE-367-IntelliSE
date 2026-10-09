"""Provisional C1/C2 input schemas for FR-C3-01.

These models describe an assumed transport contract only. Their presence and
the presence of reference strings do not authenticate approval or validation.
The owning Component 1 and Component 2 teams must replace or approve these
schemas before production integration.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[
    str,
    Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
        description="Provisional stable identifier; preserved without rewriting.",
    ),
]
NonEmptyText = Annotated[str, Field(min_length=1)]


class ProvisionalContractModel(BaseModel):
    """Strict and immutable base for unapproved upstream transport schemas."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class C1ApprovalStatus(StrEnum):
    """Provisional C1 approval states."""

    APPROVED = "APPROVED"
    DRAFT = "DRAFT"
    REJECTED = "REJECTED"


class C1Requirement(ProvisionalContractModel):
    """Requirement identity and state supplied by the simulated C1 contract."""

    requirement_id: Identifier
    title: NonEmptyText
    status: C1ApprovalStatus


class C1ApprovedSRS(ProvisionalContractModel):
    """Provisional representation of a client-approved C1 SRS release."""

    contract_version: NonEmptyText
    project_id: Identifier
    srs_version: Identifier
    approval_status: C1ApprovalStatus
    approval_provenance_ref: NonEmptyText
    validation_report_ref: NonEmptyText
    requirements: Annotated[tuple[C1Requirement, ...], Field(min_length=1)]


class C2ReleaseStatus(StrEnum):
    """Provisional C2 release states."""

    VALIDATED = "VALIDATED"
    DRAFT = "DRAFT"
    REJECTED = "REJECTED"


class C2ValidationState(StrEnum):
    """Provisional C2 validation outcomes."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class C2UmlElement(ProvisionalContractModel):
    """Stable UML identity released by the simulated C2 contract."""

    uml_id: Identifier
    element_type: NonEmptyText
    name: NonEmptyText


class C2UiArtifact(ProvisionalContractModel):
    """Structured UI or wireframe artifact released by simulated C2."""

    ui_id: Identifier
    artifact_type: NonEmptyText
    source_ref: NonEmptyText


class RequirementUmlAnchor(ProvisionalContractModel):
    """C2-owned requirement-to-UML association inherited by Component 3."""

    anchor_id: Identifier
    requirement_id: Identifier
    uml_id: Identifier


class C2DesignRelease(ProvisionalContractModel):
    """Provisional validated design release supplied by Component 2."""

    contract_version: NonEmptyText
    project_id: Identifier
    source_srs_version: Identifier
    uml_version: Identifier
    release_status: C2ReleaseStatus
    validation_state: C2ValidationState
    validation_report_ref: NonEmptyText
    uml_elements: Annotated[tuple[C2UmlElement, ...], Field(min_length=1)]
    ui_artifacts: Annotated[tuple[C2UiArtifact, ...], Field(min_length=1)]
    requirement_uml_anchors: Annotated[
        tuple[RequirementUmlAnchor, ...], Field(min_length=1)
    ]


class ProvisionalInputPackage(ProvisionalContractModel):
    """Combined, provisional C1/C2 input envelope accepted by Component 3."""

    contract_version: NonEmptyText
    c1: C1ApprovedSRS
    c2: C2DesignRelease
