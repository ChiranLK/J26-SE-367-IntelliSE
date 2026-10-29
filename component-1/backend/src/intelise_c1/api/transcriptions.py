"""Bounded uploads; generated originals stay separate from reviewed discussions."""
from pathlib import Path
import tempfile
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from starlette.responses import JSONResponse
from pymongo.errors import PyMongoError

from intelise_c1.api.transcription_schemas import JobAccepted, TranscriptionJob
from intelise_c1.audio.worker import AudioError
from intelise_c1.repositories.transcriptions import now

transcriptions_router = APIRouter(prefix='/transcriptions', tags=['transcriptions'])


class UploadBodyLimit:
    """Reject oversized multipart bodies BEFORE Starlette can spool unbounded data."""
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or scope['path'].rstrip('/') != '/api/v1/component-1/transcriptions':
            return await self.app(scope, receive, send)
        maximum = self.maximum + 65536  # Bounded multipart envelope overhead.
        async def reject():
            await JSONResponse({'detail': 'Audio upload exceeds the configured byte limit.'}, status_code=413)(scope, receive, send)
        headers = dict(scope['headers'])
        try:
            if int(headers.get(b'content-length', b'0')) > maximum:
                return await reject()
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)(scope, receive, send)
        count, oversized, replaced = 0, False, False
        async def bounded_receive():
            nonlocal count, oversized
            message = await receive()
            count += len(message.get('body', b''))
            if count > maximum:
                oversized = True
                raise ValueError('Upload body limit exceeded')
            return message
        async def bounded_send(message):
            nonlocal replaced
            if oversized:
                if not replaced:
                    replaced = True
                    await reject()
            else:
                await send(message)
        await self.app(scope, bounded_receive, bounded_send)


def worker(request):
    value = getattr(request.app.state, 'audio_worker', None)
    if value is None:
        raise HTTPException(503, 'Transcription persistence is unavailable. Check MongoDB configuration and availability.')
    return value


@transcriptions_router.post('', response_model=JobAccepted, status_code=202)
async def create(request: Request, response: Response, audio: Annotated[UploadFile, File(description='WAV, MP3 or M4A audio, subject to configured byte/duration limits.')]):
    manager = worker(request)
    await manager.initialize()
    try:
        manager.runtime.check_ready()
    except AudioError as error:
        await audio.close()
        raise HTTPException(503, str(error)) from None
    extension = Path(audio.filename or '').suffix.lower().removeprefix('.')
    if extension not in {'wav', 'mp3', 'm4a'}:
        await audio.close()
        raise HTTPException(415, 'Only WAV, MP3 and M4A uploads are supported.')
    if not manager.reserve():
        await audio.close()
        raise HTTPException(429, 'Transcription worker is saturated. Wait for an existing job to finish.')
    identifier = str(uuid4())
    queued = False
    base = manager.settings.audio_temp_dir.resolve()
    directory = base / identifier
    try:
        directory.mkdir(parents=True, mode=0o700)
        size = 0
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.' + extension, delete=False) as output:
            upload = Path(output.name)
            while chunk := await audio.read(65536):
                size += len(chunk)
                if size > manager.settings.audio_max_bytes:
                    raise HTTPException(413, 'Audio upload exceeds the configured byte limit.')
                # Upload writes are small/bounded; heavy decode/ASR never executes in this loop.
                output.write(chunk)
        if not size:
            raise HTTPException(422, 'Audio upload is empty.')
        timestamp = now()
        is_azure = manager.settings.transcription_provider == 'azure'
        job = TranscriptionJob(transcription_id=identifier, status='queued',
                               model='azure-speech-fast' if is_azure else manager.settings.whisper_model,
                               provider=manager.settings.transcription_provider,
                               api_version=manager.settings.azure_speech_api_version if is_azure else None,
                               locale=manager.settings.azure_speech_locale if is_azure else None,
                               created_at=timestamp, updated_at=timestamp, upload_bytes=size)
        await manager.repository.create(job)
        manager.submit(identifier, upload, extension)
        queued = True
        response.headers['Location'] = f'/api/v1/component-1/transcriptions/{identifier}'
        return JobAccepted(transcription_id=identifier)
    except PyMongoError:
        # A write can have an ambiguous outcome. Recovery fails any orphaned
        # queued record on the next request after live jobs have drained.
        manager.initialized = False
        raise
    finally:
        await audio.close()
        if not queued:
            await manager.cleanup(identifier)
            manager.release()


@transcriptions_router.get('/{transcription_id}', response_model=TranscriptionJob)
async def get(transcription_id: UUID, request: Request):
    manager = worker(request)
    await manager.initialize()
    job = await manager.repository.get(str(transcription_id))
    if job is None:
        raise HTTPException(404, 'Transcription not found.')
    return job
