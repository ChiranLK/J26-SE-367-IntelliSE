"""Versioned C1/C2 (2.0) contract validation for the hybrid pipeline.

The v2 package is validated for approval, release status, version agreement,
stable IDs, anchors and override binding. It is then mapped onto the existing
v1 provisional contract so that the established ``InputValidationService`` and
``DesignUnderstandingService`` are reused instead of duplicated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import status

from intelise_c3.contracts.hybrid import (
    C1ApprovalStatusV2,
    C2ReleaseStatusV2,
    EvidenceClass,
    HumanOverrideScope,
    HybridInputPackage,
    InputClassification,
)
from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService

# Version written into every report so validation evidence is reproducible.
CONTRACT_VALIDATOR_VERSION = "c3-hybrid-contract-validator-1.0.0"


# Result model returned after the contract rules run.
@dataclass
class ContractReport:
    """Store the C1/C2 validation decision, findings, evidence, and applied rules."""

    status: str
    input_classification: str
    c1_evidence_class: str
    c2_evidence_class: str
    project_id: str
    srs_version: str
    uml_version: str
    findings: list[dict[str, str]] = field(default_factory=list)
    override_applied: dict[str, Any] | None = None
    rule_ids: tuple[str, ...] = ("R-INPUT-001@1.0.0", "R-INPUT-002@1.0.0")

    def as_json(self) -> dict[str, Any]:
        # Convert the report into the API/manifest JSON representation.
        return {
            "validator_version": CONTRACT_VALIDATOR_VERSION,
            "status": self.status,
            "input_classification": self.input_classification,
            "c1_evidence_class": self.c1_evidence_class,
            "c2_evidence_class": self.c2_evidence_class,
            "project_id": self.project_id,
            "srs_version": self.srs_version,
            "uml_version": self.uml_version,
            "findings": self.findings,
            "override_applied": self.override_applied,
            "rule_ids": list(self.rule_ids),
            "provenance_claim": (
                "Reference strings are opaque provenance. C3 checks presence and version binding; "
                "it does not authenticate C1 client approval or C2 validation."
            ),
            "simulated": EvidenceClass.SIMULATED_FIXTURE.value in {self.c1_evidence_class, self.c2_evidence_class},
        }


# Successful output passed to the generation pipeline.
@dataclass
class ValidatedInput:
    """Bundle the accepted C1/C2 package with its normalized generation and design contexts."""

    package: HybridInputPackage
    report: ContractReport
    generation_context: GenerationContext
    design_context: DesignContext


def _finding(findings: list[dict[str, str]], code: str, field_name: str, message: str) -> None:
    # Add one machine-readable validation error to the shared findings list.
    findings.append({"code": code, "field": field_name, "message": message})


def _to_v1(package: HybridInputPackage, c2_release_for_v1: str) -> ProvisionalInputPackage:
    # Map the accepted v2 contract into the established v1 validation models.
    c1, c2 = package.c1, package.c2
    return ProvisionalInputPackage.model_validate(
        {
            "contract_version": "1.0",
            # Preserve approved C1 project, SRS, provenance, and requirements.
            "c1": {
                "contract_version": "1.0",
                "project_id": c1.project_id,
                "srs_version": c1.srs_version,
                "approval_status": "APPROVED",
                "approval_provenance_ref": c1.approval_reference,
                "validation_report_ref": c1.provenance.quality_report_ref,
                "design_uml_version_ref": c2.uml_version,
                "requirements": [
                    {
                        "requirement_id": requirement.requirement_id,
                        "title": requirement.title,
                        "status": "APPROVED",
                        "requirement_type": requirement.requirement_type,
                    }
                    for requirement in c1.requirements
                ],
            },
            # Preserve released C2 design metadata and traceability evidence.
            "c2": {
                "contract_version": "1.0",
                "project_id": c2.project_id,
                "source_srs_version": c2.srs_version,
                "uml_version": c2.uml_version,
                "release_status": c2_release_for_v1,
                "validation_state": "PASSED",
                "validation_report_ref": c2.validation_reports.semantic_report_ref,
                # Convert CLASS/USE_CASE artifacts into v1 UML elements.
                "uml_elements": [
                    {
                        "uml_id": artifact.uml_id,
                        "element_type": "CLASS_DIAGRAM" if artifact.diagram_type == "CLASS" else "USE_CASE_DIAGRAM",
                        "name": artifact.name,
                        "plantuml_source": artifact.plantuml_source,
                    }
                    for artifact in c2.uml_artifacts
                ],
                # Convert each C2 screen into a traceable v1 UI artifact.
                "ui_artifacts": [
                    {
                        "ui_id": screen.screen_id,
                        "artifact_type": "UI_SPECIFICATION",
                        "source_ref": f"c2-ui-spec:{screen.screen_id}",
                    }
                    for screen in c2.ui_specification
                ],
                # Preserve requirement-to-UML links for downstream traceability.
                "requirement_uml_anchors": [
                    {
                        "anchor_id": anchor.anchor_id,
                        "requirement_id": anchor.requirement_id,
                        "uml_id": anchor.uml_id,
                    }
                    for anchor in c2.requirement_uml_anchors
                ],
            },
        }
    )


# C1/C2 INPUT VALIDATION RULES
# C1: checks SRS/requirement approvals, unique IDs, and FR-to-UML coverage.
# C2: checks project/version matching, release status, UML anchors, UI links, and design elements.
# Returns normalized generation/design contexts, or rejects the package with validation findings.
class HybridContractValidator:
    """Run deterministic C1/C2 checks and build contexts for an accepted package."""

    def validate(self, package: HybridInputPackage) -> ValidatedInput:
        c1, c2 = package.c1, package.c2
        findings: list[dict[str, str]] = []
        override_applied: dict[str, Any] | None = None

        # These are deterministic C1/C2 contract checks. They do not use the
        # Knowledge Base or an LLM to decide whether an input is valid.

        # C1 acceptance gate: the SRS and every requirement must be approved.
        if c1.approval_status is not C1ApprovalStatusV2.CLIENT_APPROVED:
            _finding(findings, "C1_NOT_CLIENT_APPROVED", "c1.approval_status",
                     f"C1 SRS {c1.srs_version} is {c1.approval_status.value}; only CLIENT_APPROVED versions are accepted.")
        for index, requirement in enumerate(c1.requirements):
            if requirement.approval_status is not C1ApprovalStatusV2.CLIENT_APPROVED:
                _finding(findings, "C1_REQUIREMENT_NOT_APPROVED", f"c1.requirements[{index}].approval_status",
                         f"Requirement {requirement.requirement_id} is {requirement.approval_status.value}.")

        # Cross-document identity gate: C1 and C2 must describe the same
        # project and the C2 design must target the approved C1 SRS version.
        if c1.project_id != c2.project_id:
            _finding(findings, "PROJECT_ID_MISMATCH", "c2.project_id",
                     f"C1 project {c1.project_id} does not match C2 project {c2.project_id}.")
        if c1.srs_version != c2.srs_version:
            _finding(findings, "SRS_VERSION_MISMATCH", "c2.srs_version",
                     f"C2 design was released for SRS {c2.srs_version}, not the approved SRS {c1.srs_version}.")

        # C2 release gate: only validated designs are accepted automatically.
        # A review-state design needs an explicit override bound to its exact
        # project, SRS version, and UML version.
        if c2.release_status is C2ReleaseStatusV2.NEEDS_HUMAN_REVIEW:
            override = package.human_override
            if override is None or override.scope is not HumanOverrideScope.C2_NEEDS_HUMAN_REVIEW_RELEASE:
                _finding(findings, "C2_NEEDS_HUMAN_REVIEW", "c2.release_status",
                         "C2 release NEEDS_HUMAN_REVIEW; automatic generation requires an explicit, version-bound human override.")
            elif (override.bound_project_id, override.bound_srs_version, override.bound_uml_version) != (
                c2.project_id, c2.srs_version, c2.uml_version
            ):
                _finding(findings, "OVERRIDE_VERSION_MISMATCH", "human_override",
                         "The human override is bound to a different project/SRS/UML version and cannot be applied.")
            else:
                override_applied = override.model_dump(mode="json")
        elif c2.release_status is not C2ReleaseStatusV2.VALIDATED:
            _finding(findings, "C2_RELEASE_NOT_VALIDATED", "c2.release_status",
                     f"C2 release status {c2.release_status.value} cannot be used for generation"
                     + (" and cannot be overridden." if c2.release_status is C2ReleaseStatusV2.FAILED else "."))
        if package.human_override is not None and override_applied is None and c2.release_status is C2ReleaseStatusV2.VALIDATED:
            _finding(findings, "OVERRIDE_NOT_APPLICABLE", "human_override",
                     "A human override was supplied for a VALIDATED release; overrides are only accepted where they are needed.")

        # Reference-integrity gate: IDs must be unique and every C2 anchor or
        # UI reference must point to a requirement/UML artifact supplied by
        # this package. Every functional requirement needs a UML anchor.

        # Collect the stable C1 requirement IDs and reject duplicates.
        requirement_ids = [requirement.requirement_id for requirement in c1.requirements]
        if len(set(requirement_ids)) != len(requirement_ids):
            _finding(findings, "DUPLICATE_REQUIREMENT_ID", "c1.requirements", "Stable requirement IDs must be unique.")
        known_requirements = set(requirement_ids)
        uml_ids = {artifact.uml_id for artifact in c2.uml_artifacts}
        anchored: set[str] = set()

        # Confirm every C2 anchor points to an existing C1 requirement and UML artifact.
        for index, anchor in enumerate(c2.requirement_uml_anchors):
            if anchor.requirement_id not in known_requirements:
                _finding(findings, "UNKNOWN_REQUIREMENT_REFERENCE", f"c2.requirement_uml_anchors[{index}]",
                         f"Anchor {anchor.anchor_id} references unknown requirement {anchor.requirement_id}.")
            if anchor.uml_id not in uml_ids:
                _finding(findings, "UNKNOWN_UML_REFERENCE", f"c2.requirement_uml_anchors[{index}]",
                         f"Anchor {anchor.anchor_id} references unknown UML artifact {anchor.uml_id}.")
            anchored.add(anchor.requirement_id)

        # Require every functional requirement to have at least one released UML link.
        for requirement in c1.requirements:
            if requirement.requirement_type == "FR" and requirement.requirement_id not in anchored:
                _finding(findings, "FR_WITHOUT_UML_ANCHOR", "c2.requirement_uml_anchors",
                         f"Functional requirement {requirement.requirement_id} has no released UML anchor.")

        # Confirm each C2 UI screen references only known C1 requirements.
        for screen in c2.ui_specification:
            for requirement_id in screen.requirement_ids:
                if requirement_id not in known_requirements:
                    _finding(findings, "UNKNOWN_REQUIREMENT_REFERENCE", f"c2.ui_specification.{screen.screen_id}",
                             f"UI screen {screen.screen_id} references unknown requirement {requirement_id}.")

        # Build the auditable ACCEPTED/REJECTED report for this validation attempt.
        report = ContractReport(
            status="REJECTED" if findings else "ACCEPTED",
            input_classification=package.input_classification.value,
            c1_evidence_class=c1.evidence_class.value,
            c2_evidence_class=c2.evidence_class.value,
            project_id=c1.project_id,
            srs_version=c1.srs_version,
            uml_version=c2.uml_version,
            findings=findings,
            override_applied=override_applied,
        )

        # Stop before normalization when any contract rule failed.
        if findings:
            raise _rejected(findings)

        # After the contract checks pass, reuse the established v1 normalizer
        # and parse the released class diagram into a design context.
        try:
            generation_context = InputValidationService().validate(_to_v1(package, "VALIDATED"))
            design_context = DesignUnderstandingService().build(generation_context)
        except ApplicationError as error:
            raise ApplicationError(
                [ErrorDetail(code=e.code, field=e.field, message=e.message) for e in error.errors],
                status_code=status.HTTP_409_CONFLICT,
            ) from error

        # Semantic design gate: referenced class names and constraint targets
        # must exist in the parsed C2 class diagram.
        class_names = {parsed.name for parsed in design_context.classes}
        late: list[dict[str, str]] = []

        # Confirm every anchor names a class parsed from the C2 class diagram.
        for index, anchor in enumerate(c2.requirement_uml_anchors):
            if anchor.uml_element not in class_names:
                _finding(late, "UNKNOWN_UML_ELEMENT", f"c2.requirement_uml_anchors[{index}].uml_element",
                         f"Anchor {anchor.anchor_id} names class {anchor.uml_element}, which the released diagram does not declare.")

        # Confirm each C1 constraint targets a real C2 class attribute.
        for requirement in c1.requirements:
            for constraint in requirement.constraints:
                class_name, field_name = constraint.target.split(".", 1)
                parsed = next((item for item in design_context.classes if item.name == class_name), None)
                if parsed is None or field_name not in {attribute.name for attribute in parsed.attributes}:
                    _finding(late, "CONSTRAINT_TARGET_NOT_IN_DESIGN", f"c1.{requirement.requirement_id}.{constraint.constraint_id}",
                             f"Constraint target {constraint.target} is not an attribute in the released design.")

        # Reject semantic design findings; otherwise return the fully normalized input.
        if late:
            raise _rejected(late)
        return ValidatedInput(package, report, generation_context, design_context)


def _rejected(findings: list[dict[str, str]]) -> ApplicationError:
    # Convert internal findings into the standard HTTP 409 application error.
    return ApplicationError(
        [ErrorDetail(code=f["code"], field=f["field"], message=f["message"]) for f in findings],
        status_code=status.HTTP_409_CONFLICT,
    )


def classify_legacy_package(_package: ProvisionalInputPackage) -> str:
    """The 1.0 plain-text/PlantUML adapter output is always provisional demo input."""

    # Legacy adapter inputs cannot claim validated upstream C1/C2 provenance.
    return InputClassification.PROVISIONAL_DEMO_INPUT.value
