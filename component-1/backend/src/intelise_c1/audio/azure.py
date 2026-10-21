"""Azure Fast Transcription through existing jobs. No SDK, retries or fallback."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import sys
from time import monotonic

import httpx

from intelise_c1.api.transcription_schemas import TranscriptResult
from intelise_c1.audio.worker import AudioError


class AzureSpeech:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport
        self.process = None

    def ffmpeg(self):
        explicit = self.settings.audio_ffmpeg_path
        return str(explicit) if explicit else shutil.which('ffmpeg')

    def check_ready(self):
        key = self.settings.azure_speech_key
        if not key or not key.get_secret_value().strip():
            raise AudioError('azure_not_configured')
        executable = self.ffmpeg()
        if not executable or not Path(executable).is_file() or not os.access(executable, os.X_OK):
            raise AudioError('missing_ffmpeg')

    async def close(self):
        process, self.process = self.process, None
        if process is not None:
            # The worker and its FFmpeg child share this owned process group.
            try:
                if os.name == 'posix': os.killpg(process.pid, signal.SIGKILL)
                elif process.returncode is None: process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

    async def decode(self, upload, extension, pcm):
        s = self.settings
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name('decode_upload.py')),
            '--ffmpeg', self.ffmpeg(), '--upload', str(upload), '--extension', extension,
            '--pcm', str(pcm), '--maximum-seconds', str(s.audio_max_seconds),
            '--timeout', str(s.audio_decode_timeout_seconds), '--silence-rms', str(s.audio_silence_rms),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            start_new_session=os.name == 'posix')
        try:
            async with asyncio.timeout(s.audio_decode_timeout_seconds + 5):
                output, _ = await self.process.communicate()
            data = json.loads(output)
            if 'error' in data:
                raise AudioError(data['error'])
            if not 0 < data['duration'] <= s.audio_max_seconds or not isinstance(data['silent'], bool):
                raise AudioError('invalid_audio')
            return data
        except TimeoutError:
            raise AudioError('decode_timeout') from None
        finally:
            await self.close()

    async def request(self, wav):
        s = self.settings
        # Reading at most the bounded decoded upload avoids sync file streaming
        # on the event loop. No original user path/name is sent to Azure.
        body = await asyncio.to_thread(wav.read_bytes)
        async with httpx.AsyncClient(timeout=s.audio_processing_timeout_seconds, transport=self.transport,
                                     follow_redirects=False, trust_env=False) as client:
            async with client.stream('POST', s.azure_speech_endpoint + '/speechtotext/transcriptions:transcribe',
                    params={'api-version': s.azure_speech_api_version},
                    headers={'Ocp-Apim-Subscription-Key': s.azure_speech_key.get_secret_value()},
                    files={'audio': ('audio.wav', body, 'audio/wav')},
                    data={'definition': json.dumps({'locales': [s.azure_speech_locale]})}) as response:
                if response.status_code in (401, 403): raise AudioError('azure_authentication')
                if response.status_code == 429: raise AudioError('azure_quota')
                if response.status_code >= 500: raise AudioError('azure_unavailable')
                if response.status_code != 200: raise AudioError('azure_request_failed')
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 2_000_000:
                        raise AudioError('azure_invalid_response')
                return json.loads(content)

    async def transcribe(self, upload, extension, pcm):
        self.check_ready()
        started = monotonic()
        try:
            async with asyncio.timeout(self.settings.audio_processing_timeout_seconds):
                decoded = await self.decode(upload, extension, pcm)
                duration = decoded['duration']
                if decoded['silent']:
                    return TranscriptResult(audio_duration_seconds=duration, processing_seconds=monotonic()-started,
                        original_transcript=None, segments=[], outcome='silence_detected', asr_performed=False)
                data = await self.request(pcm.with_suffix('.wav'))
                combined = data['combinedPhrases']
                phrases = data['phrases']
                # Audio sent is mono; multiple combined channels must not be
                # silently concatenated into a fabricated "original" transcript.
                if (not isinstance(combined, list) or len(combined) > 1 or not isinstance(phrases, list)
                        or not isinstance(data['durationMilliseconds'], (int, float))
                        or abs(data['durationMilliseconds'] / 1000 - duration) > .5):
                    raise AudioError('azure_invalid_response')
                text = combined[0]['text'] if combined else ''
                if not isinstance(text, str) or (not combined and phrases) or (not text.strip() and phrases):
                    raise AudioError('azure_invalid_response')
                segments = [{'start': p['offsetMilliseconds']/1000,
                             'end': (p['offsetMilliseconds']+p['durationMilliseconds'])/1000,
                             'text': p['text']} for p in phrases]
                return TranscriptResult(audio_duration_seconds=duration, processing_seconds=monotonic()-started,
                    original_transcript=text, segments=segments,
                    outcome='review_required' if text.strip() else 'no_intelligible_speech', asr_performed=True)
        except (TimeoutError, httpx.TimeoutException):
            raise AudioError('transcription_timeout') from None
        except httpx.RequestError:
            raise AudioError('azure_unavailable') from None
        except asyncio.CancelledError:
            await self.close()
            raise
        except AudioError:
            raise
        except Exception:
            raise AudioError('azure_invalid_response') from None
