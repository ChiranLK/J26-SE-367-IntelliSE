"""Response model for the pure-compute requirement/UML design coverage report."""

from enum import StrEnum
from typing import Literal

from intelise_c3.domain.generation_context import DomainModel

COVERAGE_NOTE = (
    "Anchors are supplied by C2 and are taken as given. This report shows only "
    "whether anchor links exist; it makes no claim that an anchor is semantically "
    "correct or that a design element satisfies its requirement."
)


class RequirementCoverageStatus(StrEnum):
    ANCHORED = "ANCHORED"
    UNANCHORED_FR = "UNANCHORED_FR"
    NFR_NOT_APPLICABLE = "NFR_NOT_APPLICABLE"


class UmlCoverageStatus(StrEnum):
    ANCHORED = "ANCHORED"
    EXTRA_NO_REQUIREMENT = "EXTRA_NO_REQUIREMENT"


class RequirementCoverage(DomainModel):
    requirement_id: str
    requirement_type: Literal["FR", "NFR"] | None
    anchored_uml_ids: tuple[str, ...]
    status: RequirementCoverageStatus


class UmlElementCoverage(DomainModel):
    uml_id: str
    name: str
    kind: str
    anchored_requirement_ids: tuple[str, ...]
    status: UmlCoverageStatus


class CoverageTotals(DomainModel):
    frs_anchored: int
    frs_unanchored: int
    nfrs: int
    uml_anchored: int
    uml_extra: int


class CoverageDiagnostic(DomainModel):
    code: str
    subject_id: str
    message: str


class DesignCoverageReport(DomainModel):
    requirements: tuple[RequirementCoverage, ...]
    uml_elements: tuple[UmlElementCoverage, ...]
    totals: CoverageTotals
    diagnostics: tuple[CoverageDiagnostic, ...]
    note: str = COVERAGE_NOTE
