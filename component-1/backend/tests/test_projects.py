"""API validation and safe unavailability behavior without a database."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import OperationFailure

from intelise_c1.api.project_schemas import ProjectCreate
from intelise_c1.core.config import Settings
from intelise_c1.core.database import UNAVAILABLE_DETAIL
from intelise_c1.main import create_app

PROJECTS = "/api/v1/component-1/projects"
PAYLOAD = {"name": "Test project", "discussion_text": "Original client discussion."}


@pytest.fixture
def client():
    with TestClient(create_app(Settings(_env_file=None, mongodb_uri=None))) as test_client:
        yield test_client


@pytest.mark.parametrize("field", ["name", "discussion_text"])
@pytest.mark.parametrize("value", ["", " ", "\t\n\u00a0"])
def test_blank_rejection(client, field, value):
    response = client.post(PROJECTS, json={**PAYLOAD, field: value})
    assert response.status_code == 422


@pytest.mark.parametrize("field, value", [
    ("name", "a" * 121),
    ("description", "a" * 2001),
    ("discussion_text", "a" * 100_001),
    ("name", None),
    ("discussion_text", None),
    ("discussion_text", 123),
    ("status", "approved"),
])
def test_invalid_or_oversized_input(client, field, value):
    assert client.post(PROJECTS, json={**PAYLOAD, field: value}).status_code == 422


def test_length_boundaries_and_original_text():
    original = " \n Café\r\nClient words\t "
    payload = ProjectCreate(name="  Project  ", discussion_text=original)
    assert payload.name == "Project"
    assert payload.discussion_text == original
    ProjectCreate(name="a" * 120, description="b" * 2000, discussion_text="c" * 100_000)


@pytest.mark.parametrize("project_id", ["bad", "g" * 24, "a" * 23, "a" * 25])
def test_malformed_id(client, project_id):
    assert client.get(f"{PROJECTS}/{project_id}").status_code == 422


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "offset=10001", "limit=abc"])
def test_pagination_bounds(client, query):
    assert client.get(f"{PROJECTS}?{query}").status_code == 422


def test_missing_database_configuration(client):
    responses = [
        client.post(PROJECTS, json=PAYLOAD),
        client.get(PROJECTS),
        client.get(f"{PROJECTS}/{'a' * 24}"),
    ]
    assert all(response.status_code == 503 for response in responses)
    assert all(response.json() == {"detail": UNAVAILABLE_DETAIL} for response in responses)
    assert client.get("/api/v1/component-1/health").status_code == 200


@pytest.mark.parametrize("uri", ["not-a-mongodb-uri", "mongodb://", "mongodb://127.0.0.1:1"])
def test_bad_or_unreachable_database_keeps_health_available(uri):
    settings = Settings(_env_file=None, mongodb_uri=uri, mongodb_timeout_ms=100)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/component-1/health").status_code == 200
        assert client.post(PROJECTS, json=PAYLOAD).status_code == 503
        assert client.get(PROJECTS).status_code == 503
        assert client.get(f"{PROJECTS}/{'a' * 24}").status_code == 503


def test_driver_failures_are_sanitized(client, caplog):
    sensitive_detail = "mongodb://user:secret@example.test Original confidential discussion"
    repository = SimpleNamespace(**{
        method: AsyncMock(side_effect=OperationFailure(sensitive_detail))
        for method in ["create", "list", "get"]
    })
    client.app.state.projects = repository
    for response in [
        client.post(PROJECTS, json=PAYLOAD),
        client.get(PROJECTS),
        client.get(f"{PROJECTS}/{'a' * 24}"),
    ]:
        assert response.status_code == 503
        assert response.json() == {"detail": UNAVAILABLE_DETAIL}
        assert sensitive_detail not in response.text
    assert sensitive_detail not in caplog.text


def test_mongodb_environment(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://user:secret@localhost:27017")
    monkeypatch.setenv("MONGODB_DATABASE", "intellise_test_config")
    settings = Settings(_env_file=None)
    assert settings.mongodb_database == "intellise_test_config"
    assert settings.mongodb_uri.get_secret_value() == "mongodb://user:secret@localhost:27017"
    assert "secret@" not in repr(settings)
    isolated = Settings(_env_file=None, mongodb_uri="mongodb://127.0.0.1:27081", mongodb_database="isolated_override")
    assert isolated.mongodb_database == "isolated_override"
    assert isolated.mongodb_uri.get_secret_value() == "mongodb://127.0.0.1:27081"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mongodb_database="invalid/database")


def test_project_post_preflight(client):
    response = client.options(PROJECTS, headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
