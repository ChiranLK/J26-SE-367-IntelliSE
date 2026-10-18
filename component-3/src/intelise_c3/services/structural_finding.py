"""Shared helper for building structural verification findings."""

from intelise_c3.domain.generation import GeneratedFileRecord, GenerationManifest
from intelise_c3.domain.structural_verification import (
    StructuralFindingCategory,
    StructuralFindingStatus,
    StructuralVerificationFinding,
)


def make_structural_finding(
    manifest: GenerationManifest,
    records: dict[str, GeneratedFileRecord],
    *,
    finding_id: str,
    rule_id: str,
    category: StructuralFindingCategory,
    finding_status: StructuralFindingStatus,
    message: str,
    paths: tuple[str, ...],
    expected: tuple[str, ...],
    observed: tuple[str, ...],
    remediation: str | None,
) -> StructuralVerificationFinding:
    relevant = tuple(records[path] for path in paths if path in records)
    requirement_ids = set(manifest.source.requirement_ids)
    uml_ids = set(manifest.source.uml_ids)
    referenced_requirements = tuple(
        sorted(
            requirement_id
            for record in relevant
            for requirement_id in record.requirement_ids
            if requirement_id in requirement_ids
        )
    )
    referenced_uml = tuple(
        sorted(
            uml_id
            for record in relevant
            for uml_id in record.uml_ids
            if uml_id in uml_ids
        )
    )
    return StructuralVerificationFinding(
        finding_id=finding_id,
        rule_id=rule_id,
        category=category,
        status=finding_status,
        message=message,
        affected_module_ids=tuple(sorted({record.file_id for record in relevant})),
        requirement_ids=tuple(dict.fromkeys(referenced_requirements)),
        uml_ids=tuple(dict.fromkeys(referenced_uml)),
        evidence_paths=tuple(path for path in paths if path in records),
        expected=expected,
        observed=observed,
        remediation=remediation,
    )
