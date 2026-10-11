"""Real MongoDB tests; never use the application's configured database."""

from datetime import datetime, timedelta
import os
from uuid import uuid4

from bson import ObjectId
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from intelise_c1.core.config import Settings
from intelise_c1.main import create_app

pytestmark = pytest.mark.integration
PROJECTS = "/api/v1/component-1/projects"


@pytest.fixture
def database_settings():
    uri = os.environ.get("TEST_MONGODB_URI")
    if not uri:
        pytest.skip("Set TEST_MONGODB_URI to run isolated real-MongoDB integration tests")
    # A generated name prevents writing to or dropping existing application data.
    database_name = f"intellise_c1_test_{uuid4().hex}"
    cleanup_client = MongoClient(uri, serverSelectionTimeoutMS=2000, timeoutMS=2000, tz_aware=True)
    connected = False
    try:
        cleanup_client.admin.command("ping")
        connected = True
        yield Settings(_env_file=None, mongodb_uri=uri, mongodb_database=database_name)
    finally:
        try:
            if connected:
                cleanup_client.drop_database(database_name)
        finally:
            cleanup_client.close()


@pytest.fixture
def client(database_settings):
    with TestClient(create_app(database_settings)) as test_client:
        yield test_client


def test_create_and_retrieve_original_discussion(client):
    original = " \n Café stakeholders said:\r\nKeep this exact text.\t "
    payload = {"name": "  Client portal  ", "description": "A test-only project.", "discussion_text": original}
    response = client.post(PROJECTS, json=payload)
    assert response.status_code == 201
    record = response.json()
    assert ObjectId.is_valid(record["id"])
    assert record["name"] == "Client portal"
    assert record["description"] == payload["description"]
    assert record["discussion_text"] == original
    assert record["status"] == "draft"
    assert record["created_at"] == record["updated_at"]
    assert datetime.fromisoformat(record["created_at"]).utcoffset() == timedelta(0)
    fetched = client.get(f"{PROJECTS}/{record['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == record


def test_paginated_newest_first_listing(client):
    assert client.get(PROJECTS).json() == {"items": [], "limit": 20, "offset": 0, "has_more": False}
    ids = []
    for index in range(5):
        response = client.post(PROJECTS, json={"name": f"Project {index}", "discussion_text": "Private test-only text."})
        assert response.status_code == 201
        ids.append(response.json()["id"])
    seen = []
    for offset in [0, 2, 4]:
        response = client.get(PROJECTS, params={"limit": 2, "offset": offset})
        assert response.status_code == 200
        page = response.json()
        assert page["limit"] == 2 and page["offset"] == offset
        assert page["has_more"] == (offset < 4)
        for item in page["items"]:
            assert "discussion_text" not in item
            assert "_id" not in item
        seen.extend(item["id"] for item in page["items"])
    assert seen == list(reversed(ids))
    assert client.get(PROJECTS, params={"offset": 10000}).json()["items"] == []


def test_nonexistent_id(client):
    response = client.get(f"{PROJECTS}/{ObjectId()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_persistence_across_application_restart(database_settings):
    # Closing the first lifespan closes its actual MongoDB client. The new app
    # opens a fresh client and must read the record from the same isolated DB.
    with TestClient(create_app(database_settings)) as first:
        response = first.post(PROJECTS, json={"name": "Restart check", "discussion_text": "Original restart-test text."})
        assert response.status_code == 201
        saved = response.json()
    with TestClient(create_app(database_settings)) as restarted:
        response = restarted.get(f"{PROJECTS}/{saved['id']}")
        assert response.status_code == 200
        assert response.json() == saved
