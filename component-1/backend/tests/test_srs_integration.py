"""Real isolated MongoDB; upstream model responses explicitly mocked at API boundary."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from intelise_c1.api.extraction_schemas import ExtractionOutput
from intelise_c1.main import create_app
from test_projects_integration import database_settings, PROJECTS  # noqa: F401

pytestmark = pytest.mark.integration


def test_srs_history_approval_conflicts_and_restart(database_settings):
    settings = database_settings
    quotes = ['Students shall be able to add courses.', 'Results shall appear within one second.']
    source = ' '.join(quotes)
    with TestClient(create_app(settings)) as client:
        project = client.post(PROJECTS, json={'name': 'Disposable SRS integration', 'discussion_text': source}).json()
        project_url = f"{PROJECTS}/{project['id']}"
        client.app.state.extraction_provider = SimpleNamespace(model_identifier='mock-extractor', extract=AsyncMock(return_value=ExtractionOutput.model_validate({'candidates': [dict(requirement_text=quote, actor=None, action=None, evidence=[dict(quote=quote, start=source.index(quote), end=source.index(quote)+len(quote))]) for quote in quotes]})))
        client.app.state.classifier = SimpleNamespace(predict=Mock(return_value=(['FR', 'NFR'], 'mock-baseline', 'a'*64)))
        response = client.post(project_url + '/extractions')
        assert response.status_code == 201, response.text
        extraction = response.json()
        classifications = f"{project_url}/extractions/{extraction['run_id']}/classifications"
        classification = client.post(classifications).json()
        for item, label in zip(extraction['candidates'][:1], ['FR']):
            response = client.post(f"{classifications}/{classification['classification_id']}/requirements/{item['requirement_id']}/reviews", json=dict(submission_id=str(uuid4()), reviewed_label=label, reviewer_id='Analyst', note=''))
            assert response.status_code == 201
        url = project_url + '/srs'
        body = dict(submission_id=str(uuid4()), expected_revision=0, reviewer_id='Analyst', extraction_run_id=extraction['run_id'], classification_id=classification['classification_id'])
        response = client.post(url, json=body)
        assert response.status_code == 200, response.text
        state = response.json()
        assert client.post(url, json=body).json() == state
        version = state['versions'][-1]
        first = version['requirements'][0]['requirement_id']
        competing = [dict(submission_id=str(uuid4()), expected_revision=state['revision'], reviewer_id='Client', version_id=version['version_id'], requirement_id=first, decision='needs_clarification', comment=f'Question {i}') for i in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda data: client.post(url + '/feedback', json=data), competing))
        assert sorted(r.status_code for r in responses) == [200, 409]
        state = client.get(url).json()
        assert len(state['versions'][-1]['feedback']) == 1
        assert version['requirements'][1]['label_review_id'] is None
        bulk_body = dict(submission_id=str(uuid4()), expected_revision=state['revision'], reviewer_id='Client', version_id=version['version_id'], confirm=True)
        response = client.post(url + '/accept-remaining', json=bulk_body)
        assert response.status_code == 200
        state = response.json()
        assert [entry['decision'] for entry in state['versions'][0]['feedback']] == ['needs_clarification', 'accepted']
        assert client.post(url + '/accept-remaining', json=bulk_body).json() == state
        assert client.post(url + '/approval', json=dict(submission_id=str(uuid4()), expected_revision=state['revision'], reviewer_id='Client', version_id=version['version_id'], confirm=True)).status_code == 409
        response = client.post(url + '/feedback', json=dict(submission_id=str(uuid4()), expected_revision=state['revision'], reviewer_id='Client', version_id=version['version_id'], requirement_id=first, decision='accepted'))
        assert response.status_code == 200
        state = response.json()
        response = client.post(url + '/approval', json=dict(submission_id=str(uuid4()), expected_revision=state['revision'], reviewer_id='Client', version_id=version['version_id'], confirm=True))
        assert response.status_code == 200
        approved = response.json()
        response = client.post(url + '/revisions', json=dict(submission_id=str(uuid4()), expected_revision=approved['revision'], reviewer_id='Analyst', base_version_id=version['version_id'], changes=[dict(requirement_id=first, text='Students shall be able to add and name courses.', label='FR', reason='Client requested names')]))
        assert response.status_code == 200
        final = response.json()
        assert final['versions'][0] == approved['versions'][0]
        assert final['versions'][1]['status'] == 'draft'
        assert final['versions'][1]['feedback'] == []
        with MongoClient(settings.mongodb_uri.get_secret_value(), serverSelectionTimeoutMS=2000) as mongo:
            assert mongo[settings.mongodb_database].srs_projects.count_documents({}) == 1
            assert mongo[settings.mongodb_database].srs_projects.find_one({'_id': project['id']})['revision'] == final['revision']
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(url).json() == final
        assert restarted.get(project_url).json() == project
        assert restarted.get(project_url + '/extractions/latest').json() == extraction
        assert restarted.get(classifications + '/latest').json() == classification
        assert restarted.get('/api/v1/component-1/health').status_code == 200
