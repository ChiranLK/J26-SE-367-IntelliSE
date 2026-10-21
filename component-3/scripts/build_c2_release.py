"""Build a C2DesignRelease JSON from a raw PlantUML class diagram.

The diagram is parsed with Component 3's design understanding (so abstract
classes and enums are supported) only to enumerate its classes/enums and to fail
early on unsupported syntax. Requirement-to-UML anchors come exclusively from the
caller's anchors.json; nothing is inferred.

Usage:
    python scripts/build_c2_release.py --puml diagram.puml --anchors anchors.json \\
        --uml-version V --srs-version V --project-id ID --release-status VALIDATED \\
        --validation-state PASSED --validation-report-ref REF --ui-artifact REF \\
        [--output c2.json]

anchors.json: {"<requirement_id>": ["ClassOrEnumName", ...], ...}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from intelise_c3.contracts.provisional_input import (
    C2DesignRelease,
    C2ReleaseStatus,
    C2UiArtifact,
    C2UmlElement,
    C2ValidationState,
    RequirementUmlAnchor,
)
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.design_context import ParsedElementKind
from intelise_c3.domain.generation_context import (
    GenerationContext,
    NormalizedUmlElement,
    SourceContractVersions,
    UpstreamProvenance,
)
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import SUPPORTED_INPUT_CONTRACT_VERSION

DIAGRAM_UML_ID = "UML-DIAGRAM-CLASS"
# Per-class elements must not use the CLASS/CLASS_DIAGRAM types: the design
# parser would then demand PlantUML source for each of them.
CLASS_ELEMENT_TYPE = "CLASS_ELEMENT"
ENUM_ELEMENT_TYPE = "ENUM_ELEMENT"


class ReleaseBuildError(ValueError):
    """The inputs cannot produce a faithful C2 release."""


def element_id(name: str, kind: ParsedElementKind) -> str:
    prefix = "UML-ENUM" if kind is ParsedElementKind.ENUM else "UML-CLASS"
    return f"{prefix}-{name}"


def parse_diagram(source: str, *, project_id: str, srs_version: str, uml_version: str):
    """Run the real design parser on the diagram and return its classes/enums."""
    placeholder = "N/A"
    context = GenerationContext(
        project_id=project_id,
        srs_version=srs_version,
        uml_version=uml_version,
        source_contract_versions=SourceContractVersions(
            envelope=SUPPORTED_INPUT_CONTRACT_VERSION,
            c1=SUPPORTED_INPUT_CONTRACT_VERSION,
            c2=SUPPORTED_INPUT_CONTRACT_VERSION,
        ),
        upstream_provenance=UpstreamProvenance(
            c1_approval_provenance_ref=placeholder,
            c1_validation_report_ref=placeholder,
            c2_validation_report_ref=placeholder,
        ),
        requirements=(),
        uml_elements=(
            NormalizedUmlElement(
                uml_id=DIAGRAM_UML_ID,
                element_type="CLASS_DIAGRAM",
                name="Class diagram",
                plantuml_source=source,
            ),
        ),
        ui_artifacts=(),
        requirement_uml_anchors=(),
    )
    try:
        return DesignUnderstandingService().build(context).classes
    except ApplicationError as error:
        detail = error.errors[0]
        raise ReleaseBuildError(
            f"PlantUML parse failed: {detail.code} at {detail.field}: {detail.message}"
        ) from error


def load_anchor_map(path: Path) -> dict[str, tuple[str, ...]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseBuildError(f"Cannot read anchors file '{path}': {error}") from error
    if not isinstance(raw, dict) or not raw:
        raise ReleaseBuildError("anchors.json must be a non-empty object {requirement_id: [names]}.")
    result: dict[str, tuple[str, ...]] = {}
    for requirement_id, names in raw.items():
        if (
            not isinstance(names, list)
            or not names
            or not all(isinstance(name, str) and name for name in names)
        ):
            raise ReleaseBuildError(
                f"Anchors for '{requirement_id}' must be a non-empty list of class/enum names."
            )
        if len(set(names)) != len(names):
            raise ReleaseBuildError(f"Anchors for '{requirement_id}' repeat a name.")
        result[requirement_id] = tuple(names)
    return result


def build_release(
    *,
    source: str,
    anchor_map: dict[str, tuple[str, ...]],
    project_id: str,
    srs_version: str,
    uml_version: str,
    release_status: C2ReleaseStatus,
    validation_state: C2ValidationState,
    validation_report_ref: str,
    ui_artifacts: list[str],
    ui_artifact_type: str,
) -> C2DesignRelease:
    if not ui_artifacts:
        raise ReleaseBuildError("At least one --ui-artifact is required.")
    parsed = parse_diagram(
        source, project_id=project_id, srs_version=srs_version, uml_version=uml_version
    )
    by_name = {item.name: item for item in parsed}

    elements = [
        C2UmlElement(
            uml_id=DIAGRAM_UML_ID,
            element_type="CLASS_DIAGRAM",
            name="Class diagram",
            plantuml_source=source,
        )
    ]
    for item in parsed:
        is_enum = item.kind is ParsedElementKind.ENUM
        elements.append(
            C2UmlElement(
                uml_id=element_id(item.name, item.kind),
                element_type=ENUM_ELEMENT_TYPE if is_enum else CLASS_ELEMENT_TYPE,
                name=item.name,
            )
        )

    anchors: list[RequirementUmlAnchor] = []
    for requirement_id, names in anchor_map.items():
        for name in names:
            target = by_name.get(name)
            if target is None:
                raise ReleaseBuildError(
                    f"Anchor for requirement '{requirement_id}' names unknown "
                    f"class/enum '{name}'. Known: {', '.join(sorted(by_name))}."
                )
            uml_id = element_id(target.name, target.kind)
            anchors.append(
                RequirementUmlAnchor(
                    anchor_id=f"ANCHOR-{requirement_id}-{target.name}",
                    requirement_id=requirement_id,
                    uml_id=uml_id,
                )
            )

    return C2DesignRelease(
        contract_version=SUPPORTED_INPUT_CONTRACT_VERSION,
        project_id=project_id,
        source_srs_version=srs_version,
        uml_version=uml_version,
        release_status=release_status,
        validation_state=validation_state,
        validation_report_ref=validation_report_ref,
        uml_elements=tuple(elements),
        ui_artifacts=tuple(
            C2UiArtifact(ui_id=f"UI-{index}", artifact_type=ui_artifact_type, source_ref=ref)
            for index, ref in enumerate(ui_artifacts, start=1)
        ),
        requirement_uml_anchors=tuple(anchors),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--puml", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--uml-version", required=True)
    parser.add_argument("--srs-version", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--release-status", required=True, choices=[s.value for s in C2ReleaseStatus])
    parser.add_argument(
        "--validation-state", required=True, choices=[s.value for s in C2ValidationState]
    )
    parser.add_argument("--validation-report-ref", required=True)
    parser.add_argument(
        "--ui-artifact", required=True, action="append", metavar="REF",
        help="UI/wireframe reference; repeatable, at least one",
    )
    parser.add_argument("--ui-artifact-type", default="UI_REFERENCE")
    parser.add_argument("--output", type=Path, help="Write JSON here (default: stdout)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        source = args.puml.read_bytes().decode("utf-8-sig")
        release = build_release(
            source=source,
            anchor_map=load_anchor_map(args.anchors),
            project_id=args.project_id,
            srs_version=args.srs_version,
            uml_version=args.uml_version,
            release_status=C2ReleaseStatus(args.release_status),
            validation_state=C2ValidationState(args.validation_state),
            validation_report_ref=args.validation_report_ref,
            ui_artifacts=args.ui_artifact,
            ui_artifact_type=args.ui_artifact_type,
        )
    except (OSError, ReleaseBuildError, ValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    payload = json.dumps(release.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(payload)
    print(
        f"built release with {len(release.uml_elements)} UML elements and "
        f"{len(release.requirement_uml_anchors)} anchors",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
