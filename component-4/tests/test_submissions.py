from starlette.testclient import TestClient


def test_create_manual_submission_success(client: TestClient):
    """Verify successful creation of a manual code submission."""
    payload = {
        "code": "def add(a: int, b: int) -> int:\n    return a + b\n",
        "language": "python",
        "filename": "calculator.py",
        "requirement_ids": ["REQ-001", "REQ-002"],
        "metadata": {"author": "Component-3", "module": "math"},
    }
    response = client.post("/api/v1/submissions", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["id"].startswith("sub-")
    assert data["code"] == payload["code"]
    assert data["language"] == "python"
    assert data["filename"] == "calculator.py"
    assert data["requirement_ids"] == ["REQ-001", "REQ-002"]
    assert data["source_type"] == "manual_entry"
    assert data["metadata"]["author"] == "Component-3"
    assert "created_at" in data


def test_create_manual_submission_without_optional_fields(client: TestClient):
    """Verify manual submission succeeds when filename and requirement_ids are omitted."""
    payload = {
        "code": "console.log('Hello, World!');",
        "language": "javascript",
    }
    response = client.post("/api/v1/submissions", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"].startswith("sub-")
    assert data["language"] == "javascript"
    assert data["filename"] is None
    assert data["requirement_ids"] == []


def test_create_submission_empty_code_rejected(client: TestClient):
    """Verify that an empty or whitespace-only code payload is rejected."""
    payload = {
        "code": "   \n\t  ",
        "language": "python",
    }
    response = client.post("/api/v1/submissions", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data


def test_create_submission_missing_language_rejected(client: TestClient):
    """Verify that omitting language field fails validation."""
    payload = {
        "code": "print('Hello')",
    }
    response = client.post("/api/v1/submissions", json=payload)
    assert response.status_code == 422


def test_create_submission_invalid_language_rejected(client: TestClient):
    """Verify that providing an unsupported language fails validation."""
    payload = {
        "code": "print('Hello')",
        "language": "unsupported_xyz_lang",
    }
    response = client.post("/api/v1/submissions", json=payload)
    assert response.status_code == 422


def test_list_submissions(client: TestClient):
    """Verify listing and pagination of stored submissions."""
    # Create two submissions
    client.post(
        "/api/v1/submissions",
        json={"code": "x = 1", "language": "python", "filename": "a.py"},
    )
    client.post(
        "/api/v1/submissions",
        json={"code": "y = 2", "language": "python", "filename": "b.py"},
    )

    response = client.get("/api/v1/submissions?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_get_submission_by_id_success(client: TestClient):
    """Verify retrieving a specific submission by its unique ID."""
    create_res = client.post(
        "/api/v1/submissions",
        json={"code": "def test(): pass", "language": "python"},
    )
    sub_id = create_res.json()["id"]

    get_res = client.get(f"/api/v1/submissions/{sub_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["id"] == sub_id
    assert data["code"] == "def test(): pass"


def test_get_nonexistent_submission_returns_404(client: TestClient):
    """Verify that querying an unknown submission ID returns a structured 404 error."""
    response = client.get("/api/v1/submissions/sub-nonexistent-id")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "was not found" in data["error"]["message"]
