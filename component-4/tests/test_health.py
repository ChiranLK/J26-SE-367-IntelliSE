from starlette.testclient import TestClient


def test_root_endpoint(client: TestClient):
    """Verify that root endpoint returns service metadata and documentation links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "INTELISE Component 4" in data["name"]
    assert data["version"] == "0.1.0"
    assert data["docs"] == "/docs"
    assert data["phase"] == "Phase 1 - Backend Foundation"


def test_health_check_endpoint(client: TestClient):
    """Verify that the health-check endpoint reports healthy status and storage mode."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "INTELISE Component 4" in data["service"]
    assert data["version"] == "0.1.0"
    assert data["storage_backend"] == "memory"
    assert data["is_ephemeral_storage"] is True
    assert "timestamp" in data


def test_api_v1_health_check_endpoint(client: TestClient):
    """Verify that the versioned /api/v1/health endpoint also operates correctly."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["storage_backend"] == "memory"
