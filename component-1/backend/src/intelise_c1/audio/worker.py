"""One bounded single-instance queue; CPU/decoder work lives in an isolated process."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
from time import monotonic
from uuid import UUID

from pymongo.errors import PyMongoError
from intelise_c1.api.transcription_schemas import TranscriptResult

ERRORS = {
    'azure_not_configured': 'Configure Azure Speech KEY 1 and FFmpeg using scripts/configure_azure_speech.py.',
    'azure_authentication': 'Azure rejected the credentials or access. Check KEY 1, resource endpoint and permissions.',
    'azure_quota': 'Azure Speech quota or capacity is unavailable. Check the Standard S0 resource and credit; no automatic retry occurred.',
    'azure_unavailable': 'Azure Speech could not be reached. Check your network and resource availability; no fallback occurred.',
    'azure_invalid_response': 'Azure returned an incomplete or invalid transcription response. No transcript was saved.',
    'azure_request_failed': 'Azure rejected the transcription request. Check resource region, API support and audio settings.',
    'missing_runtime': 'Configure C1_WHISPER_PYTHON to the prepared isolated Whisper environment.',
    'missing_model': 'Prepare the requested Whisper model explicitly before uploading audio.',
    'missing_ffmpeg': 'Prepared FFmpeg is unavailable. Prepare the ASR environment and verify its decoder.',
    'invalid_model_hash': 'Prepared model checksum failed. Prepare the trusted model again.',
    'invalid_audio': 'The file could not be decoded as the declared audio format.',
    'audio_too_long': 'Decoded audio exceeds the configured duration limit.',
    'decode_timeout': 'Audio decoding exceeded its time limit.',
    'transcription_timeout': 'Transcription exceeded its time limit; no automatic retry was attempted.',
    'transcription_failed': 'Transcription failed. Check the ASR environment and review the recording.',
    'interrupted': 'Transcription was interrupted. Upload again after reviewing this job.',
}


class AudioError(Exception):
    def __init__(self, code, duration=None, elapsed=None):
        self.code = code if code in ERRORS else 'transcription_failed'
        self.duration = duration
        self.elapsed = elapsed
        super().__init__(ERRORS[self.code])


class WhisperProcess:
    def __init__(self, settings):
        self.settings = settings
        self.process = None

    def check_ready(self):
        s = self.settings
        if s.whisper_python is None or not s.whisper_python.is_file():
            raise AudioError('missing_runtime')
        checkpoint = s.whisper_model_dir / f'{s.whisper_model}.pt'
        manifest = s.whisper_model_dir / f'{s.whisper_model}.json'
        try:
            data = json.loads(manifest.read_text())
            if data['model'] != s.whisper_model or not checkpoint.is_file() or checkpoint.stat().st_size == 0:
                raise AudioError('missing_model')
            if set(data['formats']) != {'wav', 'mp3', 'm4a'} or not Path(data['ffmpeg']).is_file():
                raise AudioError('missing_ffmpeg')
        except (OSError, ValueError, KeyError, TypeError):
            raise AudioError('missing_model') from None

    async def close(self):
        process, self.process = self.process, None
        if process is None:
            return
        if process.returncode is None:
            try:
                if os.name == 'posix': os.killpg(process.pid, signal.SIGTERM)
                else: process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                try:
                    if os.name == 'posix': os.killpg(process.pid, signal.SIGKILL)
                    else: process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        # Decoder children are in the same owned process group, including on cancellation.

    async def transcribe(self, upload, extension, pcm):
        self.check_ready()
        s = self.settings
        try:
            if self.process is None or self.process.returncode is not None:
                self.process = await asyncio.create_subprocess_exec(
                    str(s.whisper_python), str(Path(__file__).with_name('runtime.py')), 'serve',
                    '--model-dir', str(s.whisper_model_dir.resolve()), '--model', s.whisper_model,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, limit=1024 * 1024,
                    start_new_session=os.name == 'posix',
                )
            payload = {'upload': str(upload), 'extension': extension, 'pcm': str(pcm),
                       'duration_limit': s.audio_max_seconds, 'decode_timeout': s.audio_decode_timeout_seconds,
                       'silence_rms': s.audio_silence_rms}
            async with asyncio.timeout(s.audio_processing_timeout_seconds):
                self.process.stdin.write((json.dumps(payload) + '\n').encode())
                await self.process.stdin.drain()
                line = await self.process.stdout.readline()
            data = json.loads(line)
            if 'error' in data:
                raise AudioError(data['error'], data.get('audio_duration_seconds'), data.get('processing_seconds'))
            result = TranscriptResult.model_validate(data['result'])
            if result.audio_duration_seconds > s.audio_max_seconds:
                raise AudioError('audio_too_long')
            return result
        except TimeoutError:
            await self.close()
            raise AudioError('transcription_timeout') from None
        except asyncio.CancelledError:
            await self.close()
            raise
        except AudioError:
            raise
        except Exception:
            await self.close()
            raise AudioError('transcription_failed') from None


class AudioWorker:
    def __init__(self, repository, settings, runtime=None):
        self.repository = repository
        self.settings = settings
        if runtime is not None:
            self.runtime = runtime
        elif settings.transcription_provider == 'azure':
            from intelise_c1.audio.azure import AzureSpeech
            self.runtime = AzureSpeech(settings)
        else:
            self.runtime = WhisperProcess(settings)
        self.queue = asyncio.Queue(maxsize=settings.audio_queue_size + 1)
        self.used = 0
        self.initialized = False
        self.initializing = asyncio.Lock()
        self.task = None
        self.startup_task = None
        self.stopping = False

    def start(self):
        # No ASR import/download; DB failure must not prevent health startup.
        self.startup_task = asyncio.create_task(self._startup())

    async def _startup(self):
        try:
            await self.initialize()
        except PyMongoError:
            pass  # Retry recovery on an explicit subsequent API request, not generation.

    async def cleanup(self, identifier):
        try:
            canonical = str(UUID(identifier))
        except (ValueError, TypeError):
            return
        if canonical != identifier:
            return
        base = self.settings.audio_temp_dir.resolve()
        directory = base / identifier
        if directory.is_symlink() or directory.resolve().parent != base:
            return
        if directory.exists():
            await asyncio.to_thread(shutil.rmtree, directory)

    async def initialize(self):
        async with self.initializing:
            if not self.initialized:
                if self.used:
                    # Do not recover records belonging to this live worker. Wait
                    # until its pending jobs have reached terminal states.
                    raise PyMongoError('Transcription recovery is pending')
                interrupted = await self.repository.recover()
                for identifier in interrupted:
                    await self.cleanup(identifier)
                # Also remove uploads left by a crash before the DB insert.
                base = self.settings.audio_temp_dir
                if base.exists():
                    for directory in await asyncio.to_thread(lambda: list(base.iterdir())):
                        await self.cleanup(directory.name)
                self.initialized = True
            if self.task is None or self.task.done():
                self.task = asyncio.create_task(self._run())

    def reserve(self):
        if self.stopping or self.used >= self.settings.audio_queue_size + 1:
            return False
        self.used += 1
        return True

    def release(self):
        self.used -= 1

    def submit(self, identifier, upload, extension):
        self.queue.put_nowait((identifier, upload, extension))

    async def fail(self, identifier, code, elapsed=None, duration=None):
        await self.repository.transition(identifier, ['queued', 'processing'], {
            'status': 'failed', 'error_code': code, 'error_message': ERRORS[code],
            'processing_seconds': elapsed, 'audio_duration_seconds': duration,
        })

    async def _run(self):
        while True:
            identifier, upload, extension = await self.queue.get()
            started = monotonic()
            try:
                changed = await self.repository.transition(identifier, ['queued'], {'status': 'processing'})
                if changed:
                    result = await self.runtime.transcribe(upload, extension, upload.parent / 'decoded.pcm')
                    await self.repository.transition(identifier, ['processing'], {'status': 'completed', **result.model_dump()})
            except asyncio.CancelledError:
                await self.runtime.close()
                try: await self.fail(identifier, 'interrupted', monotonic() - started)
                except PyMongoError: self.initialized = False
                raise
            except AudioError as error:
                try: await self.fail(identifier, error.code, error.elapsed or monotonic() - started, error.duration)
                except PyMongoError: self.initialized = False
            except Exception:
                self.initialized = False  # Explicit API requests recover unsaved terminal states.
                try: await self.fail(identifier, 'transcription_failed', monotonic() - started)
                except PyMongoError: pass
            finally:
                try:
                    await self.cleanup(identifier)
                finally:
                    self.release()
                    self.queue.task_done()

    async def stop(self):
        self.stopping = True
        if self.startup_task:
            self.startup_task.cancel()
            await asyncio.gather(self.startup_task, return_exceptions=True)
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        await self.runtime.close()
        while not self.queue.empty():
            identifier, _, _ = self.queue.get_nowait()
            try: await self.fail(identifier, 'interrupted')
            except PyMongoError: pass
            await self.cleanup(identifier)
            self.release()
            self.queue.task_done()
