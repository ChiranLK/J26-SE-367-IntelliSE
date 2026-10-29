# Azure Speech: local key setup and existing audio workflow

This backend now supports explicit `whisper` (default) or `azure` transcription.
Azure uses Fast Transcription, REST API `2025-10-15`, with English locale `en-US`
by default. It uses the existing upload endpoint, queue, MongoDB jobs, polling,
human-review step and project provenance. It does not replace the classifier,
train a model or automatically extract/classify requirements. No new dependency
or lock change is required. Whisper stays available; failure never switches
providers. Ordinary startup performs no Azure request or model download.

Official API source:
https://learn.microsoft.com/en-us/azure/ai-services/speech-service/fast-transcription-create

## Configure KEY 1 without sharing it

The resource configured in the Azure portal is `intellise-c1-speech-chiran`,
resource group `intellise-component1-rg`, region `southeastasia`, Standard S0.
The user's resource endpoint is
`https://southeastasia.api.cognitive.microsoft.com/`. The resource group name is
not an API endpoint. S0 transcription consumes billed usage, potentially covered
by eligible student credit. Check the credit expiry and actual subscription.

From this backend worktree's `component-1/backend`:

```sh
.venv/bin/python scripts/configure_azure_speech.py
```

The command asks for KEY 1 through hidden terminal input. No characters appearing
while you paste is normal. Do not put the key in the command, chat, screenshots,
frontend code, or a `VITE_` variable. The command writes the backend's ignored
`.env` with owner-only permissions and makes an owner-only ignored backup if the
file already existed. It preserves all unrelated settings, including MongoDB,
classifier and Whisper settings, and selects Azure explicitly.

It records:

```dotenv
C1_TRANSCRIPTION_PROVIDER=azure
C1_AZURE_SPEECH_KEY=<entered privately by the setup command>
C1_AZURE_SPEECH_ENDPOINT=https://southeastasia.api.cognitive.microsoft.com
C1_AZURE_SPEECH_API_VERSION=2025-10-15
C1_AZURE_SPEECH_LOCALE=en-US
C1_AUDIO_FFMPEG_PATH=<local executable path>
```

Do not copy the placeholder as a real key. Configuration does not authenticate
with Azure or incur an audio-transcription request. The resource's actual key
must be validated through an explicit upload.

Azure still needs local FFmpeg to decode, verify duration and enforce the existing
upload policy before sending audio. It needs no Whisper model, Torch or Speech
SDK. The setup command uses an explicitly configured/system FFmpeg, or copies
the already installed bundled decoder into ignored `models/audio/ffmpeg` so it
does not depend on `/tmp` surviving. It never downloads or overwrites an existing
decoder. An explicitly configured missing decoder is an error. Existing default
limits remain WAV/MP3/M4A, 10 MB and 120 decoded seconds.

To check local configuration without sending credentials/audio:

```sh
.venv/bin/python scripts/configure_azure_speech.py --check
```

Restart the application explicitly. From the main repository root:

```sh
./start-component-1
```

Stop previously started backend/frontend terminals with Ctrl+C first if their
ports are occupied; the launcher does not replace existing processes. MongoDB
must be available (the documented launcher can start its local Docker service).
The launcher checks Azure locally when selected and no longer requires Whisper
assets for Azure. A valid local configuration is not proof that a key is accepted
by the cloud. The existing extraction-provider prerequisites still apply.

In the project form select Upload audio, choose an authorized recording, and
press Transcribe audio. Review/edit the result, then explicitly Use this
transcript and save the project. The original generated transcript remains
separate from reviewed discussion. No microphone recording was added.

## API and provenance compatibility

Routes stay:

- `POST /api/v1/component-1/transcriptions`: multipart `audio`, HTTP 202 job ID.
- `GET /api/v1/component-1/transcriptions/{id}`: queued/processing/completed/failed.
- Project creation accepts the existing optional `transcription_id` reference.

Jobs add `provider` (`whisper` or `azure`), `api_version` and `locale` fields.
Azure model identity is the service identifier `azure-speech-fast`; it is not a
claimed exact proprietary model-weight version. The requested REST API version
is retained separately. Public `language` remains `en` for the existing English
interface. Supported configured locales: en-US/en-GB/en-IN/en-AU. Accent accuracy
is not guaranteed. Historic records without the new fields default to Whisper.

Azure project provenance records the actual provider, service/API/locale,
unchanged Azure original, timestamps, segments and hashes of original/reviewed
text. These fields come from storage, never client-supplied model claims. The
existing frontend provenance validator accepts Azure explicitly and still
verifies text hashes. Original jobs and successful prior projects are unchanged.

The decoder runs in a bounded child process outside the async event loop.
Normalized mono WAV is sent by an async HTTP request; user filenames are not
sent as request filenames. Whole-job and decode deadlines apply. Responses are
size-bounded; required schema/duration/segment consistency is checked before
completion. Invalid/incomplete results never become fabricated transcripts.
Azure combined text is preserved as received; no silent spelling repair.
Empty speech output is reviewable; local silence can skip the cloud call. RMS
silence detection does not eliminate ASR hallucinations.

KEY 1 stays in backend settings as SecretStr and is sent only in the Azure HTTPS
header. Endpoints are restricted to supported Azure resource origins; redirects
are not followed. Response error bodies, credentials and full transcripts are
not logged. No request is automatically retried, and no provider fallback occurs.

Missing local key/decoder: upload HTTP 503. Accepted jobs can fail with sanitized
`azure_authentication` (401/403), `azure_quota` (429), `azure_unavailable`,
`azure_request_failed`, `azure_invalid_response` or `transcription_timeout`.
Existing upload size/type/duration, saturation, DB and restart-recovery behavior
remains in force. Health remains usable with Azure credentials absent.

## Verification and an explicit live check

Verified on 18 October 2026: 290 backend tests passed, 11 real-MongoDB tests
skipped because `TEST_MONGODB_URI` was unset; 83 frontend tests passed. Frontend
lint/build, backend dependency consistency and compilation passed. The frontend
suite required localhost access outside the sandbox for its existing test server.
One existing Starlette/httpx deprecation warning remains. Local `.env`, backup
names and the retained FFmpeg binary are ignored by Git. Existing staged work was
preserved; nothing was committed or pushed. KEY 1 was not available locally during
verification, so no live Azure transcription, billing or authentication check is
claimed. Configure the key privately before the explicit live check below.

Automated Azure HTTP tests mock the cloud. They do not establish key validity,
Azure latency or recognition accuracy. An actual local FFmpeg smoke decoded a
one-second generated PCM WAV, rejected overlong audio and rejected corrupt audio;
this is decoder testing, not an ASR quality result.

After configuring KEY 1 and starting real MongoDB, use an authorized English
recording for a billable isolated integration check:

```sh
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 \
.venv/bin/python scripts/smoke_azure_speech.py --sample /absolute/path/to/recording.wav
```

The script uses a generated disposable database and separate server/port,
verifies upload/job/health, real MongoDB persistence, edited-copy provenance and
retrieval after restart with credentials disabled. It cleans temporary files and
removes only its generated test database. It prints metadata/hash/timing, never
the full transcript or key. The smoke edit is not independent human review.
No cloud request has been made by configuration alone. Do not call mocked test
output an actual Azure result.

Automated commands:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
# From component-1/frontend:
npm test
npm run lint
npm run build
```

To switch back, explicitly set `C1_TRANSCRIPTION_PROVIDER=whisper`, retain its
prepared settings and restart. Never disable TLS verification or loosen model
dependency checks to make transcription work.
