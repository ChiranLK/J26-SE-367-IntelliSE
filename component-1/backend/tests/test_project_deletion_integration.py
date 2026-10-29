"""Actual MongoDB with generated isolated DBs; mocked ASR/extraction/classifier."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo import MongoClient
import pytest

from intelise_c1.api.extraction_schemas import ExtractionOutput
from intelise_c1.main import create_app
from test_projects_integration import database_settings, PROJECTS
from test_transcriptions import FakeASR, URL, terminal

pytestmark = pytest.mark.integration


def test_delete_hides_project_and_runs_but_retains_sources_across_restart(database_settings, tmp_path):
    settings = database_settings.model_copy(update={'audio_temp_dir': tmp_path / 'uploads'})
    source = 'Users shall be able to add two numbers.'
    output = ExtractionOutput.model_validate({'candidates': [{'requirement_text': source, 'actor': None, 'action': None,
        'evidence': [{'quote': source, 'start': 0, 'end': len(source)}]}]})
    with TestClient(create_app(settings)) as client:
        client.app.state.audio_worker.runtime = FakeASR()
        accepted = client.post(URL, files={'audio': ('sample.wav', b'mocked audio')})
        assert accepted.status_code == 202
        job_id = accepted.json()['transcription_id']
        job = terminal(client, job_id)
        assert job['status'] == 'completed'
        client.app.state.extraction_provider = SimpleNamespace(model_identifier='mock-extractor', extract=AsyncMock(return_value=output))
        client.app.state.classifier = SimpleNamespace(predict=Mock(return_value=(['FR'], 'mock-baseline', 'a'*64)))
        response = client.post(PROJECTS, json={'name': 'Disposable delete check', 'discussion_text': source, 'transcription_id': job_id})
        assert response.status_code == 201
        project = response.json()
        other = client.post(PROJECTS, json={'name': 'Keep this test project', 'discussion_text': 'Original test text.'}).json()
        project_url = f"{PROJECTS}/{project['id']}"
        extraction = client.post(project_url + '/extractions').json()
        class_url = project_url + f"/extractions/{extraction['run_id']}/classifications"
        classification = client.post(class_url).json()
        root = class_url + '/' + classification['classification_id']
        review = client.post(root + f"/requirements/{extraction['candidates'][0]['requirement_id']}/reviews", json={
            'submission_id': str(uuid4()), 'reviewed_label': 'FR', 'reviewer_id': 'Integration reviewer'} )
        assert review.status_code == 201
        assert client.delete(project_url).status_code == 204
        assert client.get(project_url).status_code == 404
        assert [item['id'] for item in client.get(PROJECTS).json()['items']] == [other['id']]
        assert client.get(project_url + '/extractions/latest').status_code == 404
        assert client.post(project_url + '/extractions').status_code == 404
        assert client.get(class_url + '/latest').status_code == 404
        assert client.post(class_url).status_code == 404
        assert client.get(root + '/reviews').status_code == 404
        assert client.get(f'{URL}/{job_id}').json() == job
        assert client.delete(f'{PROJECTS}/{ObjectId()}').status_code == 404
    with MongoClient(settings.mongodb_uri.get_secret_value(), tz_aware=True) as mongo:
        db = mongo[settings.mongodb_database]
        retained = db.projects.find_one({'_id': ObjectId(project['id'])})
        assert retained['discussion_text'] == source
        assert retained['transcription_provenance']['transcription_id'] == job_id
        assert db.extraction_runs.count_documents({'project_id': project['id']}) == 1
        assert db.classification_runs.count_documents({'project_id': project['id']}) == 1
        assert db.classification_reviews.count_documents({'project_id': project['id']}) == 1
        assert db.transcription_jobs.count_documents({'transcription_id': job_id}) == 1
        before = retained.copy()
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(project_url).status_code == 404
        assert restarted.delete(project_url).status_code == 204
        assert restarted.get(f"{PROJECTS}/{other['id']}").json() == other
        assert restarted.get(f'{URL}/{job_id}').json() == job
    with MongoClient(settings.mongodb_uri.get_secret_value(), tz_aware=True) as mongo:
        after = mongo[settings.mongodb_database].projects.find_one({'_id': ObjectId(project['id'])})
        assert after == before  # Repeated deletion preserves the first deletion time and source.
