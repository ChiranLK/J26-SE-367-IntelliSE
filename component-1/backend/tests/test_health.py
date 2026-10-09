import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from intelise_c1.core.config import Settings
from intelise_c1.main import create_app


@pytest.fixture
def client():
    settings = Settings(_env_file=None, cors_origins=["http://localhost:5173"])
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health_reports_only_process_state(client):
    response = client.get("/api/v1/component-1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "component": "component-1",
        "service": "requirement-engineering",
    }


def test_allowed_origin_can_read_health(client):
    response = client.get(
        "/api/v1/component-1/health", headers={"Origin": "http://localhost:5173"}
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unlisted_origin_is_not_allowed(client):
    response = client.get(
        "/api/v1/component-1/health", headers={"Origin": "https://unlisted.example"}
    )
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", ["*", "https://*.example", "http://localhost:5173/"])
def test_cors_requires_explicit_origins(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=[origin])
