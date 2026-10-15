"""Immutable normalized design context produced from an accepted input context."""

from enum import StrEnum
from typing import Literal

from intelise_c3.domain.generation_context import (
    DomainModel,
    NormalizedRequirement,
    NormalizedRequirementUmlAnchor,
    NormalizedUiArtifact,
    NormalizedUmlElement,
    SourceContractVersions,
    UpstreamProvenance,
)


class Visibility(StrEnum):
    """Visibility markers supported by the limited PlantUML subset."""

    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    PROTECTED = "PROTECTED"
    PACKAGE = "PACKAGE"
    UNSPECIFIED = "UNSPECIFIED"


class DesignDiagnosticSeverity(StrEnum):
    """Non-fatal diagnostic severity recorded during design understanding."""

    INFO = "INFO"
    WARNING = "WARNING"


class ParsedAttribute(DomainModel):
    """Attribute parsed without changing its C2-supplied name or type."""

    name: str
    type_name: str
    visibility: Visibility


class ParsedMethodParameter(DomainModel):
    """Method parameter parsed from the supported PlantUML member syntax."""

    name: str
    type_name: str


class ParsedMethod(DomainModel):
    """Method parsed without inventing behavior or implementation details."""

    name: str
    parameters: tuple[ParsedMethodParameter, ...]
    return_type: str | None
    visibility: Visibility


class ParsedClass(DomainModel):
    """Class structure extracted from one released C2 UML artifact."""

    source_uml_id: str
    name: str
    attributes: tuple[ParsedAttribute, ...]
    methods: tuple[ParsedMethod, ...]


class ParsedRelationship(DomainModel):
    """Relationship notation preserved with a normalized relationship kind."""

    source_uml_id: str
    source_class: str
    target_class: str
    connector: str
    relationship_type: str
    source_multiplicity: str | None = None
    target_multiplicity: str | None = None
    label: str | None = None


class DesignDiagnostic(DomainModel):
    """Evidence-oriented, non-fatal parser or preservation finding."""

    severity: DesignDiagnosticSeverity
    code: str
    message: str
    source_uml_id: str | None = None


class DesignContext(DomainModel):
    """Versioned design understanding for downstream generation agents."""

    design_context_version: Literal["1.0"] = "1.0"
    generation_context_version: str
    project_id: str
    srs_version: str
    uml_version: str
    source_contract_versions: SourceContractVersions
    upstream_provenance: UpstreamProvenance
    requirements: tuple[NormalizedRequirement, ...]
    source_uml_elements: tuple[NormalizedUmlElement, ...]
    ui_artifacts: tuple[NormalizedUiArtifact, ...]
    requirement_uml_anchors: tuple[NormalizedRequirementUmlAnchor, ...]
    classes: tuple[ParsedClass, ...]
    relationships: tuple[ParsedRelationship, ...]
    diagnostics: tuple[DesignDiagnostic, ...]
