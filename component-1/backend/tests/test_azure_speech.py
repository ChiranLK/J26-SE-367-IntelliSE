"""Mocked Azure HTTP tests: no cloud credentials, billing or ASR accuracy claim."""
import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from intelise_c1.audio.azure import AzureSpeech
from intelise_c1.audio.worker import AudioError, AudioWorker, WhisperProcess
from intelise_c1.core.config import Settings
from intelise_c1.main import create_app
from intelise_c1.services.transcription_provenance import build_provenance
from test_project_provenance import completed
from test_transcriptions import MemoryJobs, terminal

SECRET = 'test-only-secret-123456789'
VALID = {'durationMilliseconds': 1000, 'combinedPhrases': [{'text': ' Generated original. '}],
         'phrases': [{'offsetMilliseconds': 0, 'durationMilliseconds': 1000, 'text': ' Generated original. '}]}


def settings(tmp_path):
    executable = tmp_path / 'ffmpeg'
    executable.write_text('test-only placeholder, decoder is mocked')
    executable.chmod(0o700)
    return Settings(_env_file=None, transcription_provider='azure', azure_speech_key=SECRET,
                    audio_ffmpeg_path=executable, audio_temp_dir=tmp_path / 'uploads')


def runtime(tmp_path, handler):
    value = AzureSpeech(settings(tmp_path), transport=httpx.MockTransport(handler))
    value.decode = AsyncMock(return_value={'duration': 1, 'silent': False})
    (tmp_path / 'decoded.wav').write_bytes(b'test-only mocked decoded audio')
    return value


def transcribe(value, tmp_path):
    return asyncio.run(value.transcribe(tmp_path / 'upload.wav', 'wav', tmp_path / 'decoded.pcm'))


def test_success_exact_original_timestamps_and_single_request(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.path == '/speechtotext/transcriptions:transcribe'
        assert request.url.params['api-version'] == '2025-10-15'
        assert request.headers['Ocp-Apim-Subscription-Key'] == SECRET
        assert b'audio.wav' in request.content and b'en-US' in request.content
        return httpx.Response(200, json=VALID)
    value = runtime(tmp_path, handler)
    result = transcribe(value, tmp_path)
    assert result.original_transcript == ' Generated original. '
    assert result.segments[0].start == 0 and result.segments[0].end == 1
    assert result.outcome == 'review_required' and result.asr_performed
    assert len(calls) == 1


@pytest.mark.parametrize('status,code', [(401,'azure_authentication'),(403,'azure_authentication'),
    (429,'azure_quota'),(503,'azure_unavailable'),(400,'azure_request_failed'),(302,'azure_request_failed')])
def test_errors_sanitized_without_retry_redirect_or_fallback(tmp_path, status, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=SECRET + ' full private discussion', headers={'Location':'https://untrusted.example'})
    value = runtime(tmp_path, handler)
    with pytest.raises(AudioError) as error:
        transcribe(value, tmp_path)
    assert error.value.code == code and SECRET not in str(error.value) and 'private discussion' not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize('exception,code', [(httpx.ReadTimeout,'transcription_timeout'),(httpx.ConnectError,'azure_unavailable')])
def test_network_errors_no_retry(tmp_path, exception, code):
    calls=[]
    def handler(request):
        calls.append(request)
        raise exception(SECRET, request=request)
    value=runtime(tmp_path,handler)
    with pytest.raises(AudioError) as error: transcribe(value,tmp_path)
    assert error.value.code==code and SECRET not in str(error.value) and len(calls)==1


@pytest.mark.parametrize('data', [{}, {**VALID,'combinedPhrases':'bad'}, {**VALID,'durationMilliseconds':9000},
    {**VALID,'combinedPhrases':[{'text':'a'},{'text':'b'}]}, {**VALID,'combinedPhrases':[]},
    {**VALID,'phrases':[{'offsetMilliseconds':-100,'durationMilliseconds':1000,'text':'x'}]},
    {**VALID,'phrases':[{'offsetMilliseconds':0,'durationMilliseconds':9000,'text':'x'}]}])
def test_invalid_schema_duration_or_segments_fail(tmp_path,data):
    value=runtime(tmp_path,lambda request:httpx.Response(200,json=data))
    with pytest.raises(AudioError,match='incomplete or invalid'): transcribe(value,tmp_path)


def test_invalid_json_and_response_limit(tmp_path):
    for content in (b'{incomplete', b'x'*2_000_001):
        value=runtime(tmp_path,lambda request:httpx.Response(200,content=content))
        with pytest.raises(AudioError) as error: transcribe(value,tmp_path)
        assert error.value.code=='azure_invalid_response'


def test_empty_speech_and_silence_have_reviewable_outcomes(tmp_path):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'durationMilliseconds':1000,'combinedPhrases':[],'phrases':[]})
    value=runtime(tmp_path,handler)
    result=transcribe(value,tmp_path)
    assert result.original_transcript=='' and result.outcome=='no_intelligible_speech' and result.asr_performed
    value.decode.return_value={'duration':1,'silent':True}
    result=transcribe(value,tmp_path)
    assert result.original_transcript is None and result.outcome=='silence_detected' and not result.asr_performed
    assert len(calls)==1


def test_duration_failure_never_uploads_audio(tmp_path):
    value=runtime(tmp_path,lambda request:pytest.fail('Invalid local audio must not reach Azure'))
    value.decode.side_effect=AudioError('audio_too_long')
    with pytest.raises(AudioError) as error: transcribe(value,tmp_path)
    assert error.value.code=='audio_too_long'


def test_jobs_record_azure_identity_and_existing_whisper_records_still_load(tmp_path):
    config=settings(tmp_path)
    value=runtime(tmp_path,lambda request:httpx.Response(200,json=VALID))
    async def decode(upload,extension,pcm):
        pcm.with_suffix('.wav').write_bytes(b'mocked WAV')
        return {'duration':1,'silent':False}
    value.decode=decode
    repo=MemoryJobs()
    with TestClient(create_app(config)) as client:
        worker=AudioWorker(repo,config,value); client.app.state.audio_worker=worker
        client.portal.call(worker.initialize)
        response=client.post('/api/v1/component-1/transcriptions',files={'audio':('sample.wav',b'test')})
        assert response.status_code==202
        saved=terminal(client,response.json()['transcription_id'])
        assert saved['status']=='completed' and saved['provider']=='azure' and saved['model']=='azure-speech-fast'
        assert saved['api_version']=='2025-10-15' and saved['locale']=='en-US'
        assert client.get('/api/v1/component-1/health').status_code==200
        client.portal.call(worker.stop)
    assert not list(config.audio_temp_dir.iterdir())
    job=completed()
    assert job.provider=='whisper'
    azure=job.model_copy(update={'provider':'azure','model':'azure-speech-fast','api_version':'2025-10-15','locale':'en-US'})
    before=azure.model_dump()
    provenance=build_provenance(azure,azure.transcription_id,'Edited reviewed discussion.',azure.updated_at)
    assert provenance.provider=='azure' and provenance.api_version=='2025-10-15'
    assert provenance.original_transcript==azure.original_transcript and azure.model_dump()==before


def test_health_without_credentials_and_explicit_provider_selection(tmp_path):
    config=Settings(_env_file=None,transcription_provider='azure')
    with TestClient(create_app(config)) as client:
        assert client.get('/api/v1/component-1/health').status_code==200
    worker=AudioWorker(MemoryJobs(),config)
    assert isinstance(worker.runtime,AzureSpeech)
    with pytest.raises(AudioError) as error: worker.runtime.check_ready()
    assert error.value.code=='azure_not_configured'
    assert isinstance(AudioWorker(MemoryJobs(),Settings(_env_file=None)).runtime,WhisperProcess)
    assert SECRET not in repr(settings(tmp_path))
    assert Settings(_env_file=None,audio_ffmpeg_path='').audio_ffmpeg_path is None


@pytest.mark.parametrize('endpoint',['http://example.com','https://evil.example','https://a.cognitiveservices.azure.com@evil.example',
                                  'https://southeastasia.api.cognitive.microsoft.com/path','https://a.cognitiveservices.azure.com?key=secret'])
def test_endpoint_restrictions(endpoint):
    with pytest.raises(ValidationError): Settings(_env_file=None,azure_speech_endpoint=endpoint)


def test_secure_env_update_preserves_settings_and_backup(tmp_path):
    spec=importlib.util.spec_from_file_location('configure',Path(__file__).parents[1]/'scripts/configure_azure_speech.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    env=tmp_path/'.env'; env.write_text('# keep me\nMONGODB_DATABASE=keep\nC1_CLASSIFIER_MODEL_DIR=keep-model\nC1_AZURE_SPEECH_KEY=old\nC1_AZURE_SPEECH_KEY=duplicate\n')
    original=env.read_bytes()
    module.update_env(env,{'C1_AZURE_SPEECH_KEY':SECRET,'C1_TRANSCRIPTION_PROVIDER':'azure'})
    assert env.stat().st_mode & 0o777==0o600
    assert '# keep me' in env.read_text() and 'C1_CLASSIFIER_MODEL_DIR=keep-model' in env.read_text()
    assert env.read_text().count('C1_AZURE_SPEECH_KEY=')==1
    backup=list(tmp_path.glob('.env.backup-*'))[0]
    assert backup.read_bytes()==original and backup.stat().st_mode & 0o777==0o600
