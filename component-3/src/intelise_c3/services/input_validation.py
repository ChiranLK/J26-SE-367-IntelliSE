"""Deterministic validation and normalization for provisional C1/C2 inputs."""

from collections import Counter

from fastapi import status

from intelise_c3.contracts.provisional_input import (
    C1ApprovalStatus,
    C2ReleaseStatus,
    C2ValidationState,
    ProvisionalInputPackage,
)
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation_context import (
    GenerationContext,
    NormalizedRequirement,
    NormalizedRequirementUmlAnchor,
    NormalizedUiArtifact,
    NormalizedUmlElement,
    SourceContractVersions,
    UpstreamProvenance,
)

SUPPORTED_INPUT_CONTRACT_VERSION = "1.0"


class InputValidationService:
    """Apply FR-C3-01 rules without using an LLM or mutating input data."""

    def validate(self, package: ProvisionalInputPackage) -> GenerationContext:
        """Reject invalid upstream input or create an immutable domain context."""
        errors: list[ErrorDetail] = []

        versions = (
            ("contract_version", package.contract_version),
            ("c1.contract_version", package.c1.contract_version),
            ("c2.contract_version", package.c2.contract_version),
        )
        for field, value in versions:
            if value != SUPPORTED_INPUT_CONTRACT_VERSION:
                errors.append(
                    ErrorDetail(
                        code="UNSUPPORTED_CONTRACT_VERSION",
                        field=field,
                        message=(
                            f"Contract version '{value}' is unsupported; "
                            f"expected '{SUPPORTED_INPUT_CONTRACT_VERSION}'."
                        ),
                    )
                )

        if len({value for _, value in versions}) != 1:
            errors.append(
                ErrorDetail(
                    code="CONTRACT_VERSION_MISMATCH",
                    field="c2.contract_version",
                    message="Envelope, C1, and C2 contract versions must match.",
                )
            )

        if package.c1.project_id != package.c2.project_id:
            errors.append(
                ErrorDetail(
                    code="PROJECT_ID_MISMATCH",
                    field="c2.project_id",
                    message="C2 project_id must match the C1 project_id.",
                )
            )

        if package.c1.srs_version != package.c2.source_srs_version:
            errors.append(
                ErrorDetail(
                    code="SRS_VERSION_MISMATCH",
                    field="c2.source_srs_version",
                    message="C2 source_srs_version must match the C1 srs_version.",
                )
            )

        if package.c1.approval_status is not C1ApprovalStatus.APPROVED:
            errors.append(
                ErrorDetail(
                    code="C1_PACKAGE_NOT_APPROVED",
                    field="c1.approval_status",
                    message="The C1 SRS package must have APPROVED status.",
                )
            )

        for index, requirement in enumerate(package.c1.requirements):
            if requirement.status is not C1ApprovalStatus.APPROVED:
                errors.append(
                    ErrorDetail(
                        code="C1_REQUIREMENT_NOT_APPROVED",
                        field=f"c1.requirements.{index}.status",
                        message=(
                            f"Requirement '{requirement.requirement_id}' must have "
                            "APPROVED status."
                        ),
                    )
                )

        self._require_reference(
            errors,
            package.c1.approval_provenance_ref,
            field="c1.approval_provenance_ref",
            code="MISSING_APPROVAL_PROVENANCE",
            label="C1 approval provenance reference",
        )
        self._require_reference(
            errors,
            package.c1.validation_report_ref,
            field="c1.validation_report_ref",
            code="MISSING_VALIDATION_REPORT",
            label="C1 validation report reference",
        )
        self._require_reference(
            errors,
            package.c2.validation_report_ref,
            field="c2.validation_report_ref",
            code="MISSING_VALIDATION_REPORT",
            label="C2 validation report reference",
        )

        requirement_ids = [
            requirement.requirement_id for requirement in package.c1.requirements
        ]
        self._reject_duplicates(
            errors,
            requirement_ids,
            field_prefix="c1.requirements",
            field_name="requirement_id",
            code="DUPLICATE_REQUIREMENT_ID",
            label="requirement ID",
        )

        if package.c2.validation_state is not C2ValidationState.PASSED:
            errors.append(
                ErrorDetail(
                    code="C2_VALIDATION_NOT_PASSED",
                    field="c2.validation_state",
                    message=(
                        "C2 validation_state must be PASSED; "
                        f"received {package.c2.validation_state.value}."
                    ),
                )
            )

        if package.c2.release_status is not C2ReleaseStatus.VALIDATED:
            errors.append(
                ErrorDetail(
                    code="C2_RELEASE_NOT_VALIDATED",
                    field="c2.release_status",
                    message="C2 release_status must be VALIDATED.",
                )
            )

        uml_ids = [element.uml_id for element in package.c2.uml_elements]
        self._reject_duplicates(
            errors,
            uml_ids,
            field_prefix="c2.uml_elements",
            field_name="uml_id",
            code="DUPLICATE_UML_ID",
            label="UML ID",
        )

        anchor_ids = [
            anchor.anchor_id for anchor in package.c2.requirement_uml_anchors
        ]
        self._reject_duplicates(
            errors,
            anchor_ids,
            field_prefix="c2.requirement_uml_anchors",
            field_name="anchor_id",
            code="DUPLICATE_ANCHOR_ID",
            label="anchor ID",
        )

        known_requirement_ids = set(requirement_ids)
        known_uml_ids = set(uml_ids)
        for index, anchor in enumerate(package.c2.requirement_uml_anchors):
            if anchor.requirement_id not in known_requirement_ids:
                errors.append(
                    ErrorDetail(
                        code="UNKNOWN_REQUIREMENT_REFERENCE",
                        field=(
                            f"c2.requirement_uml_anchors.{index}.requirement_id"
                        ),
                        message=(
                            f"Anchor '{anchor.anchor_id}' references unknown "
                            f"requirement '{anchor.requirement_id}'."
                        ),
                    )
                )
            if anchor.uml_id not in known_uml_ids:
                errors.append(
                    ErrorDetail(
                        code="UNKNOWN_UML_REFERENCE",
                        field=f"c2.requirement_uml_anchors.{index}.uml_id",
                        message=(
                            f"Anchor '{anchor.anchor_id}' references unknown UML "
                            f"element '{anchor.uml_id}'."
                        ),
                    )
                )

        if errors:
            raise ApplicationError(
                errors,
                status_code=status.HTTP_409_CONFLICT,
            )

        return self._normalize(package)

    @staticmethod
    def _require_reference(
        errors: list[ErrorDetail],
        value: str,
        *,
        field: str,
        code: str,
        label: str,
    ) -> None:
        if not value.strip():
            errors.append(
                ErrorDetail(
                    code=code,
                    field=field,
                    message=f"{label} is required.",
                )
            )

    @staticmethod
    def _reject_duplicates(
        errors: list[ErrorDetail],
        values: list[str],
        *,
        field_prefix: str,
        field_name: str,
        code: str,
        label: str,
    ) -> None:
        duplicate_values = {value for value, count in Counter(values).items() if count > 1}
        for index, value in enumerate(values):
            if value in duplicate_values and values.index(value) != index:
                errors.append(
                    ErrorDetail(
                        code=code,
                        field=f"{field_prefix}.{index}.{field_name}",
                        message=f"Duplicate {label} '{value}'.",
                    )
                )

    @staticmethod
    def _normalize(package: ProvisionalInputPackage) -> GenerationContext:
        return GenerationContext(
            project_id=package.c1.project_id,
            srs_version=package.c1.srs_version,
            uml_version=package.c2.uml_version,
            source_contract_versions=SourceContractVersions(
                envelope=package.contract_version,
                c1=package.c1.contract_version,
                c2=package.c2.contract_version,
            ),
            upstream_provenance=UpstreamProvenance(
                c1_approval_provenance_ref=package.c1.approval_provenance_ref,
                c1_validation_report_ref=package.c1.validation_report_ref,
                c2_validation_report_ref=package.c2.validation_report_ref,
            ),
            requirements=tuple(
                NormalizedRequirement(
                    requirement_id=requirement.requirement_id,
                    title=requirement.title,
                    approval_status="APPROVED",
                )
                for requirement in package.c1.requirements
            ),
            uml_elements=tuple(
                NormalizedUmlElement(
                    uml_id=element.uml_id,
                    element_type=element.element_type,
                    name=element.name,
                )
                for element in package.c2.uml_elements
            ),
            ui_artifacts=tuple(
                NormalizedUiArtifact(
                    ui_id=artifact.ui_id,
                    artifact_type=artifact.artifact_type,
                    source_ref=artifact.source_ref,
                )
                for artifact in package.c2.ui_artifacts
            ),
            requirement_uml_anchors=tuple(
                NormalizedRequirementUmlAnchor(
                    anchor_id=anchor.anchor_id,
                    requirement_id=anchor.requirement_id,
                    uml_id=anchor.uml_id,
                )
                for anchor in package.c2.requirement_uml_anchors
            ),
        )
