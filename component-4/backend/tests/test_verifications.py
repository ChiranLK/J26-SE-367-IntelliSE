import pytest
from starlette.testclient import TestClient
from app.core.config import settings
from app.core.errors import StorageException
from app.repositories import get_submission_repository, get_verification_repository
from app.repositories.in_memory import (
    InMemorySubmissionRepository,
    InMemoryVerificationRunRepository,
)
from app.schemas.common import VerificationStatus
from app.schemas.verification import VerificationRunResponse


def test_create_verification_run_success(client: TestClient):
    """
    Verify creating a verification run for a submission.
    Ensures initial status is strictly PENDING and no simulated tests/agents are executed.
    """
    # 1. Create a submission first
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": "def multiply(x, y): return x * y", "language": "python"},
    )
    assert sub_res.status_code == 201
    submission_id = sub_res.json()["id"]

    # 2. Initiate verification run
    run_payload = {
        "submission_id": submission_id,
        "triggered_by": "manual",
        "test_types": ["unit", "integration"],
    }
    run_res = client.post("/api/v1/verifications", json=run_payload)
    assert run_res.status_code == 201
    run_data = run_res.json()

    assert run_data["id"].startswith("run-")
    assert run_data["submission_id"] == submission_id
    # Crucial Phase 1 restriction: must be PENDING, not falsely PASSED
    assert run_data["status"] == "PENDING"
    assert run_data["test_results"] == []
    assert run_data["defect_reports"] == []
    assert run_data["feedback_iterations"] == []
    assert run_data["error_message"] is None
    assert "created_at" in run_data
    assert "updated_at" in run_data


def test_create_verification_run_nonexistent_submission_fails(client: TestClient):
    """Verify that initiating a run for a non-existent submission returns 404."""
    run_payload = {
        "submission_id": "sub-unknown-99999",
    }
    response = client.post("/api/v1/verifications", json=run_payload)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_get_verification_run_details(client: TestClient):
    """Verify retrieving full verification run details by ID."""
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": "print('test')", "language": "python"},
    )
    submission_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications",
        json={"submission_id": submission_id},
    )
    run_id = run_res.json()["id"]

    get_res = client.get(f"/api/v1/verifications/{run_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["id"] == run_id
    assert data["submission_id"] == submission_id
    assert data["status"] == "PENDING"


def test_get_verification_run_status(client: TestClient):
    """Verify retrieving lightweight status of a verification run."""
    sub_res = client.post(
        "/api/v1/submissions",
        json={"code": "print('status check')", "language": "python"},
    )
    submission_id = sub_res.json()["id"]

    run_res = client.post(
        "/api/v1/verifications",
        json={"submission_id": submission_id},
    )
    run_id = run_res.json()["id"]

    status_res = client.get(f"/api/v1/verifications/{run_id}/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["id"] == run_id
    assert status_data["submission_id"] == submission_id
    assert status_data["status"] == "PENDING"
    assert "updated_at" in status_data


def test_get_nonexistent_verification_run_returns_404(client: TestClient):
    """Verify that querying a nonexistent verification run returns 404."""
    details_res = client.get("/api/v1/verifications/run-does-not-exist")
    assert details_res.status_code == 404

    status_res = client.get("/api/v1/verifications/run-does-not-exist/status")
    assert status_res.status_code == 404


def test_list_verification_runs_with_filter(client: TestClient):
    """Verify listing runs and filtering by submission ID."""
    # Submission 1
    s1 = client.post(
        "/api/v1/submissions", json={"code": "x = 1", "language": "python"}
    ).json()["id"]
    # Submission 2
    s2 = client.post(
        "/api/v1/submissions", json={"code": "y = 2", "language": "python"}
    ).json()["id"]

    # Runs for s1
    client.post("/api/v1/verifications", json={"submission_id": s1})
    client.post("/api/v1/verifications", json={"submission_id": s1})
    # Run for s2
    client.post("/api/v1/verifications", json={"submission_id": s2})

    # List all
    all_runs = client.get("/api/v1/verifications").json()
    assert all_runs["total"] == 3

    # Filter by s1
    s1_runs = client.get(f"/api/v1/verifications?submission_id={s1}").json()
    assert s1_runs["total"] == 2
    assert all(item["submission_id"] == s1 for item in s1_runs["items"])

    # Filter by s2
    s2_runs = client.get(f"/api/v1/verifications?submission_id={s2}").json()
    assert s2_runs["total"] == 1
    assert s2_runs["items"][0]["submission_id"] == s2


def test_cannot_assign_passed_without_test_evidence():
    """Verify that a verification run cannot be created or serialized with PASSED status without real test evidence."""
    with pytest.raises(ValueError, match="cannot be marked PASSED without real test evidence"):
        VerificationRunResponse(
            id="run-fake-test",
            submission_id="sub-12345",
            status=VerificationStatus.PASSED,
            test_results=[],  # No evidence
        )


def test_in_memory_mode_operates_without_mongodb(monkeypatch):
    """Verify that in memory mode, repository factories succeed without requiring MongoDB."""
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "memory")
    sub_repo = get_submission_repository()
    verif_repo = get_verification_repository()
    assert isinstance(sub_repo, InMemorySubmissionRepository)
    assert isinstance(verif_repo, InMemoryVerificationRunRepository)


def test_mongodb_configured_fails_fast_on_missing_uri(monkeypatch):
    """Verify that when STORAGE_BACKEND='mongodb' is configured, failure to connect raises StorageException and NEVER silently falls back."""
    import app.repositories as repos
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "mongodb")
    monkeypatch.setattr(settings, "MONGODB_URI", "")
    # Clear cached singletons for this test
    monkeypatch.setattr(repos, "_mongo_submission_repo", None)
    monkeypatch.setattr(repos, "_mongo_verification_repo", None)

    with pytest.raises(StorageException, match="STORAGE_BACKEND is set to 'mongodb'"):
        get_submission_repository()

    with pytest.raises(StorageException, match="STORAGE_BACKEND is set to 'mongodb'"):
        get_verification_repository()

