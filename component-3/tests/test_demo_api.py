"""Tests for the helper API behind the C3 research demo dashboard.

The Ollama probe is the only thing replaced by a test double here, and only where a
test needs a deterministic reachable/unreachable answer. Generation, traceability,
verification, and scoped regeneration run through the real services in temporary
directories. No generated JavaScript is executed.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.contracts.stack_selection import StackSelectionCriteria
from intelise_c3.core.config import get_settings
from intelise_c3.main import create_app
from intelise_c3.scripts.generate_task_mvp import build_simulated_request
from intelise_c3.services import demo_support
from intelise_c3.services.docker_preview import DockerPreviewService

PRIMARY_SCENARIO = "SIM-SCN-001-service-update-missing-task"
CONTROLLER_SCENARIO = "SIM-SCN-002-controller-with-location"
SERVICE_PATH = "backend/src/services/taskService.js"


@pytest.fixture
def demo_client(tmp_path: Path) -> Iterator[TestClient]:
    get_settings.cache_clear()
    application = create_app()
    settings = SimpleNamespace(
        service_name="intelise-component-3",
        api_version="v1",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5-coder:3b",
        generated_workspace_root=tmp_path / "workspaces",
        traceability_store_path=tmp_path / "graphs.sqlite3",
    )
    application.state.settings = settings
    application.state.preview_service = DockerPreviewService(settings)
    with TestClient(application) as client:
        yield client
    get_settings.cache_clear()


def tree_hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


# ------------------------------------------------------------------ overview


class _FakeTagsResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_overview_reports_real_probe_result_and_integration_labels(
    demo_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        demo_support.httpx,
        "get",
        lambda url, timeout: _FakeTagsResponse({"models": [{"name": "qwen2.5-coder:3b"}]}),
    )

    body = demo_client.get("/api/v1/demo/overview").json()

    assert body["ollama"]["reachable"] is True
    assert body["ollama"]["model_installed"] is True
    assert body["ollama"]["configured_model"] == "qwen2.5-coder:3b"
    states = {item["component"]: item["state"] for item in body["integrations"]}
    assert states["Component 1 (requirements)"] == "SIMULATED_FIXTURE"
    assert states["Component 2 (UML and UI design)"] == "SIMULATED_FIXTURE"
    assert states["Component 4 (testing, XAI)"] == "NOT_INTEGRATED"
    assert states["Deployment"] == "NOT_IMPLEMENTED"
    assert body["generated_workspace_root_name"] == "workspaces"
    assert str(Path.home()) not in json.dumps(body)  # no absolute local paths are exposed


def test_overview_reports_missing_model_and_unreachable_ollama_honestly(
    demo_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        demo_support.httpx,
        "get",
        lambda url, timeout: _FakeTagsResponse({"models": [{"name": "other:1b"}]}),
    )
    missing = demo_client.get("/api/v1/demo/overview").json()["ollama"]
    assert (missing["reachable"], missing["model_installed"]) == (True, False)

    def refuse(url, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(demo_support.httpx, "get", refuse)
    down = demo_client.get("/api/v1/demo/overview").json()["ollama"]
    assert (down["reachable"], down["model_installed"]) == (False, None)
    assert "ConnectError" in down["detail"]


def test_engine_reload_invalidates_provider_bound_hybrid_services(
    demo_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GENERATION_PROVIDER", "openrouter")
    monkeypatch.setenv("TEAMSOCLO_MODEL", "claude-opus-5-5")
    monkeypatch.setattr(
        demo_support.httpx,
        "get",
        lambda url, timeout: _FakeTagsResponse({"models": []}),
    )
    demo_client.app.state.hybrid_pipeline = object()
    demo_client.app.state.hybrid_preview = object()

    response = demo_client.post("/api/v1/demo/engine-reload")

    assert response.status_code == 200
    assert demo_client.app.state.settings.teamsoclo_model == "claude-opus-5-5"
    assert demo_client.app.state.hybrid_pipeline is None
    assert demo_client.app.state.hybrid_preview is None


# ------------------------------------------------------------------ fixtures


def test_fixtures_are_labeled_simulated_and_match_existing_contracts(
    demo_client: TestClient,
) -> None:
    package = demo_client.get("/api/v1/demo/fixtures/input-package").json()
    assert package["classification"] == "SIMULATED_C1_C2_FIXTURE"
    assert package["review_status"] == "NOT_INDEPENDENTLY_REVIEWED"
    assert "not approved" in package["notice"].lower()
    validated = demo_client.post("/api/v1/validate-input", json=package["payload"])
    assert validated.status_code == 200
    assert validated.json()["project_id"] == "PROJECT-TASK-MVP-001"

    defects = demo_client.get("/api/v1/demo/fixtures/defect-scenarios").json()
    assert defects["classification"] == "SIMULATED_C4_FIXTURE"
    assert len(defects["payload"]["scenarios"]) == 8

    criteria = demo_client.get("/api/v1/demo/fixtures/stack-criteria").json()
    assert criteria["classification"] == "SIMULATED_CRITERIA"
    StackSelectionCriteria.model_validate(criteria["payload"])


def test_unknown_fixture_is_rejected_with_a_structured_error(demo_client: TestClient) -> None:
    response = demo_client.get("/api/v1/demo/fixtures/..%2F..%2Fsecret")
    assert response.status_code == 404

    response = demo_client.get("/api/v1/demo/fixtures/not-a-fixture")
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "UNKNOWN_DEMO_FIXTURE"


# --------------------------------------------------------------- code preview


def _generate_template_run(client: TestClient) -> dict:
    request = build_simulated_request(GenerationMode.TEMPLATE_ONLY)
    response = client.post(
        "/api/v1/generation-runs", json=json.loads(request.model_dump_json())
    )
    assert response.status_code == 201
    return response.json()


def test_code_preview_returns_verified_text_and_never_executes(
    demo_client: TestClient, tmp_path: Path
) -> None:
    run = _generate_template_run(demo_client)
    payload = {
        "manifest": run["manifest"],
        "workspace_relative_path": run["workspace_relative_path"],
        "relative_path": SERVICE_PATH,
    }

    response = demo_client.post("/api/v1/demo/code-preview", json=payload)

    assert response.status_code == 200
    body = response.json()
    on_disk = (tmp_path / "workspaces" / run["workspace_relative_path"] / SERVICE_PATH).read_text(
        encoding="utf-8"
    )
    assert body["content"] == on_disk
    assert body["origin"] == "TEMPLATE"
    assert body["truncated"] is False
    assert body["execution_claim"] == "DISPLAY_ONLY_NOT_EXECUTED"
    assert sha256(on_disk.encode("utf-8")).hexdigest() == body["sha256"]


@pytest.mark.parametrize(
    "bad_path",
    ["../artifact-manifest.json", "/etc/passwd", "backend\\src\\app.js", "backend/../../x"],
)
def test_code_preview_rejects_unsafe_paths(demo_client: TestClient, bad_path: str) -> None:
    run = _generate_template_run(demo_client)

    response = demo_client.post(
        "/api/v1/demo/code-preview",
        json={
            "manifest": run["manifest"],
            "workspace_relative_path": run["workspace_relative_path"],
            "relative_path": bad_path,
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "UNSAFE_PREVIEW_PATH"


def test_code_preview_serves_only_manifest_files(demo_client: TestClient) -> None:
    run = _generate_template_run(demo_client)

    response = demo_client.post(
        "/api/v1/demo/code-preview",
        json={
            "manifest": run["manifest"],
            "workspace_relative_path": run["workspace_relative_path"],
            "relative_path": "artifact-manifest.json",  # exists on disk, not a manifest file
        },
    )

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "PREVIEW_FILE_NOT_IN_MANIFEST"


def test_code_preview_rejects_a_tampered_workspace(
    demo_client: TestClient, tmp_path: Path
) -> None:
    run = _generate_template_run(demo_client)
    target = tmp_path / "workspaces" / run["workspace_relative_path"] / SERVICE_PATH
    target.write_text(target.read_text(encoding="utf-8") + "\n// tampered\n", encoding="utf-8")

    response = demo_client.post(
        "/api/v1/demo/code-preview",
        json={
            "manifest": run["manifest"],
            "workspace_relative_path": run["workspace_relative_path"],
            "relative_path": SERVICE_PATH,
        },
    )

    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "ARTIFACT_HASH_MISMATCH"


def test_code_preview_truncates_large_files(
    demo_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _generate_template_run(demo_client)
    monkeypatch.setattr(demo_support, "MAX_PREVIEW_BYTES", 40)

    response = demo_client.post(
        "/api/v1/demo/code-preview",
        json={
            "manifest": run["manifest"],
            "workspace_relative_path": run["workspace_relative_path"],
            "relative_path": SERVICE_PATH,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is True
    assert len(body["content"].encode("utf-8")) <= 40


# --------------------------------------- baseline, impact, and MOCK regeneration


def _defect_report(baseline: dict, scenario_id: str, *, graph_version: int | None = None) -> dict:
    scenarios = demo_support.load_fixture("defect-scenarios").payload["scenarios"]
    scenario = next(item for item in scenarios if item["scenario_id"] == scenario_id)
    manifest = baseline["generation_run"]["manifest"]
    return {
        "source_classification": "SIMULATED_C4_FIXTURE",
        "defect_report_id": "SIM-C4-REPORT-DEMO-TEST",
        "reported_at_utc": datetime.now(UTC).isoformat(),
        "source_generation_run_id": manifest["generation_run_id"],
        "source_artifact_digest_sha256": manifest["artifact_digest_sha256"],
        "source_graph_version": graph_version or baseline["graph_snapshot"]["graph_version"],
        "defects": scenario["defects"],
    }


def _scoped_request(baseline: dict, report: dict) -> dict:
    return {
        "defect_report": report,
        "manifest": baseline["generation_run"]["manifest"],
        "workspace_relative_path": baseline["generation_run"]["workspace_relative_path"],
        "design_context": baseline["design_context"],
    }


def test_baseline_is_a_real_run_labeled_as_a_simulated_defect(
    demo_client: TestClient, tmp_path: Path
) -> None:
    response = demo_client.post("/api/v1/demo/scoped-regeneration/baseline")

    assert response.status_code == 201
    baseline = response.json()
    assert baseline["classification"] == "SIMULATED_DEFECTIVE_BASELINE"
    assert baseline["model_evidence_class"] == "MOCKED_TEST_DOUBLE"
    assert baseline["injected_defect_module"] == SERVICE_PATH
    manifest = baseline["generation_run"]["manifest"]
    service_record = next(item for item in manifest["files"] if item["relative_path"] == SERVICE_PATH)
    assert service_record["origin"] == "LOCAL_LLM"  # the (mock) model-authored module
    assert baseline["graph_snapshot"]["graph_version"] == 1
    assert baseline["graph_snapshot"]["generation_run_id"] == manifest["generation_run_id"]
    assert manifest["llm_inference"]["configured_model_identifier"] == "SIMULATED-MOCK-MODEL-NOT-OLLAMA"
    assert (tmp_path / "workspaces" / baseline["generation_run"]["workspace_relative_path"]).is_dir()


def test_mock_scoped_regeneration_runs_the_real_pipeline_without_claiming_repair(
    demo_client: TestClient, tmp_path: Path
) -> None:
    baseline = demo_client.post("/api/v1/demo/scoped-regeneration/baseline").json()
    source_dir = tmp_path / "workspaces" / baseline["generation_run"]["workspace_relative_path"]
    source_before = tree_hashes(source_dir)
    request = _scoped_request(baseline, _defect_report(baseline, PRIMARY_SCENARIO))

    impact = demo_client.post("/api/v1/impact-selections", json=request)
    assert impact.status_code == 200
    assert impact.json()["status"] == "SELECTED"
    assert [m["relative_path"] for m in impact.json()["selected_modules"]] == [SERVICE_PATH]

    response = demo_client.post("/api/v1/demo/scoped-regenerations/mock", json=request)

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "PATCHED_PENDING_INDEPENDENT_RETEST"
    assert result["model_evidence_class"] == "MOCKED_TEST_DOUBLE"
    assert result["c4_retest_handoff"]["retest_status"] == "PENDING"
    assert result["c4_testing_claim"] is False
    assert result["metrics"]["repair_success"] == "NOT_EVALUATED_REQUIRES_INDEPENDENT_C4_RETEST"
    assert result["graph_versioning"]["base_graph_version"] == 1
    assert result["graph_versioning"]["new_graph_version"] == 2
    assert result["preservation"]["collateral_edit_count"] == 0
    assert result["artifact_versioning"]["source_artifact_digest_sha256"] != (
        result["artifact_versioning"]["new_artifact_digest_sha256"]
    )
    assert tree_hashes(source_dir) == source_before  # the source run is untouched
    assert (
        demo_client.get(
            f"/api/v1/traceability/graphs/{baseline['graph_snapshot']['graph_id']}"
        ).json()["graph_version"]
        == 2
    )
    v1 = demo_client.get(
        f"/api/v1/traceability/graphs/{baseline['graph_snapshot']['graph_id']}/versions/1"
    ).json()
    assert v1["graph_content_digest_sha256"] == baseline["graph_snapshot"]["graph_content_digest_sha256"]


def test_mock_mode_fails_visibly_when_the_selected_module_is_not_the_mocked_one(
    demo_client: TestClient, tmp_path: Path
) -> None:
    baseline = demo_client.post("/api/v1/demo/scoped-regeneration/baseline").json()
    request = _scoped_request(baseline, _defect_report(baseline, CONTROLLER_SCENARIO))

    response = demo_client.post("/api/v1/demo/scoped-regenerations/mock", json=request)

    assert response.status_code == 200
    result = response.json()
    assert [m["relative_path"] for m in result["impact_selection"]["selected_modules"]] == [
        "backend/src/controllers/taskController.js"
    ]
    assert result["status"] == "FAILED"  # never silently replaced by demo data
    assert result["reason_codes"] == ["PATCH_ATTEMPTS_EXHAUSTED"]
    assert result["artifact_versioning"] is None and result["c4_retest_handoff"] is None
    assert {item["rejection_code"] for item in result["patch_attempts"]} == {
        "PATCH_PATH_NOT_AUTHORIZED"
    }


def test_mock_regeneration_rejects_stale_and_mismatched_reports(demo_client: TestClient) -> None:
    baseline = demo_client.post("/api/v1/demo/scoped-regeneration/baseline").json()

    stale = _scoped_request(baseline, _defect_report(baseline, PRIMARY_SCENARIO, graph_version=9))
    response = demo_client.post("/api/v1/demo/scoped-regenerations/mock", json=stale)

    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "STALE_DEFECT_REPORT"

    missing_version = _scoped_request(baseline, _defect_report(baseline, PRIMARY_SCENARIO))
    missing_version["defect_report"].pop("source_graph_version")
    response = demo_client.post("/api/v1/demo/scoped-regenerations/mock", json=missing_version)
    assert response.status_code == 422


# ------------------------------------------------------------- workspace run


def test_workspace_run_returns_the_verified_stored_manifest(demo_client: TestClient) -> None:
    run = _generate_template_run(demo_client)

    response = demo_client.post(
        "/api/v1/demo/workspace-run",
        json={"workspace_relative_path": run["workspace_relative_path"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["manifest"] == run["manifest"]
    assert body["workspace_relative_path"] == run["workspace_relative_path"]


def test_mock_regenerated_workspace_can_be_previewed_through_the_verified_path(
    demo_client: TestClient,
) -> None:
    baseline = demo_client.post("/api/v1/demo/scoped-regeneration/baseline").json()
    request = _scoped_request(baseline, _defect_report(baseline, PRIMARY_SCENARIO))
    result = demo_client.post("/api/v1/demo/scoped-regenerations/mock", json=request).json()
    new_path = result["artifact_versioning"]["new_workspace_relative_path"]

    new_run = demo_client.post(
        "/api/v1/demo/workspace-run", json={"workspace_relative_path": new_path}
    ).json()
    preview = demo_client.post(
        "/api/v1/demo/code-preview",
        json={
            "manifest": new_run["manifest"],
            "workspace_relative_path": new_run["workspace_relative_path"],
            "relative_path": SERVICE_PATH,
        },
    )

    assert preview.status_code == 200
    assert (
        new_run["manifest"]["artifact_digest_sha256"]
        == result["artifact_versioning"]["new_artifact_digest_sha256"]
    )
    old_preview = demo_client.post(
        "/api/v1/demo/code-preview",
        json={
            "manifest": baseline["generation_run"]["manifest"],
            "workspace_relative_path": baseline["generation_run"]["workspace_relative_path"],
            "relative_path": SERVICE_PATH,
        },
    )
    assert old_preview.status_code == 200
    assert preview.json()["content"] != old_preview.json()["content"]


@pytest.mark.parametrize("bad_path", ["../outside", "/abs/path", "a\\b", "C:/windows"])
def test_workspace_run_rejects_unsafe_paths(demo_client: TestClient, bad_path: str) -> None:
    response = demo_client.post(
        "/api/v1/demo/workspace-run", json={"workspace_relative_path": bad_path}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "UNSAFE_WORKSPACE_PATH"


def test_workspace_run_reports_unknown_workspaces(demo_client: TestClient) -> None:
    response = demo_client.post(
        "/api/v1/demo/workspace-run", json={"workspace_relative_path": "nope/missing"}
    )

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "GENERATION_WORKSPACE_NOT_FOUND"
