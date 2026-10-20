"""C4 intake endpoint, design-context persistence, and run lookup tests.

All inputs are explicitly SIMULATED; ``C4_AGENT_OUTPUT`` below is a label used to
exercise the contract, not evidence that a real Component 4 produced the report.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.core.config import get_settings
from intelise_c3.core.errors import ApplicationError
from intelise_c3.scripts.generate_task_mvp import build_simulated_request
from intelise_c3.services.code_generation import CodeGenerationService
from intelise_c3.services.design_context_store import DesignContextStore
from intelise_c3.traceability.store import SQLiteTraceabilityStore

from tests.test_scoped_regeneration import Env, _client_for, repaired_client

ENDPOINT = "/api/v1/c4/defect-reports"
UNSUPPORTED_SCENARIO = "SIM-SCN-006-unsupported-category"


def _context_store(env: Env) -> DesignContextStore:
    # The simulated Env settings place design contexts next to the graph database.
    return DesignContextStore(env.store_path.parent / "design-contexts")


def _body(env: Env, *, scenario: str | None = None, classification="C4_AGENT_OUTPUT") -> dict:
    request = env.request(*([scenario] if scenario else []))
    report = json.loads(request.defect_report.model_dump_json())
    report["source_classification"] = classification
    return {
        "generation_run_id": env.baseline.manifest.generation_run_id,
        "defect_report": report,
    }


@pytest.fixture()
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def _post(env: Env, body: dict, monkeypatch: pytest.MonkeyPatch, client_double=None):
    monkeypatch.setattr(
        "intelise_c3.api.routes.scoped_regeneration.OllamaLLMClient",
        lambda _settings: client_double or repaired_client(),
    )
    try:
        with _client_for(env) as client:
            return client.post(ENDPOINT, json=body)
    finally:
        get_settings.cache_clear()


def test_c4_report_by_run_id_returns_pending_retest_handoff(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _context_store(env).save(env.design_request.design_context)

    response = _post(env, _body(env), monkeypatch)

    assert response.status_code == 200, response.text
    handoff = response.json()
    assert handoff["retest_status"] == "PENDING"
    assert handoff["independent_c4_evidence"] == "NONE"
    assert handoff["source_generation_run_id"] == env.baseline.manifest.generation_run_id
    assert handoff["new_generation_run_id"] != handoff["source_generation_run_id"]
    assert handoff["new_graph_version"] == 2
    assert handoff["changed_modules"] == ["backend/src/services/taskService.js"]
    # The source run is never modified.
    assert env.baseline.manifest.generation_run_id in {
        path.name for path in env.run_container.iterdir()
    }


def test_run_id_in_request_must_match_the_report(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _body(env)
    body["generation_run_id"] = "some-other-run"

    response = _post(env, body, monkeypatch)

    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "DEFECT_REPORT_RUN_MISMATCH"


def test_unknown_run_is_404_without_any_write(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _body(env)
    body["generation_run_id"] = "unknown-run"
    body["defect_report"]["source_generation_run_id"] = "unknown-run"
    before = env.run_directories()

    response = _post(env, body, monkeypatch)

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "GENERATION_RUN_NOT_FOUND"
    assert env.run_directories() == before


def test_missing_persisted_design_context_is_explicit_409(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = env.run_directories()

    response = _post(env, _body(env), monkeypatch)

    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "DESIGN_CONTEXT_NOT_PERSISTED"
    assert env.run_directories() == before


def test_tampered_persisted_design_context_is_rejected(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _context_store(env)
    digest = store.save(env.design_request.design_context)
    path = env.store_path.parent / "design-contexts" / f"{digest}.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["project_id"] = "PROJECT-TAMPERED"
    path.write_text(json.dumps(stored), encoding="utf-8")

    response = _post(env, _body(env), monkeypatch)

    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "DESIGN_CONTEXT_DIGEST_MISMATCH"


def test_existing_stale_digest_check_still_applies(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _context_store(env).save(env.design_request.design_context)
    body = _body(env)
    body["defect_report"]["source_artifact_digest_sha256"] = "1" * 64

    response = _post(env, body, monkeypatch)

    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "DEFECT_REPORT_DIGEST_MISMATCH"


def test_review_required_outcome_is_a_409_with_reason_not_a_fake_handoff(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _context_store(env).save(env.design_request.design_context)
    before = env.run_directories()

    response = _post(env, _body(env, scenario=UNSUPPORTED_SCENARIO), monkeypatch)

    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "REGENERATION_REVIEW_REQUIRED"
    assert env.run_directories() == before


@pytest.mark.parametrize(
    "mutate",
    [
        lambda body: body["defect_report"].update(source_classification="REAL_C4"),
        lambda body: body["defect_report"]["defects"][0].pop("explanation"),
        lambda body: body["defect_report"]["defects"][0].pop("location"),
        lambda body: body["defect_report"]["defects"][0]["location"].pop("relative_path"),
        lambda body: body.pop("generation_run_id"),
    ],
    ids=[
        "unknown-classification",
        "missing-explanation",
        "missing-location",
        "missing-location-path",
        "missing-run-id",
    ],
)
def test_malformed_submissions_are_422(
    env: Env, monkeypatch: pytest.MonkeyPatch, mutate
) -> None:
    body = _body(env)
    mutate(body)

    response = _post(env, body, monkeypatch)

    assert response.status_code == 422


# ------------------------------------------------- design context persistence


def test_generation_persists_a_digest_checked_design_context(tmp_path: Path) -> None:
    request = build_simulated_request(GenerationMode.TEMPLATE_ONLY)
    store = DesignContextStore(tmp_path / "design-contexts")

    result = asyncio.run(
        CodeGenerationService(
            tmp_path / "ws", None, design_context_store=store
        ).generate(request)
    )

    loaded = store.load(result.manifest.run_evidence.input_hashes.design_context_sha256)
    assert loaded == request.design_context


def test_store_is_idempotent_and_rejects_unknown_or_invalid_digests(tmp_path: Path) -> None:
    request = build_simulated_request(GenerationMode.TEMPLATE_ONLY)
    store = DesignContextStore(tmp_path / "dc")
    first = store.save(request.design_context)
    assert store.save(request.design_context) == first
    assert len(list((tmp_path / "dc").glob("*.json"))) == 1

    for bad, code in (("0" * 64, "DESIGN_CONTEXT_NOT_PERSISTED"), ("../x", "DESIGN_CONTEXT_DIGEST_MISMATCH")):
        with pytest.raises(ApplicationError) as captured:
            store.load(bad)
        assert captured.value.errors[0].code == code


def test_generation_without_a_store_is_unchanged(tmp_path: Path) -> None:
    request = build_simulated_request(GenerationMode.TEMPLATE_ONLY)

    asyncio.run(CodeGenerationService(tmp_path / "ws", None).generate(request))

    assert not (tmp_path / "design-contexts").exists()


def test_find_by_run_id_returns_newest_snapshot_or_none(env: Env) -> None:
    store = SQLiteTraceabilityStore(env.store_path)

    found = store.find_by_run_id(env.baseline.manifest.generation_run_id)

    assert found is not None
    graph_id, version, manifest = found
    assert (graph_id, version) == (env.v1.graph_id, 1)
    assert manifest.generation_run_id == env.baseline.manifest.generation_run_id
    assert store.find_by_run_id("no-such-run") is None
