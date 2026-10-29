"""Mocked ASR/collection checks: these do not measure recognition quality."""
import asyncio
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from intelise_c1.api.transcription_schemas import TranscriptResult, TranscriptionJob
from intelise_c1.audio import runtime as decoder
from intelise_c1.audio.worker import AudioError, AudioWorker, WhisperProcess
from intelise_c1.core.config import Settings
from intelise_c1.main import create_app
from intelise_c1.repositories.transcriptions import now

URL = '/api/v1/component-1/transcriptions'
RESULT = dict(audio_duration_seconds=1, processing_seconds=.02,
              original_transcript=' Generated original. ', segments=[dict(start=0, end=1, text=' Generated original. ')],
              outcome='review_required', asr_performed=True)


class MemoryJobs:
    """Test double only; application code always uses MongoDB."""
    def __init__(self):
        self.rows = {}

    async def create(self, job):
        self.rows[job.transcription_id] = job.model_dump()

    async def get(self, identifier):
        row = self.rows.get(identifier)
        return TranscriptionJob(**row) if row else None

    async def transition(self, identifier, expected, fields):
        row = self.rows.get(identifier)
        if not row or row['status'] not in expected:
            return False
        row.update(fields, updated_at=now())
        return True

    async def recover(self):
        pending = [k for k, row in self.rows.items() if row['status'] in ['queued', 'processing']]
        for identifier in pending:
            await self.transition(identifier, ['queued', 'processing'], dict(status='failed', error_code='interrupted'))
        return pending


class FakeASR:
    def __init__(self):
        self.error = None
        self.readiness_error = None
        self.calls = []
        self.delay = .02

    def check_ready(self):
        if self.readiness_error:
            raise AudioError(self.readiness_error)

    async def transcribe(self, upload, extension, pcm):
        self.calls.append((upload, extension))
        pcm.write_bytes(b'\0\0' * 10)
        await asyncio.sleep(self.delay)
        if self.error:
            raise AudioError(self.error)
        return TranscriptResult(**RESULT)

    async def close(self):
        pass


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, audio_temp_dir=tmp_path / 'uploads', audio_max_bytes=1024, audio_queue_size=0)
    repo, asr = MemoryJobs(), FakeASR()
    with TestClient(create_app(settings)) as api:
        manager = AudioWorker(repo, settings, asr)
        api.app.state.audio_worker = manager
        api.portal.call(manager.initialize)
        api.jobs, api.asr, api.manager = repo, asr, manager
        yield api


def upload(client, content=b'real decoding is mocked in this test', filename='../../private.wav'):
    return client.post(URL, files={'audio': (filename, content, 'audio/wav')})


def terminal(client, identifier):
    for _ in range(200):
        response = client.get(f'{URL}/{identifier}')
        assert response.status_code == 200
        row = response.json()
        if row['status'] in ['completed', 'failed']:
            return row
        time.sleep(.005)
    pytest.fail('Job failed to reach terminal state')


def test_success_original_segments_review_and_cleanup(client):
    response = upload(client)
    assert response.status_code == 202
    identifier = response.json()['transcription_id']
    assert response.headers['location'] == f'{URL}/{identifier}'
    row = terminal(client, identifier)
    assert row['status'] == 'completed'
    assert row['model'] == 'tiny.en' and row['language'] == 'en'
    assert row['original_transcript'] == RESULT['original_transcript']
    assert row['reviewed_text'] is None and row['review_status'] == 'needs_review'
    assert row['segments'] == RESULT['segments']
    assert row['processing_seconds'] == .02
    path, extension = client.asr.calls[0]
    assert path.parent.name == identifier and path.name != 'private.wav' and extension == 'wav'
    for _ in range(100):
        if not path.parent.exists(): break
        time.sleep(.005)
    assert not path.parent.exists()
    assert client.get('/api/v1/component-1/projects').status_code == 503  # No automatic project creation.


@pytest.mark.parametrize('content,name,status', [(b'', 'a.wav', 422), (b'x'*1025, 'a.mp3', 413), (b'x', 'a.flac', 415)])
def test_upload_validation(client, content, name, status):
    assert upload(client, content, name).status_code == status
    assert not client.jobs.rows and not client.asr.calls and client.manager.used == 0
    assert not list(client.manager.settings.audio_temp_dir.glob('*'))


def test_body_limit_before_multipart_parsing(client):
    response = client.post(URL, content=b'x' * 70000, headers={'content-type': 'multipart/form-data; boundary=test'})
    assert response.status_code == 413
    assert not client.jobs.rows


def test_streamed_body_limit_without_content_length(client):
    from intelise_c1.api.transcriptions import UploadBodyLimit
    async def check():
        messages = []
        async def receive(): return {'type': 'http.request', 'body': b'x' * 70000, 'more_body': False}
        async def send(message): messages.append(message)
        async def application(scope, receive, send):
            with pytest.raises(ValueError): await receive()
            await send({'type': 'http.response.start', 'status': 400, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'bad'})
        scope = {'type': 'http', 'method': 'POST', 'path': URL, 'headers': []}
        await UploadBodyLimit(application, 1024)(scope, receive, send)
        assert messages[0]['status'] == 413
        assert len([m for m in messages if m['type'] == 'http.response.start']) == 1
    asyncio.run(check())


def test_worker_saturation_and_responsive_health(client):
    client.asr.delay = .2
    first = upload(client)
    assert first.status_code == 202
    assert upload(client).status_code == 429
    start = time.monotonic()
    assert client.get('/api/v1/component-1/health').status_code == 200
    assert time.monotonic() - start < .15
    assert terminal(client, first.json()['transcription_id'])['status'] == 'completed'


@pytest.mark.parametrize('code', ['invalid_audio', 'audio_too_long', 'decode_timeout', 'transcription_timeout', 'transcription_failed'])
def test_failed_job_has_no_fake_transcript_and_cleans_files(client, code):
    client.asr.error = code
    response = upload(client)
    identifier = response.json()['transcription_id']
    row = terminal(client, identifier)
    assert row['status'] == 'failed' and row['error_code'] == code
    assert row['original_transcript'] is None and row['segments'] == []
    assert len(client.asr.calls) == 1  # No generation retry.
    for _ in range(100):
        if client.manager.used == 0: break
        time.sleep(.005)
    assert client.manager.used == 0
    assert not (client.manager.settings.audio_temp_dir / identifier).exists()


@pytest.mark.parametrize('code', ['missing_runtime', 'missing_model', 'missing_ffmpeg'])
def test_missing_dependencies_do_not_break_health_or_get(client, code):
    client.asr.readiness_error = code
    assert upload(client).status_code == 503
    assert client.get('/api/v1/component-1/health').status_code == 200
    assert client.get(f'{URL}/{uuid4()}').status_code == 404
    assert not client.jobs.rows


def test_db_failure_upload_is_cleaned_and_sanitized(client):
    client.jobs.create = AsyncMock(side_effect=PyMongoError('secret and private text'))
    response = upload(client)
    assert response.status_code == 503
    assert 'secret' not in response.text and 'private text' not in response.text
    assert client.manager.used == 0 and not client.asr.calls
    assert not list(client.manager.settings.audio_temp_dir.glob('*'))


def test_recovery_marks_interrupted_and_preserves_completed(tmp_path):
    async def check():
        repo = MemoryJobs()
        settings = Settings(_env_file=None, audio_temp_dir=tmp_path)
        pending = str(uuid4())
        completed = str(uuid4())
        for identifier, status in [(pending, 'processing'), (completed, 'completed')]:
            await repo.create(TranscriptionJob(transcription_id=identifier, model='tiny.en', status=status,
                                             upload_bytes=1, created_at=now(), updated_at=now()))
        original = dict(repo.rows[completed])
        (tmp_path / pending).mkdir()
        (tmp_path / pending / 'owned.wav').write_bytes(b'audio')
        manager = AudioWorker(repo, settings, FakeASR())
        await manager.initialize()
        assert repo.rows[pending]['status'] == 'failed'
        assert repo.rows[pending]['error_code'] == 'interrupted'
        assert repo.rows[completed] == original
        assert not (tmp_path / pending).exists()
        await manager.stop()
    asyncio.run(check())


def test_runtime_timeout_closes_process_without_retry(tmp_path):
    async def check():
        settings = Settings(_env_file=None, audio_processing_timeout_seconds=1)
        runtime = WhisperProcess(settings)
        runtime.check_ready = lambda: None
        async def delayed(): await asyncio.sleep(2)
        runtime.process = SimpleNamespace(returncode=None, stdin=SimpleNamespace(write=lambda b: None, drain=AsyncMock()),
                                          stdout=SimpleNamespace(readline=delayed))
        runtime.close = AsyncMock()
        with pytest.raises(AudioError, match='no automatic retry'):
            await runtime.transcribe(tmp_path / 'upload.wav', 'wav', tmp_path / 'pcm')
        runtime.close.assert_awaited_once()
    asyncio.run(check())


@pytest.mark.parametrize('output,code', [(b'not json\n', 'transcription_failed'), (b'{}\n', 'transcription_failed'),
                                       (json.dumps({'error':'invalid_audio'}).encode()+b'\n', 'invalid_audio')])
def test_invalid_runtime_protocol(tmp_path, output, code):
    async def check():
        runtime = WhisperProcess(Settings(_env_file=None))
        runtime.check_ready = lambda: None
        runtime.process = SimpleNamespace(returncode=None, stdin=SimpleNamespace(write=lambda b: None, drain=AsyncMock()),
                                          stdout=SimpleNamespace(readline=AsyncMock(return_value=output)))
        runtime.close = AsyncMock()
        with pytest.raises(AudioError) as error:
            await runtime.transcribe(tmp_path/'upload.wav', 'wav', tmp_path/'pcm')
        assert error.value.code == code
    asyncio.run(check())


@pytest.mark.parametrize('failure,code', [(subprocess.TimeoutExpired('ffmpeg', 1), 'decode_timeout'),
                                       (subprocess.CalledProcessError(1, 'ffmpeg'), 'invalid_audio')])
def test_decoder_errors_bounded_and_sanitized(tmp_path, monkeypatch, failure, code):
    def run(*args, **kwargs):
        assert kwargs['timeout'] == 1
        assert '-protocol_whitelist' in args[0]
        raise failure
    monkeypatch.setattr(decoder.subprocess, 'run', run)
    with pytest.raises(decoder.AudioFailure, match=code):
        decoder.decode('ffmpeg', 'not a real file', 'wav', tmp_path/'pcm', 120, 1)


def test_duration_uses_decoded_samples_and_overlong_rejected(tmp_path, monkeypatch):
    pcm = tmp_path/'pcm'
    def run(*args, **kwargs): pcm.write_bytes(b'\0\0' * 16001)
    monkeypatch.setattr(decoder.subprocess, 'run', run)
    with pytest.raises(decoder.AudioFailure, match='audio_too_long'):
        decoder.decode('ffmpeg', 'file', 'wav', pcm, 1, 1)
    assert decoder.decode('ffmpeg', 'file', 'wav', pcm, 2, 1) == 16001 / 16000


def test_silence_outcome_has_no_fabricated_transcript():
    result = TranscriptResult(audio_duration_seconds=1, processing_seconds=.1, original_transcript=None,
                              segments=[], outcome='silence_detected', asr_performed=False)
    assert result.original_transcript is None
    with pytest.raises(ValueError):
        TranscriptResult(**{**result.model_dump(), 'original_transcript': 'invented'})
