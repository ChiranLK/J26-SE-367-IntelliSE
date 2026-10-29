"""Tests for Docker preview helper routes (orchestration only; no generated JS on host)."""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from intelise_c3.core.config import get_settings
from intelise_c3.main import create_app
from intelise_c3.services.docker_preview import DockerPreviewService
from tests.test_dynamic_generation import _generate, _request


@pytest.fixture
def preview_client(tmp_path: Path) -> Iterator[TestClient]:
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


def test_crud_domain_catalog_lists_simulated_domains(preview_client: TestClient) -> None:
    body = preview_client.get("/api/v1/demo/crud-domains").json()
    ids = {item["domain_id"] for item in body["domains"]}
    assert ids == {"student_management", "library_management", "inventory_management"}
    assert all(item["classification"] == "SIMULATED_C1_C2_FIXTURE" for item in body["domains"])


def test_student_management_fixture_is_loadable(preview_client: TestClient) -> None:
    body = preview_client.get("/api/v1/demo/fixtures/student_management").json()
    assert body["classification"] == "SIMULATED_C1_C2_FIXTURE"
    assert body["payload"]["c1"]["project_id"].startswith("PROJECT-STUDENT")


def test_preview_build_rejects_task_manifest(preview_client: TestClient, tmp_path: Path) -> None:
    from intelise_c3.scripts.generate_task_mvp import build_simulated_request
    from intelise_c3.contracts.generation import GenerationMode
    from intelise_c3.services.code_generation import CodeGenerationService
    import asyncio

    root = tmp_path / "workspaces"
    preview_client.app.state.settings.generated_workspace_root = root
    preview_client.app.state.preview_service = DockerPreviewService(
        preview_client.app.state.settings
    )
    request = build_simulated_request(GenerationMode.TEMPLATE_ONLY)
    result = asyncio.run(CodeGenerationService(root, None).generate(request))
    response = preview_client.post(
        "/api/v1/demo/preview/build",
        json={
            "manifest": result.manifest.model_dump(mode="json"),
            "workspace_relative_path": result.workspace_relative_path,
        },
    )
    assert response.status_code == 422


def test_preview_build_without_docker_returns_503(
    preview_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("intelise_c3.services.docker_preview.shutil.which", lambda _name: None)
    preview_client.app.state.preview_service = DockerPreviewService(
        preview_client.app.state.settings
    )
    result, _workspace = _generate(tmp_path, "student_management")
    response = preview_client.post(
        "/api/v1/demo/preview/build",
        json={
            "manifest": result.manifest.model_dump(mode="json"),
            "workspace_relative_path": result.workspace_relative_path,
        },
    )
    assert response.status_code == 503
