"""Normalized internal input context for future generation workflows."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, model_serializer


class DomainModel(BaseModel):
    """Immutable base for internal Component 3 domain values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceContractVersions(DomainModel):
    """Exact provisional contract versions received from upstream inputs."""

    envelope: str
    c1: str
    c2: str


class UpstreamProvenance(DomainModel):
    """Opaque upstream references retained without authenticity claims."""

    c1_approval_provenance_ref: str
    c1_validation_report_ref: str
    c2_validation_report_ref: str


class NormalizedRequirement(DomainModel):
    """C1 requirement identity preserved for downstream traceability."""

    requirement_id: str
    title: str
    approval_status: Literal["APPROVED"]
    requirement_type: Literal["FR", "NFR"] | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_requirement_type(self, handler: SerializerFunctionWrapHandler) -> dict:
        # Omitted while None so digests of legacy contexts are unchanged.
        data = handler(self)
        if self.requirement_type is None:
            data.pop("requirement_type", None)
        return data


class NormalizedUmlElement(DomainModel):
    """C2 UML identity preserved for downstream traceability."""

    uml_id: str
    element_type: str
    name: str
    plantuml_source: str | None = None


class NormalizedUiArtifact(DomainModel):
    """C2 structured UI artifact preserved for future generation."""

    ui_id: str
    artifact_type: str
    source_ref: str


class NormalizedRequirementUmlAnchor(DomainModel):
    """Validated C2 requirement-to-UML anchor preserved unchanged."""

    anchor_id: str
    requirement_id: str
    uml_id: str
    uml_element: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_uml_element(self, handler: SerializerFunctionWrapHandler) -> dict:
        data = handler(self)
        if self.uml_element is None:
            data.pop("uml_element", None)
        return data


class GenerationContext(DomainModel):
    """Versioned, normalized context allowed to proceed to later C3 stages."""

    context_version: Literal["1.0"] = "1.0"
    project_id: str
    srs_version: str
    uml_version: str
    source_contract_versions: SourceContractVersions
    upstream_provenance: UpstreamProvenance
    requirements: tuple[NormalizedRequirement, ...]
    uml_elements: tuple[NormalizedUmlElement, ...]
    ui_artifacts: tuple[NormalizedUiArtifact, ...]
    requirement_uml_anchors: tuple[NormalizedRequirementUmlAnchor, ...]
