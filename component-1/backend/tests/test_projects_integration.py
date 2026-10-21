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


def test_extraction_runs_persist_across_restart(database_settings):
    """Real MongoDB persistence with mocked extraction; no live-model accuracy claim."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from intelise_c1.api.extraction_schemas import ExtractionOutput

    source = "Guests must not delete reports."
    output = ExtractionOutput.model_validate({"candidates": [{
        "requirement_text": source, "actor": "Guests", "action": "delete",
        "evidence": [{"quote": source, "start": 0, "end": len(source)}],
    }]})
    with TestClient(create_app(database_settings)) as first:
        first.app.state.extraction_provider = SimpleNamespace(
            model_identifier="mock-model", extract=AsyncMock(return_value=output)
        )
        project = first.post(PROJECTS, json={"name": "Extraction restart", "discussion_text": source}).json()
        url = f"{PROJECTS}/{project['id']}/extractions"
        a, b = first.post(url), first.post(url)
        assert a.status_code == b.status_code == 201
        assert a.json()["run_id"] != b.json()["run_id"]
    with TestClient(create_app(database_settings)) as restarted:
        assert restarted.get(url + "/latest").json() == b.json()
        assert restarted.get(f"{PROJECTS}/{project['id']}").json() == project
    with MongoClient(database_settings.mongodb_uri.get_secret_value()) as mongo:
        records = list(mongo[database_settings.mongodb_database].extraction_runs.find({"project_id": project["id"]}))
        assert {record["run_id"] for record in records} == {a.json()["run_id"], b.json()["run_id"]}


def test_classification_runs_survive_restart_without_model(database_settings):
    """Real MongoDB, mocked extraction/classifier; not live-model evaluation."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from intelise_c1.api.extraction_schemas import ExtractionOutput

    source = 'Members can export reports.'
    output = ExtractionOutput.model_validate({'candidates': [{
        'requirement_text': source, 'actor': 'Members', 'action': 'export',
        'evidence': [{'quote': source, 'start': 0, 'end': len(source)}],
    }]})
    with TestClient(create_app(database_settings)) as first:
        first.app.state.extraction_provider = SimpleNamespace(model_identifier='mock-extractor', extract=AsyncMock(return_value=output))
        first.app.state.classifier = SimpleNamespace(predict=Mock(return_value=(['FR'], 'mock-baseline', 'a' * 64)))
        project_response = first.post(PROJECTS, json={'name': 'Classification restart', 'discussion_text': source})
        assert project_response.status_code == 201
        project = project_response.json()
        extracted = first.post(f"{PROJECTS}/{project['id']}/extractions")
        assert extracted.status_code == 201
        extraction = extracted.json()
        url = f"{PROJECTS}/{project['id']}/extractions/{extraction['run_id']}/classifications"
        a, b = first.post(url), first.post(url)
        assert a.status_code == b.status_code == 201
        assert a.json()['classification_id'] != b.json()['classification_id']
    with TestClient(create_app(database_settings)) as restarted:
        assert restarted.get(url + '/latest').json() == b.json()
        assert restarted.get(f"{PROJECTS}/{project['id']}/extractions/latest").json() == extraction
        assert restarted.get(f"{PROJECTS}/{project['id']}").json() == project
        assert restarted.post(url).status_code == 503  # No trained classifier configured.
    with MongoClient(database_settings.mongodb_uri.get_secret_value()) as mongo:
        records = list(mongo[database_settings.mongodb_database].classification_runs.find({'extraction_run_id': extraction['run_id']}))
        assert {record['classification_id'] for record in records} == {a.json()['classification_id'], b.json()['classification_id']}


def test_label_reviews_survive_restart_and_preserve_originals(database_settings):
    """Actual MongoDB; valid API extraction and classifier outputs are mocked."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from intelise_c1.api.extraction_schemas import ExtractionOutput

    source = 'Users shall be able to reset their passwords.'
    output = ExtractionOutput.model_validate({'candidates': [{
        'requirement_text': source, 'actor': None, 'action': None,
        'evidence': [{'quote': source, 'start': 0, 'end': len(source)}],
    }]})
    with TestClient(create_app(database_settings)) as first:
        first.app.state.extraction_provider = SimpleNamespace(model_identifier='mock-extractor', extract=AsyncMock(return_value=output))
        first.app.state.classifier = SimpleNamespace(predict=Mock(return_value=(['NFR'], 'mock-baseline', 'a' * 64)))
        response = first.post(PROJECTS, json={'name': 'Disposable label review', 'discussion_text': source})
        assert response.status_code == 201
        project = response.json()
        extracted = first.post(f"{PROJECTS}/{project['id']}/extractions")
        assert extracted.status_code == 201
        extraction = extracted.json()
        class_url = f"{PROJECTS}/{project['id']}/extractions/{extraction['run_id']}/classifications"
        response = first.post(class_url)
        assert response.status_code == 201
        classification = response.json()
        root = f"{class_url}/{classification['classification_id']}"
        payload = {'submission_id': str(uuid4()), 'reviewed_label': 'FR', 'reviewer_id': 'Integration reviewer', 'note': 'User action; reviewed manually.'}
        save_url = f"{root}/requirements/{extraction['candidates'][0]['requirement_id']}/reviews"
        response = first.post(save_url, json=payload)
        assert response.status_code == 201, response.text
        saved = response.json()
        assert saved['original_prediction'] == 'NFR' and saved['reviewed_label'] == 'FR'
        assert first.post(save_url, json=payload).json() == saved
        assert first.get(root + '/reviews').json()['reviews'] == [saved]
        newer = first.post(class_url).json()
        assert first.get(f"{class_url}/{newer['classification_id']}/reviews").json()['reviews'] == []
    with TestClient(create_app(database_settings)) as restarted:
        assert restarted.get(root + '/reviews').json()['reviews'] == [saved]
        assert restarted.get(f"{PROJECTS}/{project['id']}").json() == project
        assert restarted.get(f"{PROJECTS}/{project['id']}/extractions/latest").json() == extraction
        assert restarted.get(class_url + '/latest').json() == newer
        response = restarted.post(save_url, json=payload)
        assert response.status_code == 200 and response.json() == saved
        assert restarted.get('/api/v1/component-1/health').status_code == 200
    with MongoClient(database_settings.mongodb_uri.get_secret_value()) as mongo:
        db = mongo[database_settings.mongodb_database]
        assert db.classification_reviews.count_documents({}) == 1
        assert db.classification_runs.count_documents({}) == 2
        assert db.extraction_runs.count_documents({}) == 1
