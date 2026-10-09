"""Availability and CORS smoke checks without external services."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from intelise_c1.core.config import Settings
from intelise_c1.main import create_app

HEALTH_PATH = "/api/v1/component-1/health"


@pytest.fixture
def client():
    settings = Settings(_env_file=None, mongodb_uri=None, cors_origins=["http://localhost:5173"])
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health(client):
    response = client.get(HEALTH_PATH)
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "component": "component-1",
        "service": "requirement-engineering",
    }


def test_allowed_origin(client):
    response = client.get(HEALTH_PATH, headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize("origin, status", [("http://localhost:5173", 200), ("https://unlisted.example", 400)])
def test_cors_preflight(client, origin, status):
    response = client.options(
        HEALTH_PATH,
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == status
    assert response.headers.get("access-control-allow-origin") == (origin if status == 200 else None)


def test_unlisted_origin(client):
    response = client.get(HEALTH_PATH, headers={"Origin": "https://unlisted.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("C1_BACKEND_HOST", "0.0.0.0")
    monkeypatch.setenv("C1_BACKEND_PORT", "8011")
    monkeypatch.setenv("C1_CORS_ORIGINS", '["http://localhost:3000"]')
    settings = Settings(_env_file=None)
    assert settings.backend_host == "0.0.0.0"
    assert settings.backend_port == 8011
    assert settings.cors_origins == ["http://localhost:3000"]


@pytest.mark.parametrize("origin", ["*", "http://localhost:5173/", "https://example.com/path"])
def test_reject_non_origin_cors_values(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=[origin])
