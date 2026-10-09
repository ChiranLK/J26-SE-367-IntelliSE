"""FR-C3-01 tests using explicitly simulated provisional C1/C2 payloads."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.services.input_validation import InputValidationService

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "simulated"


def _load_json(name: str) -> Any:
    return json.loads((FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))


def _resolve_parent(document: Any, path: list[str | int]) -> tuple[Any, str | int]:
    current = document
    for part in path[:-1]:
        current = current[part]
    return current, path[-1]


def _apply_mutations(
    base_payload: dict[str, Any], mutations: list[dict[str, Any]]
) -> dict[str, Any]:
    payload = copy.deepcopy(base_payload)
    for mutation in mutations:
        path = mutation["path"]
        parent, key = _resolve_parent(payload, path)
        operation = mutation["operation"]
        if operation == "set":
            parent[key] = mutation["value"]
        elif operation == "remove":
            del parent[key]
        elif operation == "append":
            parent[key].append(mutation["value"])
        else:
            raise AssertionError(f"Unknown fixture mutation operation: {operation}")
    return payload


INVALID_SCENARIOS = _load_json("invalid_input_scenarios.json")["scenarios"]


def test_valid_package_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/validate-input",
        json=_load_json("valid_input_package.json"),
    )

    assert response.status_code == 200
    assert response.json()["context_version"] == "1.0"


@pytest.mark.parametrize(
    "scenario",
    INVALID_SCENARIOS,
    ids=[scenario["name"] for scenario in INVALID_SCENARIOS],
)
def test_invalid_packages_are_rejected(
    client: TestClient, scenario: dict[str, Any]
) -> None:
    payload = _apply_mutations(
        _load_json("valid_input_package.json"), scenario["mutations"]
    )

    response = client.post("/api/v1/validate-input", json=payload)

    assert response.status_code == scenario["expected_status"]
    errors = response.json()["errors"]
    assert any(
        error["code"] == scenario["expected_code"]
        and error["field"] == scenario["expected_field"]
        for error in errors
    )


def test_malformed_json_is_rejected_with_422(client: TestClient) -> None:
    malformed_body = (FIXTURE_DIRECTORY / "malformed_input.json").read_text(
        encoding="utf-8"
    )

    response = client.post(
        "/api/v1/validate-input",
        content=malformed_body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "MALFORMED_INPUT"


def test_validation_does_not_mutate_input_and_models_are_frozen() -> None:
    package = ProvisionalInputPackage.model_validate(
        _load_json("valid_input_package.json")
    )
    before = package.model_dump(mode="json")

    InputValidationService().validate(package)

    assert package.model_dump(mode="json") == before
    with pytest.raises(ValidationError):
        package.contract_version = "changed"  # type: ignore[misc]


def test_generation_context_preserves_ids_anchors_and_versions(
    client: TestClient,
) -> None:
    source = _load_json("valid_input_package.json")

    response = client.post("/api/v1/validate-input", json=source)

    assert response.status_code == 200
    context = response.json()
    assert [item["requirement_id"] for item in context["requirements"]] == [
        item["requirement_id"] for item in source["c1"]["requirements"]
    ]
    assert [item["uml_id"] for item in context["uml_elements"]] == [
        item["uml_id"] for item in source["c2"]["uml_elements"]
    ]
    assert context["requirement_uml_anchors"] == source["c2"][
        "requirement_uml_anchors"
    ]
    assert context["project_id"] == source["c1"]["project_id"]
    assert context["srs_version"] == source["c1"]["srs_version"]
    assert context["uml_version"] == source["c2"]["uml_version"]
    assert context["source_contract_versions"] == {
        "envelope": source["contract_version"],
        "c1": source["c1"]["contract_version"],
        "c2": source["c2"]["contract_version"],
    }
    assert context["upstream_provenance"] == {
        "c1_approval_provenance_ref": source["c1"][
            "approval_provenance_ref"
        ],
        "c1_validation_report_ref": source["c1"]["validation_report_ref"],
        "c2_validation_report_ref": source["c2"]["validation_report_ref"],
    }


def test_health_endpoint_regression(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "service_name": "intelise-component-3",
        "status": "healthy",
        "api_version": "v1",
    }
