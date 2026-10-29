"""Mocked classifier/persistence API tests; not research evaluation."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from bson import ObjectId
from fastapi.testclient import TestClient
import pytest
from pymongo.errors import OperationFailure

from intelise_c1.api.extraction_schemas import ExtractionOutput
from intelise_c1.core.config import Settings
from intelise_c1.main import create_app
from intelise_c1.repositories.classifications import ClassificationRepository
from intelise_c1.repositories.extractions import ExtractionRepository
from intelise_c1.services.classifier import ClassifierUnavailable, LocalClassifier
from intelise_c1.services.extraction import build_run

PROJECT = '507f1f77bcf86cd799439011'
SOURCE = 'Members can upload reports. Reports must load within two seconds.'


class CollectionDouble:
    def __init__(self, documents=None):
        self.documents = deepcopy(documents or [])
        self.create_index = AsyncMock()

    async def insert_one(self, document):
        self.documents.append({'_id': ObjectId(), **deepcopy(document)})

    async def find_one(self, query, sort=None):
        matches = [document for document in self.documents if all(document[key] == value for key, value in query.items())]
        if not matches:
            return None
        return max(matches, key=lambda document: tuple(document[key] for key, _direction in sort)) if sort else matches[0]


@pytest.fixture
def client():
    quotes = ['Members can upload reports.', 'Reports must load within two seconds.']
    output = ExtractionOutput.model_validate({'candidates': [{
        'requirement_text': quote, 'actor': None, 'action': None,
        'evidence': [{'quote': quote, 'start': SOURCE.index(quote), 'end': SOURCE.index(quote) + len(quote)}],
    } for quote in quotes]})
    extraction = build_run(SOURCE, output, PROJECT, 'mock-extractor')
    with TestClient(create_app(Settings(_env_file=None, mongodb_uri=None, classifier_model_dir=None))) as client:
        client.app.state.projects = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id=PROJECT, discussion_text=SOURCE)))
        client.app.state.extractions = ExtractionRepository(CollectionDouble([{'_id': ObjectId(), **extraction.model_dump()}]))
        client.app.state.classifications = ClassificationRepository(CollectionDouble())
        client.app.state.classifier = SimpleNamespace(predict=Mock(return_value=(['FR', 'NFR'], 'mock-baseline', 'a' * 64)))
        client.extraction = extraction
        client.url = f'/api/v1/component-1/projects/{PROJECT}/extractions/{extraction.run_id}/classifications'
        yield client


def test_mapping_unchanged_source_append_only_and_latest(client):
    before = deepcopy(client.app.state.extractions.collection.documents)
    first, second = client.post(client.url), client.post(client.url)
    assert first.status_code == second.status_code == 201
    a, b = first.json(), second.json()
    assert a['classification_id'] != b['classification_id']
    assert a['project_id'] == PROJECT and a['extraction_run_id'] == client.extraction.run_id
    assert a['model_identifier'] == 'mock-baseline' and a['model_version'] == 'a' * 64
    assert a['classified_at'].endswith('Z')
    assert a['predictions'] == [
        {'requirement_id': candidate.requirement_id, 'label': label}
        for candidate, label in zip(client.extraction.candidates, ['FR', 'NFR'], strict=True)
    ]
    assert client.app.state.extractions.collection.documents == before
    assert client.app.state.classifications.collection.documents[0]['classification_id'] == a['classification_id']
    assert len(client.app.state.classifications.collection.documents) == 2
    assert client.get(client.url + '/latest').json() == b
    client.app.state.classifier.predict.assert_called_with([item.requirement_text for item in client.extraction.candidates])
    # Existing extraction GET stays usable; review_status is unchanged.
    fetched = client.get(f'/api/v1/component-1/projects/{PROJECT}/extractions/latest')
    assert fetched.status_code == 200
    assert all(item['review_status'] == 'unreviewed' for item in fetched.json()['candidates'])


def test_no_model_unavailable_health_and_latest_still_work(client):
    assert client.post(client.url).status_code == 201
    client.app.state.classifier = LocalClassifier(None)
    response = client.post(client.url)
    assert response.status_code == 503 and 'classifier unavailable' in response.json()['detail']
    assert len(client.app.state.classifications.collection.documents) == 1
    assert client.get(client.url + '/latest').status_code == 200
    assert client.get('/api/v1/component-1/health').status_code == 200


def test_missing_or_invalid_model_directory_does_not_break_startup(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, mongodb_uri=None, classifier_model_dir=tmp_path / 'missing'))) as client:
        assert client.get('/api/v1/component-1/health').status_code == 200
    with pytest.raises(ClassifierUnavailable):
        LocalClassifier(tmp_path / 'missing').predict(['confidential text'])


@pytest.mark.parametrize('method', ['get', 'post'])
def test_missing_project_extraction_and_malformed_ids(client, method):
    suffix = '/latest' if method == 'get' else ''
    assert getattr(client, method)(client.url.replace(PROJECT, 'bad') + suffix).status_code == 422
    assert getattr(client, method)(client.url.replace(client.extraction.run_id, 'bad') + suffix).status_code == 422
    assert getattr(client, method)(client.url.replace(client.extraction.run_id, str(uuid4())) + suffix).status_code == 404
    client.app.state.projects.get.return_value = None
    assert getattr(client, method)(client.url + suffix).json()['detail'] == 'Project not found.'
    client.app.state.classifier.predict.assert_not_called()


def test_extraction_project_scope_and_no_classification_yet(client):
    assert client.get(client.url + '/latest').status_code == 404
    client.app.state.extractions.collection.documents[0]['project_id'] = str(ObjectId())
    assert client.post(client.url).status_code == 404
    assert client.app.state.classifications.collection.documents == []


@pytest.mark.parametrize('labels', [['FR'], ['FR', 'unsupported'], ['FR', 'NFR', 'FR']])
def test_invalid_predictions_persist_nothing(client, labels):
    client.app.state.classifier.predict.return_value = (labels, 'mock', 'a' * 64)
    assert client.post(client.url).status_code == 503
    assert client.app.state.classifications.collection.documents == []


def test_empty_extraction_requires_model_then_saves_empty_predictions(client):
    document = client.app.state.extractions.collection.documents[0]
    document['candidates'] = []
    client.app.state.classifier = LocalClassifier(None)
    assert client.post(client.url).status_code == 503
    client.app.state.classifier = SimpleNamespace(predict=Mock(return_value=([], 'mock', 'a' * 64)))
    response = client.post(client.url)
    assert response.status_code == 201 and response.json()['predictions'] == []
    assert client.get(client.url + '/latest').json() == response.json()


@pytest.mark.parametrize('operation', ['project', 'extraction', 'index', 'insert', 'latest', 'unconfigured'])
def test_database_failures_sanitized(client, caplog, operation):
    private = 'secret credentials and full client discussion'
    failure = AsyncMock(side_effect=OperationFailure(private))
    if operation == 'project':
        client.app.state.projects.get = failure
    elif operation == 'extraction':
        client.app.state.extractions.collection.find_one = failure
    elif operation == 'index':
        client.app.state.classifications.collection.create_index = failure
    elif operation == 'insert':
        client.app.state.classifications.collection.insert_one = failure
    elif operation == 'latest':
        client.app.state.classifications.collection.find_one = failure
    else:
        client.app.state.classifications = None
    response = client.get(client.url + '/latest') if operation == 'latest' else client.post(client.url)
    assert response.status_code == 503
    assert private not in response.text + caplog.text


def test_older_insert_and_other_extraction_do_not_replace_latest(client):
    from datetime import timedelta
    first = client.post(client.url).json()
    older = deepcopy(client.app.state.classifications.collection.documents[0])
    older['_id'] = ObjectId()
    older['classification_id'] = str(uuid4())
    older['classified_at'] -= timedelta(days=1)
    other = {**older, '_id': ObjectId(), 'extraction_run_id': str(uuid4())}
    client.app.state.classifications.collection.documents.extend([older, other])
    assert client.get(client.url + '/latest').json() == first
