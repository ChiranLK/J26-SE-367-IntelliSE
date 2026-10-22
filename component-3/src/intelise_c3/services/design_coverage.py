"""Pure, deterministic requirement/UML anchor coverage (no store, DB or files).

The link rule mirrors C2_DESIGN_ANCHOR_GRAPH_V1 in the traceability builder: an
accepted C2 anchor connects exactly one requirement to exactly one UML element.
No GenerationManifest is needed.
"""

# Import the coverage result models shown by the Design & Stack page.
from intelise_c3.domain.design_coverage import (
    CoverageDiagnostic,
    CoverageTotals,
    DesignCoverageReport,
    RequirementCoverage,
    RequirementCoverageStatus,
    UmlCoverageStatus,
    UmlElementCoverage,
)

# Import the accepted C1/C2 context and the shared PlantUML parser.
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.services.design_understanding import DesignUnderstandingService

# REQUIREMENT COVERAGE RULES
# Only C2 class and enum elements receive individual coverage rows.
_CLASSIFIER_ELEMENT_TYPES = {"CLASS_ELEMENT", "ENUM_ELEMENT"}


class DesignCoverageService:
    """Report which FRs and class/enum elements are linked by C2 anchors."""

    def __init__(self) -> None:
        # Prepare the shared parser when the coverage service is created.

        # Reuse the same deterministic design parser used by Analyze design.
        self._design = DesignUnderstandingService()

    def build(self, context: GenerationContext) -> DesignCoverageReport:
        # Build the complete requirement coverage report from accepted C1 and C2 data.

        # Parse C2 with the same rules used by the Review the Design section.
        design = self._design.build(context)

        # Keep all valid C2 UML ids for later unknown-anchor checks.
        known_uml = {item.uml_id for item in design.source_uml_elements}

        # Create two lookup tables: requirement to UML and UML to requirement.
        by_requirement: dict[str, set[str]] = {}
        by_uml: dict[str, set[str]] = {}

        # Read every C2 anchor and save the link in both lookup directions.
        for anchor in design.requirement_uml_anchors:
            by_requirement.setdefault(anchor.requirement_id, set()).add(anchor.uml_id)
            by_uml.setdefault(anchor.uml_id, set()).add(anchor.requirement_id)

        # 1. REQUIREMENTS LINKED
        # An FR is linked when at least one C2 UML anchor contains its requirement id.

        # 2. NOT LINKED
        # An FR is not linked when no C2 UML anchor contains its requirement id.

        # 3. QUALITY RULES
        # An NFR is a system-wide quality rule, so a direct class link is not required.

        # Prepare the requirement rows and any missing-link messages.
        requirements: list[RequirementCoverage] = []
        diagnostics: list[CoverageDiagnostic] = []

        # Check each C1 requirement in a stable id order.
        for item in sorted(design.requirements, key=lambda r: r.requirement_id):
            # Find every C2 UML element linked to this requirement.
            uml_ids = tuple(sorted(by_requirement.get(item.requirement_id, ())))

            # Apply the deterministic NFR, linked FR or unlinked FR rule.
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

            # Save the final status shown for this requirement.
            requirements.append(
                RequirementCoverage(
                    requirement_id=item.requirement_id,
                    requirement_type=item.requirement_type,
                    anchored_uml_ids=uml_ids,
                    status=status,
                )
            )

        # 4. CLASSES WITH A REQUIREMENT
        # A class is counted here when a C2 anchor directly links it to a requirement.

        # 5. SUPPORTING CLASSES
        # A parsed class without a direct requirement anchor is reported as extra/supporting.

        # A class/enum is identified by its own C2 element when one exists
        # (matched by name); packages that only carry the diagram element fall
        # back to the diagram's UML id, which the parser records on each class.

        # Resolve each parsed class/enum to its exact C2 UML identity.
        element_ids = {
            item.name: item.uml_id
            for item in design.source_uml_elements
            if item.element_type in _CLASSIFIER_ELEMENT_TYPES
        }

        # Prepare the class/enum coverage rows for the report.
        uml: list[UmlElementCoverage] = []

        # Match each parsed class name to its C2 element id and sort the result.
        resolved = sorted(
            ((element_ids.get(c.name, c.source_uml_id), c) for c in design.classes),
            key=lambda pair: (pair[0], pair[1].name),
        )

        # Mark UML elements as anchored or extra with no linked requirement.
        for uml_id, parsed in resolved:
            # Find every requirement directly linked to this class or enum.
            requirement_ids = tuple(sorted(by_uml.get(uml_id, ())))

            # Apply the linked-class or supporting-class rule.
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

            # Save the final status shown for this class or enum.
            uml.append(
                UmlElementCoverage(
                    uml_id=uml_id,
                    name=parsed.name,
                    kind=parsed.kind.value,
                    anchored_requirement_ids=requirement_ids,
                    status=status,
                )
            )

        # Report anchors that reference a UML identity missing from the package.
        for anchor in sorted(
            design.requirement_uml_anchors, key=lambda a: (a.requirement_id, a.uml_id)
        ):
            # Add a diagnostic when the anchor points to an unknown C2 UML id.
            if anchor.uml_id not in known_uml:
                diagnostics.append(
                    CoverageDiagnostic(
                        code="ANCHOR_UNKNOWN_UML_ELEMENT",
                        subject_id=anchor.anchor_id,
                        message=f"Anchor references unknown UML id '{anchor.uml_id}'.",
                    )
                )

        # Sort messages so the same input always produces the same output order.
        diagnostics.sort(key=lambda d: (d.code, d.subject_id))

        # Calculate the five summary values displayed on the coverage panel.
        totals = CoverageTotals(
            # Card 1: linked functional requirements.
            frs_anchored=sum(r.status is RequirementCoverageStatus.ANCHORED for r in requirements),
            # Card 2: functional requirements without a design link.
            frs_unanchored=sum(
                r.status is RequirementCoverageStatus.UNANCHORED_FR for r in requirements
            ),
            # Card 3: system-wide non-functional quality rules.
            nfrs=sum(r.status is RequirementCoverageStatus.NFR_NOT_APPLICABLE for r in requirements),
            # Card 4: classes or enums directly linked to a requirement.
            uml_anchored=sum(u.status is UmlCoverageStatus.ANCHORED for u in uml),
            # Card 5: classes or enums without a direct requirement link.
            uml_extra=sum(u.status is UmlCoverageStatus.EXTRA_NO_REQUIREMENT for u in uml),
        )

        # Return the detailed rows, five totals and validation messages to the API.
        return DesignCoverageReport(
            requirements=tuple(requirements),
            uml_elements=tuple(uml),
            totals=totals,
            diagnostics=tuple(diagnostics),
        )
