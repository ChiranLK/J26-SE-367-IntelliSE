"""Tests for the C1 report importer and C2 release builder CLI scripts."""

from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.generation_context import GenerationContext
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService

COMPONENT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = COMPONENT_ROOT / "scripts"
FIXTURES = Path(__file__).parent / "fixtures" / "simulated"
C1_REPORT = FIXTURES / "c1" / "create_a_calculator.txt"
C2_PUML = FIXTURES / "c2" / "web_CLASS_final.puml"

PROJECT_ID = "6ad62f5a8b7456adf93a30ea"
SRS_VERSION = "SRS-CALC-1"
UML_VERSION = "UML-CALC-1"

# Requirement IDs exactly as written in the real C1 export (R01..R08).
REAL_IDS = (
    "88c3ca5f-bc98-4d0f-b74c-f005e82326b7",
    "0247538c-81d7-4703-a5bc-5fe2201bc5e7",
    "6d0d8610-8d7c-4a11-8f52-2f4ef0f8a64a",
    "7a69f30e-58f2-4b6c-a15b-ec2e1f78ab6a",
    "aaa6437d-4988-4c8f-8ce6-21b632ef228b",
    "866a1f50-561d-42e9-bc2c-f1a8ad040236",
    "891fb249-e92e-4977-af3f-5b102a907d08",
    "45c56e78-aa63-4dba-b9be-a4911edbb561",
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


import_c1 = _load("import_c1_report")
build_c2 = _load("build_c2_release")


def _run(module, argv: list[str]) -> int:
    """Return the exit code, treating argparse's SystemExit as a return value."""
    try:
        return module.main(argv)
    except SystemExit as exit_:
        return int(exit_.code)


def _import_args(output: Path, *extra: str) -> list[str]:
    return [
        str(C1_REPORT),
        "--project-id", PROJECT_ID,
        "--srs-version", SRS_VERSION,
        "--output", str(output),
        *extra,
    ]


APPROVE_FLAGS = (
    "--approve",
    "--approval-ref", "SIM-APPROVAL-REF-1",
    "--approved-by", "Test Reviewer",
    "--validation-report-ref", "SIM-C1-VALIDATION-1",
)


@pytest.fixture
def anchors_file(tmp_path: Path) -> Path:
    """Hand-written anchors for R01-R05 only."""
    path = tmp_path / "anchors.json"
    path.write_text(
        json.dumps(
            {
                REAL_IDS[0]: ["Addition"],
                REAL_IDS[1]: ["Subtraction"],
                REAL_IDS[2]: ["Multiplication"],
                REAL_IDS[3]: ["Division"],
                REAL_IDS[4]: ["Calculator", "CalculationStatus"],
            }
        ),
        encoding="utf-8",
    )
    return path


def _c2_args(output: Path, anchors: Path, *extra: str) -> list[str]:
    return [
        "--puml", str(C2_PUML),
        "--anchors", str(anchors),
        "--uml-version", UML_VERSION,
        "--srs-version", SRS_VERSION,
        "--project-id", PROJECT_ID,
        "--release-status", "VALIDATED",
        "--validation-state", "PASSED",
        "--validation-report-ref", "SIM-C2-VALIDATION-1",
        "--ui-artifact", "SIM-UI-REF-1",
        "--output", str(output),
        *extra,
    ]


def _package(c1_path: Path, c2_path: Path) -> ProvisionalInputPackage:
    return ProvisionalInputPackage.model_validate(
        {
            "contract_version": "1.0",
            "c1": json.loads(c1_path.read_text(encoding="utf-8")),
            "c2": json.loads(c2_path.read_text(encoding="utf-8")),
        }
    )


def test_parser_extracts_ids_text_and_category_verbatim() -> None:
    parsed = import_c1.parse_report(C1_REPORT.read_text(encoding="utf-8"))

    assert [item.requirement_id for item in parsed] == list(REAL_IDS)
    assert [item.label for item in parsed] == [f"R0{n}" for n in range(1, 9)]
    assert [item.category for item in parsed] == ["FR"] * 5 + ["NFR"] * 3
    assert parsed[0].text == "User shall be able to add two numbers."
    assert parsed[7].text == "The calculator shall support 100 concurrent users."
    assert {item.review_state for item in parsed} == {"Unreviewed model prediction"}


def test_default_import_is_draft_and_rejected_by_validation(tmp_path: Path) -> None:
    c1_path, c2_path, anchors = tmp_path / "c1.json", tmp_path / "c2.json", tmp_path / "a.json"
    anchors.write_text(json.dumps({REAL_IDS[0]: ["Addition"]}), encoding="utf-8")
    assert _run(import_c1, _import_args(c1_path)) == 0
    assert _run(build_c2, _c2_args(c2_path, anchors)) == 0

    document = json.loads(c1_path.read_text(encoding="utf-8"))
    assert document["approval_status"] == "DRAFT"
    assert {item["status"] for item in document["requirements"]} == {"DRAFT"}
    assert document["approval_provenance_ref"] == "NOT_PROVIDED"

    with pytest.raises(ApplicationError) as captured:
        InputValidationService().validate(_package(c1_path, c2_path))

    codes = Counter(detail.code for detail in captured.value.errors)
    assert codes["C1_REQUIREMENT_NOT_APPROVED"] == 8
    assert codes["C1_PACKAGE_NOT_APPROVED"] == 1
    assert captured.value.status_code == 409


def test_approved_pair_passes_validation_and_builds_generation_context(
    tmp_path: Path, anchors_file: Path
) -> None:
    c1_path, c2_path = tmp_path / "c1.json", tmp_path / "c2.json"
    assert _run(import_c1, _import_args(c1_path, *APPROVE_FLAGS)) == 0
    assert _run(build_c2, _c2_args(c2_path, anchors_file)) == 0

    context = InputValidationService().validate(_package(c1_path, c2_path))

    assert isinstance(context, GenerationContext)
    assert [item.requirement_id for item in context.requirements] == list(REAL_IDS)
    assert context.upstream_provenance.c1_approval_provenance_ref == "SIM-APPROVAL-REF-1"
    assert context.upstream_provenance.c1_validation_report_ref == "SIM-C1-VALIDATION-1"
    # One diagram element + 8 classes + 1 enum, with deterministic IDs.
    ids = [item.uml_id for item in context.uml_elements]
    assert ids[0] == "UML-DIAGRAM-CLASS"
    assert len(ids) == 10
    assert "UML-CLASS-Operation" in ids and "UML-ENUM-CalculationStatus" in ids
    assert {(a.requirement_id, a.uml_id) for a in context.requirement_uml_anchors} == {
        (REAL_IDS[0], "UML-CLASS-Addition"),
        (REAL_IDS[1], "UML-CLASS-Subtraction"),
        (REAL_IDS[2], "UML-CLASS-Multiplication"),
        (REAL_IDS[3], "UML-CLASS-Division"),
        (REAL_IDS[4], "UML-CLASS-Calculator"),
        (REAL_IDS[4], "UML-ENUM-CalculationStatus"),
    }
    # The diagram source is carried verbatim (CRLF preserved) and still parses.
    diagram = context.uml_elements[0].plantuml_source
    assert diagram == C2_PUML.read_bytes().decode("utf-8")
    design = DesignUnderstandingService().build(context)
    assert len(design.classes) == 9


@pytest.mark.parametrize(
    "missing", ["--approval-ref", "--approved-by", "--validation-report-ref"]
)
def test_approve_without_all_three_flags_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    flags = list(APPROVE_FLAGS)
    index = flags.index(missing)
    del flags[index : index + 2]
    output = tmp_path / "c1.json"

    assert _run(import_c1, _import_args(output, *flags)) != 0
    assert missing in capsys.readouterr().err
    assert not output.exists()


def test_approve_without_any_flags_fails(tmp_path: Path) -> None:
    output = tmp_path / "c1.json"

    assert _run(import_c1, _import_args(output, "--approve")) != 0
    assert not output.exists()


def test_approval_flags_without_approve_fail(tmp_path: Path) -> None:
    output = tmp_path / "c1.json"

    assert _run(import_c1, _import_args(output, "--approval-ref", "X")) != 0
    assert not output.exists()


def test_project_and_srs_version_are_required(tmp_path: Path) -> None:
    assert _run(import_c1, [str(C1_REPORT)]) != 0


def test_malformed_report_is_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "bad.txt"
    report.write_text(
        "REQUIREMENTS\n\nR01 | FR (Functional) | Unreviewed model prediction\n"
        "Some text.\nOriginal model prediction: FR\n",
        encoding="utf-8",
    )
    output = tmp_path / "c1.json"

    code = _run(
        import_c1,
        [str(report), "--project-id", PROJECT_ID, "--srs-version", SRS_VERSION,
         "--output", str(output)],
    )

    assert code == 1
    assert "R01" in capsys.readouterr().err
    assert not output.exists()


def test_unknown_anchor_class_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    anchors = tmp_path / "anchors.json"
    anchors.write_text(json.dumps({REAL_IDS[0]: ["Addition", "Exponent"]}), encoding="utf-8")
    output = tmp_path / "c2.json"

    assert _run(build_c2, _c2_args(output, anchors)) == 1
    assert "Exponent" in capsys.readouterr().err
    assert not output.exists()


def test_missing_ui_artifact_fails(tmp_path: Path, anchors_file: Path) -> None:
    args = _c2_args(tmp_path / "c2.json", anchors_file)
    index = args.index("--ui-artifact")
    del args[index : index + 2]

    assert _run(build_c2, args) != 0


def test_unparseable_puml_fails_with_parser_code(
    tmp_path: Path, anchors_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    puml = tmp_path / "bad.puml"
    puml.write_text("@startuml\ninterface Thing\n@enduml\n", encoding="utf-8")
    args = _c2_args(tmp_path / "c2.json", anchors_file)
    args[args.index("--puml") + 1] = str(puml)

    assert _run(build_c2, args) == 1
    assert "UNSUPPORTED_PLANTUML_CONSTRUCT" in capsys.readouterr().err


def test_anchor_file_with_empty_class_list_fails(tmp_path: Path) -> None:
    anchors = tmp_path / "anchors.json"
    anchors.write_text(json.dumps({REAL_IDS[0]: []}), encoding="utf-8")

    assert _run(build_c2, _c2_args(tmp_path / "c2.json", anchors)) == 1


def test_scripts_run_as_real_commands(tmp_path: Path) -> None:
    output = tmp_path / "c1.json"
    completed = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "import_c1_report.py"), *_import_args(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["approval_status"] == "DRAFT"
