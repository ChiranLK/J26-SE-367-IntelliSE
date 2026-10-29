"""Real MongoDB, mocked ASR; recognition is checked separately by smoke script."""
import time

import pytest
from fastapi.testclient import TestClient

from intelise_c1.main import create_app
from test_projects_integration import database_settings  # Reuse isolated DB fixture.
from test_transcriptions import FakeASR, URL, terminal

pytestmark = pytest.mark.integration


def test_transcript_survives_restart_without_whisper(database_settings, tmp_path):
    settings = database_settings.model_copy(update={'audio_temp_dir': tmp_path / 'uploads'})
    with TestClient(create_app(settings)) as first:
        first.app.state.audio_worker.runtime = FakeASR()
        response = first.post(URL, files={'audio': ('sample.wav', b'mocked audio', 'audio/wav')})
        assert response.status_code == 202
        identifier = response.json()['transcription_id']
        saved = terminal(first, identifier)
        assert saved['status'] == 'completed'
        assert saved['original_transcript'] == ' Generated original. '
    assert not list(settings.audio_temp_dir.glob('*'))
    with TestClient(create_app(settings)) as restarted:
        response = restarted.get(f'{URL}/{identifier}')
        assert response.status_code == 200 and response.json() == saved
        assert restarted.post(URL, files={'audio': ('a.wav', b'audio')}).status_code == 503
        assert restarted.get('/api/v1/component-1/health').status_code == 200


def test_shutdown_interrupts_real_saved_processing_job(database_settings, tmp_path):
    settings = database_settings.model_copy(update={'audio_temp_dir': tmp_path / 'uploads'})
    with TestClient(create_app(settings)) as first:
        asr = FakeASR()
        asr.delay = 10
        first.app.state.audio_worker.runtime = asr
        response = first.post(URL, files={'audio': ('sample.wav', b'mocked audio')})
        assert response.status_code == 202
        identifier = response.json()['transcription_id']
        for _ in range(100):
            if first.get(f'{URL}/{identifier}').json()['status'] == 'processing': break
            time.sleep(.005)
        assert first.get(f'{URL}/{identifier}').json()['status'] == 'processing'
    with TestClient(create_app(settings)) as restarted:
        saved = restarted.get(f'{URL}/{identifier}').json()
        assert saved['status'] == 'failed' and saved['error_code'] == 'interrupted'
        assert saved['original_transcript'] is None
        assert not list(settings.audio_temp_dir.glob('*'))
