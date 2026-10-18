"""Immutable intermediate specification for the supported CRUD generator profile."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from intelise_c3.domain.generation_context import DomainModel


class CrudScalarType(StrEnum):
    """Scalar field types supported by the Stage 1 deterministic renderer."""

    STRING = "STRING"
    INTEGER = "INTEGER"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"


class CrudOperation(StrEnum):
    """Operations that must be evidenced by both requirements and UML methods."""

    LIST = "LIST"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class CrudFieldSpec(DomainModel):
    """One source-grounded entity field and its deterministic validation policy."""

    source_uml_id: str
    name: str
    scalar_type: CrudScalarType
    required: Literal[True] = True
    generated: bool = False
    input_control: Literal["text", "number", "checkbox", "date"]


class CrudEntitySpec(DomainModel):
    """One independent CRUD aggregate supported by the Stage 1 profile."""

    source_uml_id: str
    class_name: str
    variable_name: str
    plural_class_name: str
    route_segment: str
    table_name: str
    service_class_name: str
    repository_class_name: str
    fields: tuple[CrudFieldSpec, ...] = Field(min_length=2)
    operations: tuple[CrudOperation, ...] = Field(min_length=4, max_length=4)
    requirement_ids: tuple[str, ...] = Field(min_length=1)
    design_anchor_ids: tuple[str, ...] = Field(min_length=1)


class CrudApplicationSpec(DomainModel):
    """Versioned normalized input to every deterministic Stage 1 renderer.

    The spec is internal Component 3 state. It preserves upstream identities but
    does not claim that derived class/member mappings are authoritative C2 data.
    """

    spec_version: Literal["1.0"] = "1.0"
    profile: Literal["INDEPENDENT_CRUD_ENTITIES_V1"] = (
        "INDEPENDENT_CRUD_ENTITIES_V1"
    )
    project_id: str
    srs_version: str
    uml_version: str
    application_name: str
    application_slug: str
    source_requirement_ids: tuple[str, ...]
    source_uml_ids: tuple[str, ...]
    source_ui_artifact_ids: tuple[str, ...]
    entities: tuple[CrudEntitySpec, ...] = Field(min_length=1)

