"""Mocked storage/ASR boundary tests; no recognition-accuracy claims."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure
from pydantic import ValidationError

from intelise_c1.api.transcription_schemas import TranscriptionJob
from intelise_c1.core.config import Settings
from intelise_c1.main import create_app
from intelise_c1.repositories.projects import ProjectRepository
from intelise_c1.repositories.transcriptions import now
from test_transcriptions import RESULT

URL = '/api/v1/component-1/projects'
PAYLOAD = {'name': ' Reviewed project ', 'description': 'Keep description',
           'discussion_text': ' \r\nCafé 👋: Users must not delete accounts.\t '}


def completed():
    return TranscriptionJob(transcription_id=str(uuid4()), status='completed', model='tiny.en',
                            created_at=now(), updated_at=now(), upload_bytes=100, **RESULT)


@pytest.fixture
def client():
    collection = SimpleNamespace(create_index=AsyncMock(), insert_one=AsyncMock(), find_one=AsyncMock())
    source = SimpleNamespace(get=AsyncMock(return_value=completed()))
    with TestClient(create_app(Settings(_env_file=None))) as api:
        api.app.state.projects = ProjectRepository(collection, source)
        api.collection, api.source = collection, source
        yield api


def test_edited_review_original_hashes_and_trusted_metadata(client):
    job = client.source.get.return_value
    before = deepcopy(job.model_dump())
    response = client.post(URL, json={**PAYLOAD, 'transcription_id': job.transcription_id})
    assert response.status_code == 201
    project = response.json()
    assert project['discussion_text'] == PAYLOAD['discussion_text']
    assert project['description'] == PAYLOAD['description']
    assert project['name'] == 'Reviewed project' and project['status'] == 'draft'
    p = project['transcription_provenance']
    assert p['transcription_id'] == job.transcription_id
    assert p['model'] == job.model and p['language'] == 'en' and p['provider'] == 'whisper'
    assert p['original_transcript'] == job.original_transcript
    assert p['original_transcript'] != project['discussion_text']
    assert p['original_transcript_hash'] == sha256(job.original_transcript.encode('utf-8')).hexdigest()
    assert p['reviewed_discussion_hash'] == sha256(PAYLOAD['discussion_text'].encode('utf-8')).hexdigest()
    assert p['schema_version'] == 'c1-transcription-provenance-v1' and p['review_status'] == 'user_reviewed'
    assert p['review_recorded_at'] == project['created_at']
    assert p['segments'] == [s.model_dump() for s in job.segments]
    assert job.model_dump() == before
    client.source.get.assert_awaited_once_with(job.transcription_id)
    saved = client.collection.insert_one.call_args.args[0]
    assert 'transcription_id' not in saved and saved['transcription_provenance']['transcription_id'] == job.transcription_id
    client.collection.find_one.return_value = saved
    assert client.get(URL + '/' + project['id']).json() == project


@pytest.mark.parametrize('reference', [None, 'omitted'])
def test_text_only_wire_and_storage_unchanged(client, reference):
    payload = dict(PAYLOAD)
    if reference is None: payload['transcription_id'] = None
    response = client.post(URL, json=payload)
    assert response.status_code == 201
    assert set(response.json()) == {'id', 'name', 'description', 'discussion_text', 'status', 'created_at', 'updated_at'}
    client.source.get.assert_not_awaited()
    saved = client.collection.insert_one.call_args.args[0]
    assert 'transcription_id' not in saved and 'transcription_provenance' not in saved


@pytest.mark.parametrize('identifier', ['', 'bad', '../job', 123, {}, 'a'*36])
def test_malformed_reference_rejected_before_storage(client, identifier):
    assert client.post(URL, json={**PAYLOAD, 'transcription_id': identifier}).status_code == 422
    client.collection.insert_one.assert_not_awaited()
    client.source.get.assert_not_awaited()


@pytest.mark.parametrize('status', ['queued', 'processing', 'failed'])
def test_uncompleted_source_is_conflict_and_never_text_fallback(client, status):
    job = completed().model_copy(update={'status': status})
    client.source.get.return_value = job
    response = client.post(URL, json={**PAYLOAD, 'transcription_id': job.transcription_id})
    assert response.status_code == 409
    assert 'must be completed' in response.json()['detail']
    client.collection.insert_one.assert_not_awaited()


def test_missing_reference_is_404(client):
    client.source.get.return_value = None
    assert client.post(URL, json={**PAYLOAD, 'transcription_id': str(uuid4())}).status_code == 404
    client.collection.insert_one.assert_not_awaited()


@pytest.mark.parametrize('changes', [
    {'original_transcript': None}, {'original_transcript': '   '}, {'segments': [] , 'original_transcript': '', 'outcome': 'no_intelligible_speech'},
    {'original_transcript': None, 'segments': [], 'asr_performed': False, 'outcome': 'silence_detected'},
    {'model': ''}, {'audio_duration_seconds': None}, {'processing_seconds': None}, {'error_code': 'transcription_failed'},
])
def test_unusable_completed_result_is_409(client, changes):
    job = completed().model_copy(update=changes)
    client.source.get.return_value = job
    response = client.post(URL, json={**PAYLOAD, 'transcription_id': job.transcription_id})
    assert response.status_code == 409
    assert 'valid speech result' in response.json()['detail']
    client.collection.insert_one.assert_not_awaited()


@pytest.mark.parametrize('metadata', [{'model': 'client-model'}, {'transcription_provenance': {}}, {'review_status': 'verified'}, {'original_transcript_hash': 'a'*64}])
def test_client_cannot_override_provenance(client, metadata):
    assert client.post(URL, json={**PAYLOAD, 'transcription_id': completed().transcription_id, **metadata}).status_code == 422
    client.collection.insert_one.assert_not_awaited()


def test_invalid_stored_schema_is_sanitized_conflict(client, caplog):
    try:
        TranscriptionJob.model_validate({'original_transcript': 'private speech'})
    except ValidationError as error:
        client.source.get.side_effect = error
    response = client.post(URL, json={**PAYLOAD, 'transcription_id': str(uuid4())})
    assert response.status_code == 409 and 'private speech' not in response.text
    assert 'private speech' not in caplog.text
    client.collection.insert_one.assert_not_awaited()


@pytest.mark.parametrize('stage', ['lookup', 'insert'])
def test_database_failures_do_not_fall_back_or_leak_data(client, stage):
    job = client.source.get.return_value
    failing = client.source.get if stage == 'lookup' else client.collection.insert_one
    failing.side_effect = OperationFailure('private speech secret credentials')
    response = client.post(URL, json={**PAYLOAD, 'transcription_id': job.transcription_id})
    assert response.status_code == 503 and 'secret' not in response.text and 'private speech' not in response.text
    if stage == 'lookup': client.collection.insert_one.assert_not_awaited()


def test_normal_app_openapi_exposes_audio_and_optional_provenance(client):
    schema = client.get('/openapi.json').json()
    assert '/api/v1/component-1/transcriptions' in schema['paths']
    assert '/api/v1/component-1/transcriptions/{transcription_id}' in schema['paths']
    create = schema['components']['schemas']['ProjectCreate']
    assert 'transcription_id' in create['properties'] and 'transcription_id' not in create['required']
    assert create['additionalProperties'] is False
    assert 'transcription_provenance' in schema['components']['schemas']['ProjectRecord']['properties']
