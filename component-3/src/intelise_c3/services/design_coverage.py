"""Pure, deterministic requirement/UML anchor coverage (no store, DB or files).

The link rule mirrors C2_DESIGN_ANCHOR_GRAPH_V1 in the traceability builder: an
accepted C2 anchor connects exactly one requirement to exactly one UML element.
No GenerationManifest is needed.
"""

from intelise_c3.domain.design_coverage import (
    CoverageDiagnostic,
    CoverageTotals,
    DesignCoverageReport,
    RequirementCoverage,
    RequirementCoverageStatus,
    UmlCoverageStatus,
    UmlElementCoverage,
)
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.services.design_understanding import DesignUnderstandingService

_CLASSIFIER_ELEMENT_TYPES = {"CLASS_ELEMENT", "ENUM_ELEMENT"}


class DesignCoverageService:
    """Report which FRs and class/enum elements are linked by C2 anchors."""

    def __init__(self) -> None:
        self._design = DesignUnderstandingService()

    def build(self, context: GenerationContext) -> DesignCoverageReport:
        design = self._design.build(context)
        known_uml = {item.uml_id for item in design.source_uml_elements}
        by_requirement: dict[str, set[str]] = {}
        by_uml: dict[str, set[str]] = {}
        for anchor in design.requirement_uml_anchors:
            by_requirement.setdefault(anchor.requirement_id, set()).add(anchor.uml_id)
            by_uml.setdefault(anchor.uml_id, set()).add(anchor.requirement_id)

        requirements: list[RequirementCoverage] = []
        diagnostics: list[CoverageDiagnostic] = []
        for item in sorted(design.requirements, key=lambda r: r.requirement_id):
            uml_ids = tuple(sorted(by_requirement.get(item.requirement_id, ())))
            if item.requirement_type == "NFR":
                status = RequirementCoverageStatus.NFR_NOT_APPLICABLE
            elif uml_ids:
                status = RequirementCoverageStatus.ANCHORED
            else:
                status = RequirementCoverageStatus.UNANCHORED_FR
                diagnostics.append(
                    CoverageDiagnostic(
                        code="FR_WITHOUT_ANCHOR",
                        subject_id=item.requirement_id,
                        message="Functional (or untyped) requirement has no C2 UML anchor.",
                    )
                )
            requirements.append(
                RequirementCoverage(
                    requirement_id=item.requirement_id,
                    requirement_type=item.requirement_type,
                    anchored_uml_ids=uml_ids,
                    status=status,
                )
            )

        # A class/enum is identified by its own C2 element when one exists
        # (matched by name); packages that only carry the diagram element fall
        # back to the diagram's UML id, which the parser records on each class.
        element_ids = {
            item.name: item.uml_id
            for item in design.source_uml_elements
            if item.element_type in _CLASSIFIER_ELEMENT_TYPES
        }
        uml: list[UmlElementCoverage] = []
        resolved = sorted(
            ((element_ids.get(c.name, c.source_uml_id), c) for c in design.classes),
            key=lambda pair: (pair[0], pair[1].name),
        )
        for uml_id, parsed in resolved:
            requirement_ids = tuple(sorted(by_uml.get(uml_id, ())))
            if requirement_ids:
                status = UmlCoverageStatus.ANCHORED
            else:
                status = UmlCoverageStatus.EXTRA_NO_REQUIREMENT
                diagnostics.append(
                    CoverageDiagnostic(
                        code="UML_ELEMENT_WITHOUT_REQUIREMENT",
                        subject_id=uml_id,
                        message="Class/enum has no requirement anchored to it.",
                    )
                )
            uml.append(
                UmlElementCoverage(
                    uml_id=uml_id,
                    name=parsed.name,
                    kind=parsed.kind.value,
                    anchored_requirement_ids=requirement_ids,
                    status=status,
                )
            )

        for anchor in sorted(
            design.requirement_uml_anchors, key=lambda a: (a.requirement_id, a.uml_id)
        ):
            if anchor.uml_id not in known_uml:
                diagnostics.append(
                    CoverageDiagnostic(
                        code="ANCHOR_UNKNOWN_UML_ELEMENT",
                        subject_id=anchor.anchor_id,
                        message=f"Anchor references unknown UML id '{anchor.uml_id}'.",
                    )
                )

        diagnostics.sort(key=lambda d: (d.code, d.subject_id))
        totals = CoverageTotals(
            frs_anchored=sum(r.status is RequirementCoverageStatus.ANCHORED for r in requirements),
            frs_unanchored=sum(
                r.status is RequirementCoverageStatus.UNANCHORED_FR for r in requirements
            ),
            nfrs=sum(r.status is RequirementCoverageStatus.NFR_NOT_APPLICABLE for r in requirements),
            uml_anchored=sum(u.status is UmlCoverageStatus.ANCHORED for u in uml),
            uml_extra=sum(u.status is UmlCoverageStatus.EXTRA_NO_REQUIREMENT for u in uml),
        )
        return DesignCoverageReport(
            requirements=tuple(requirements),
            uml_elements=tuple(uml),
            totals=totals,
            diagnostics=tuple(diagnostics),
        )
