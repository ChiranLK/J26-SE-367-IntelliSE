"""Real isolated MongoDB; ASR/extraction/classifier outputs explicitly mocked."""
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from intelise_c1.api.extraction_schemas import ExtractionOutput
from intelise_c1.api.transcription_schemas import TranscriptResult
from intelise_c1.main import create_app
from test_projects_integration import database_settings, PROJECTS
from test_transcriptions import FakeASR, URL, terminal

pytestmark = pytest.mark.integration


def test_reviewed_audio_project_and_downstream_runs_survive_restart(database_settings, tmp_path):
    settings = database_settings.model_copy(update={'audio_temp_dir': tmp_path / 'uploads'})
    reviewed = ' \r\nCafé 👋: Guests must not delete reports.\t '
    with TestClient(create_app(settings)) as client:
        client.app.state.audio_worker.runtime = FakeASR()
        accepted = client.post(URL, files={'audio': ('sample.wav', b'mocked audio')})
        assert accepted.status_code == 202
        identifier = accepted.json()['transcription_id']
        job = terminal(client, identifier)
        assert job['status'] == 'completed'
        with MongoClient(settings.mongodb_uri.get_secret_value(), tz_aware=True) as mongo:
            original_document = mongo[settings.mongodb_database].transcription_jobs.find_one({'transcription_id': identifier})
        payload = {'name': ' Reviewed project ', 'description': 'Keep description',
                   'discussion_text': reviewed, 'transcription_id': identifier.upper()}
        response = client.post(PROJECTS, json=payload)
        assert response.status_code == 201
        project = response.json()
        p = project['transcription_provenance']
        assert project['discussion_text'] == reviewed and project['name'] == 'Reviewed project'
        assert p['original_transcript'] == job['original_transcript'] != reviewed
        assert p['transcription_id'] == identifier and p['model'] == job['model']
        assert p['original_transcript_hash'] == sha256(job['original_transcript'].encode()).hexdigest()
        assert p['reviewed_discussion_hash'] == sha256(reviewed.encode()).hexdigest()
        assert p['transcription_created_at'] == job['created_at']
        assert p['transcription_completed_at'] == job['updated_at']
        assert p['review_recorded_at'] == project['created_at']
        assert p['review_status'] == 'user_reviewed' and project['status'] == 'draft'
        assert client.get(f"{PROJECTS}/{project['id']}").json() == project
        assert client.get(f'{URL}/{identifier}').json() == job
        page = client.get(PROJECTS).json()
        assert len(page['items']) == 1
        assert 'discussion_text' not in page['items'][0] and 'transcription_provenance' not in page['items'][0]
        plain = client.post(PROJECTS, json={'name': 'Plain project', 'discussion_text': 'Original text-only source.'}).json()
        assert 'transcription_provenance' not in plain

        quote = 'Guests must not delete reports.'
        start = reviewed.index(quote)
        output = ExtractionOutput.model_validate({'candidates': [{
            'requirement_text': quote, 'actor': 'Guests', 'action': 'delete',
            'evidence': [{'quote': quote, 'start': start, 'end': start + len(quote)}],
        }]})
        client.app.state.extraction_provider = SimpleNamespace(model_identifier='mock-extractor', extract=AsyncMock(return_value=output))
        client.app.state.classifier = SimpleNamespace(predict=Mock(return_value=(['FR'], 'mock-baseline', 'a'*64)))
        extracted = client.post(f"{PROJECTS}/{project['id']}/extractions")
        assert extracted.status_code == 201
        extraction = extracted.json()
        assert extraction['source_discussion_hash'] == p['reviewed_discussion_hash']
        assert extraction['candidates'][0]['review_status'] == 'unreviewed'
        client.app.state.extraction_provider.extract.assert_awaited_once_with(reviewed)
        classify = f"{PROJECTS}/{project['id']}/extractions/{extraction['run_id']}/classifications"
        classified = client.post(classify)
        assert classified.status_code == 201
        classification = classified.json()
        assert classification['predictions'][0]['requirement_id'] == extraction['candidates'][0]['requirement_id']
        with MongoClient(settings.mongodb_uri.get_secret_value(), tz_aware=True) as mongo:
            assert mongo[settings.mongodb_database].transcription_jobs.find_one({'transcription_id': identifier}) == original_document
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f"{PROJECTS}/{project['id']}").json() == project
        assert restarted.get(f"{PROJECTS}/{plain['id']}").json() == plain
        assert restarted.get(f'{URL}/{identifier}').json() == job
        assert restarted.get(f"{PROJECTS}/{project['id']}/extractions/latest").json() == extraction
        assert restarted.get(classify + '/latest').json() == classification
        assert restarted.get('/api/v1/component-1/health').status_code == 200
    assert not list(settings.audio_temp_dir.glob('*'))


def test_real_mongo_rejects_missing_processing_failed_and_silent_jobs(database_settings, tmp_path):
    settings = database_settings.model_copy(update={'audio_temp_dir': tmp_path / 'uploads'})
    with TestClient(create_app(settings)) as client:
        payload = {'name': 'Must not be saved', 'discussion_text': 'Reviewed draft.'}
        assert client.post(PROJECTS, json={**payload, 'transcription_id': 'bad'}).status_code == 422
        assert client.post(PROJECTS, json={**payload, 'transcription_id': str(uuid4())}).status_code == 404
        asr = FakeASR()
        asr.delay = .2
        client.app.state.audio_worker.runtime = asr
        accepted = client.post(URL, files={'audio': ('a.wav', b'mocked')}).json()
        assert client.post(PROJECTS, json={**payload, 'transcription_id': accepted['transcription_id']}).status_code == 409
        terminal(client, accepted['transcription_id'])

        asr.error = 'invalid_audio'
        failed = client.post(URL, files={'audio': ('b.wav', b'mocked')}).json()
        assert terminal(client, failed['transcription_id'])['status'] == 'failed'
        assert client.post(PROJECTS, json={**payload, 'transcription_id': failed['transcription_id']}).status_code == 409
        class SilentASR(FakeASR):
            async def transcribe(self, upload, extension, pcm):
                return TranscriptResult(audio_duration_seconds=1, processing_seconds=.01,
                                        original_transcript=None, segments=[],
                                        outcome='silence_detected', asr_performed=False)
        client.app.state.audio_worker.runtime = SilentASR()
        silent = client.post(URL, files={'audio': ('c.wav', b'mocked')}).json()
        assert terminal(client, silent['transcription_id'])['status'] == 'completed'
        assert client.post(PROJECTS, json={**payload, 'transcription_id': silent['transcription_id']}).status_code == 409
        with MongoClient(settings.mongodb_uri.get_secret_value()) as mongo:
            assert mongo[settings.mongodb_database].projects.count_documents({}) == 0


def test_completed_job_can_back_multiple_reviews_without_mutation(database_settings, tmp_path):
    settings = database_settings.model_copy(update={'audio_temp_dir': tmp_path / 'uploads'})
    with TestClient(create_app(settings)) as client:
        client.app.state.audio_worker.runtime = FakeASR()
        identifier = client.post(URL, files={'audio': ('a.wav', b'mocked')}).json()['transcription_id']
        before = terminal(client, identifier)
        results = []
        for text in ['Reviewed draft one.', 'Reviewed draft two.']:
            response = client.post(PROJECTS, json={'name': 'Review', 'discussion_text': text, 'transcription_id': identifier})
            assert response.status_code == 201
            results.append(response.json()['transcription_provenance'])
        assert results[0]['reviewed_discussion_hash'] != results[1]['reviewed_discussion_hash']
        assert results[0]['original_transcript_hash'] == results[1]['original_transcript_hash']
        assert client.get(f'{URL}/{identifier}').json() == before
