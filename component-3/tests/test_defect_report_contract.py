"""Contract tests: closed source classification, required explanation and location."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from intelise_c3.contracts.defect_report import (
    DefectItem,
    DefectReport,
    DefectSourceClassification,
)

SCENARIOS = json.loads(
    (
        Path(__file__).parent
        / "fixtures"
        / "simulated"
        / "scoped_regeneration"
        / "c4_defect_scenarios.json"
    ).read_text(encoding="utf-8")
)


def _report_payload(classification: str = "SIMULATED_C4_FIXTURE") -> dict:
    return {
        "source_classification": classification,
        "defect_report_id": "RPT-1",
        "reported_at_utc": "2026-10-20T00:00:00+00:00",
        "source_generation_run_id": "RUN-1",
        "source_artifact_digest_sha256": "a" * 64,
        "source_graph_version": 1,
        "defects": copy.deepcopy(SCENARIOS["scenarios"][0]["defects"]),
    }


@pytest.mark.parametrize("label", ["SIMULATED_C4_FIXTURE", "C4_AGENT_OUTPUT"])
def test_both_closed_classifications_are_accepted(label: str) -> None:
    report = DefectReport.model_validate(_report_payload(label))

    assert report.source_classification is DefectSourceClassification(label)
    assert report.model_dump(mode="json")["source_classification"] == label


@pytest.mark.parametrize(
    "label", ["REAL_C4", "c4_agent_output", "", "SIMULATED", None, 7]
)
def test_other_classifications_are_rejected(label) -> None:
    with pytest.raises(ValidationError):
        DefectReport.model_validate(_report_payload(label))


def test_enum_is_exactly_the_two_documented_values() -> None:
    assert {item.value for item in DefectSourceClassification} == {
        "SIMULATED_C4_FIXTURE",
        "C4_AGENT_OUTPUT",
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda defect: defect.pop("explanation"),
        lambda defect: defect.update(explanation=None),
        lambda defect: defect.update(explanation=""),
        lambda defect: defect.update(explanation="   \n"),
        lambda defect: defect.update(explanation="x" * 1201),
        lambda defect: defect.pop("location"),
        lambda defect: defect.update(location=None),
        lambda defect: defect.update(location={"symbol": "update"}),
        lambda defect: defect.update(location={"relative_path": None}),
        lambda defect: defect.update(location={"relative_path": "../secret.js"}),
        lambda defect: defect.pop("evidence"),
    ],
    ids=[
        "explanation-missing",
        "explanation-null",
        "explanation-empty",
        "explanation-blank",
        "explanation-too-long",
        "location-missing",
        "location-null",
        "location-path-missing",
        "location-path-null",
        "location-path-unsafe",
        "evidence-missing",
    ],
)
def test_explanation_location_and_evidence_are_required(mutate) -> None:
    defect = copy.deepcopy(SCENARIOS["scenarios"][0]["defects"][0])
    DefectItem.model_validate(defect)  # the unmutated fixture defect is valid
    mutate(defect)

    with pytest.raises(ValidationError):
        DefectItem.model_validate(defect)


def test_location_symbol_stays_optional() -> None:
    defect = copy.deepcopy(SCENARIOS["scenarios"][0]["defects"][0])
    defect["location"] = {"relative_path": defect["location"]["relative_path"]}

    assert DefectItem.model_validate(defect).location.symbol is None


def test_every_simulated_scenario_defect_satisfies_the_required_fields() -> None:
    for scenario in SCENARIOS["scenarios"]:
        for defect in scenario["defects"]:
            item = DefectItem.model_validate(defect)
            assert item.explanation.strip()
            assert item.location.relative_path
