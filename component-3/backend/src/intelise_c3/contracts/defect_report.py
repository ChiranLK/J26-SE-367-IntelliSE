"""Provisional, versioned C4-style defect input for scoped regeneration.

Component 4 is not integrated. Until it is, the only accepted classification is
``SIMULATED_C4_FIXTURE``. Every free-text field here is untrusted data: it may
be wrong, stale, or contain instructions, and is never privileged input for an
LLM or for patch authorization.
"""

from enum import StrEnum
from pathlib import PurePosixPath
import re
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from intelise_c3.domain.generation_context import DomainModel

DEFECT_REPORT_SCHEMA_ID = "C4_DEFECT_REPORT_PROVISIONAL_V1"

Identifier = Annotated[
    str,
    Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

_SAFE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class DefectCategory(StrEnum):
    """Categories C3 can map to a module scope plus recognized-but-unsupported ones."""

    BUSINESS_LOGIC = "BUSINESS_LOGIC"
    API_CONTRACT = "API_CONTRACT"
    DATA_ACCESS = "DATA_ACCESS"
    UI_BEHAVIOR = "UI_BEHAVIOR"
    SECURITY = "SECURITY"
    PERFORMANCE = "PERFORMANCE"
    CONFIGURATION = "CONFIGURATION"
    OTHER = "OTHER"


class DefectSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FailingTestHookType(StrEnum):
    """How a failing test is identified against C3's emitted test evidence."""

    TEST_FILE = "TEST_FILE"
    TEST_SEAM = "TEST_SEAM"


class FailingTestReference(DomainModel):
    test_case_id: Identifier
    hook_type: FailingTestHookType
    hook_ref: Annotated[str, Field(min_length=1, max_length=240)]


class DefectLocation(DomainModel):
    """Optional C4 location claim. It can only corroborate, never authorize."""

    relative_path: Annotated[str, Field(min_length=1, max_length=240)] | None = None
    symbol: Annotated[str, Field(min_length=1, max_length=120)] | None = None

    @field_validator("relative_path")
    @classmethod
    def require_safe_relative_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        path = PurePosixPath(value)
        if (
            "\\" in value
            or path.is_absolute()
            or ".." in path.parts
            or ":" in path.parts[0]
            or path.as_posix() != value
        ):
            raise ValueError("Defect location must be a safe relative POSIX path.")
        return value


class DefectEvidence(DomainModel):
    observed_behavior: Annotated[str, Field(min_length=1, max_length=600)]
    expected_behavior: Annotated[str, Field(min_length=1, max_length=600)]


class DefectItem(DomainModel):
    defect_id: Identifier
    category: DefectCategory
    severity: DefectSeverity
    title: Annotated[str, Field(min_length=1, max_length=160)]
    affected_requirement_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=10)]
    failing_tests: Annotated[tuple[FailingTestReference, ...], Field(min_length=1, max_length=10)]
    api_operation_ids: Annotated[tuple[Identifier, ...], Field(max_length=4)] = ()
    location: DefectLocation | None = None
    evidence: DefectEvidence
    explanation: Annotated[str, Field(min_length=1, max_length=1200)] | None = None

    @field_validator("title")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if _SAFE_CONTROL.search(value):
            raise ValueError("Defect text must not contain control characters.")
        return value

    @model_validator(mode="after")
    def require_unique_references(self) -> "DefectItem":
        if len(set(self.affected_requirement_ids)) != len(self.affected_requirement_ids):
            raise ValueError("Affected requirement IDs must be unique.")
        refs = [(item.hook_type, item.hook_ref) for item in self.failing_tests]
        if len(set(refs)) != len(refs):
            raise ValueError("Failing test hook references must be unique.")
        if len(set(self.api_operation_ids)) != len(self.api_operation_ids):
            raise ValueError("API operation IDs must be unique.")
        return self


class DefectReport(DomainModel):
    """Structured defect input bound to exactly one verified generation run."""

    schema_id: Literal["C4_DEFECT_REPORT_PROVISIONAL_V1"] = DEFECT_REPORT_SCHEMA_ID
    report_version: Literal["1.0"] = "1.0"
    source_classification: Literal["SIMULATED_C4_FIXTURE"]
    defect_report_id: Identifier
    reported_at_utc: Annotated[str, Field(min_length=10, max_length=40)]
    source_generation_run_id: Identifier
    source_artifact_digest_sha256: Sha256Hex
    # Mandatory and strict: the report must name the exact graph snapshot version it
    # was produced against. Absent, null, non-integer, boolean, or < 1 is rejected.
    source_graph_version: Annotated[int, Field(ge=1, strict=True)]
    defects: Annotated[tuple[DefectItem, ...], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def require_unique_defect_ids(self) -> "DefectReport":
        ids = [item.defect_id for item in self.defects]
        if len(set(ids)) != len(ids):
            raise ValueError("Defect IDs must be unique within one report.")
        return self
