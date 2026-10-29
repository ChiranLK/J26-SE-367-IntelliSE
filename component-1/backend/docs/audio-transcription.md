# Optional CPU audio transcription

This single-instance prototype uses pretrained Whisper, default `tiny.en`, on CPU
with `fp16=False`, English `language="en"` and `task="transcribe"`. There is no
training, translation, automatic project creation, extraction or classification.
Health, project and classifier code do not import Torch/Whisper. They work with
audio disabled; MongoDB/model availability still follows their existing contracts.

## Intel macOS preparation

The existing backend/classifier uses Python 3.12.8 with NumPy 2.5.4. Intel macOS
Torch wheels end at 2.2.x; the verified ASR environment uses Torch 2.2.2 and
NumPy 1.26.4. Installing these into the working classifier environment would
change its dependencies. Keep ASR in a separate interpreter. The standalone
worker protocol allows this without changing classifier dependencies.

Verified ASR pins are in `requirements-whisper.lock`, separate from
`requirements.lock` / `requirements-baseline.lock`. Python 3.12 Intel imports and
actual speech recognition were checked locally; this is not a cross-platform lock.
Whisper's upstream README primarily describes Python 3.8–3.11. If another Intel
machine cannot use the verified 3.12 wheels, prepare a separate Python 3.11 ASR
venv with compatible pins and run decoder/model smoke checks before configuring
its interpreter. Keep the API/classifier on its current Python 3.12 environment.

From `component-1/backend`:

```sh
# Existing API environment: only multipart is new; do not install the ASR lock here.
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip check

python3.12 -m venv .venv-whisper
.venv-whisper/bin/python -m pip install setuptools==80.9.0 wheel==0.45.1
.venv-whisper/bin/python -m pip install --no-build-isolation -r requirements-whisper.lock
.venv-whisper/bin/python -m pip check
.venv-whisper/bin/python -c 'import torch,numpy,whisper; print(torch.__version__,numpy.__version__)'

# EXPLICIT network/model preparation. Never runs in ordinary API startup.
.venv-whisper/bin/python src/intelise_c1/audio/runtime.py prepare \
  --model tiny.en --model-dir models/whisper
```

Pinned setuptools is needed because this Whisper source build imports
`pkg_resources`; newest setuptools removes it. Preparation checks real WAV/MP3/M4A
decoding with the Intel FFmpeg executable supplied by `imageio-ffmpeg`, then
downloads the chosen model, verifies its upstream SHA-256 and writes a local
manifest. A globally installed `ffmpeg`/`ffprobe` is not required. Model weights,
ASR venv and uploads are ignored by Git; uploads normally live outside the repo.
Model manifests/checkpoints are trusted local operator assets. Do not use unknown
checkpoints; this pinned Torch loader predates newer loading defaults.

If Python model download reports a certificate-trust error, configure the proper
trusted CA bundle for Python (`SSL_CERT_FILE`) or explicitly fetch the official
URL from `whisper._MODELS["tiny.en"]` using system-trusted curl into
`models/whisper/tiny.en.pt`, then run preparation again to verify SHA-256 and
decoders. Never disable TLS verification. A partially downloaded checkpoint
does not pass preparation/checksum validation.

Set these in the ignored `.env` (absolute interpreter path required; the model
directory is relative to backend working directory unless made absolute):

```dotenv
C1_WHISPER_PYTHON=/absolute/path/to/component-1/backend/.venv-whisper/bin/python
C1_WHISPER_MODEL=tiny.en
C1_WHISPER_MODEL_DIR=models/whisper
C1_AUDIO_TEMP_DIR=/private/tmp/intellise-c1-audio
```

Restart the backend explicitly after configuration. An empty interpreter setting
disables uploads. GET of saved jobs still works without any Whisper assets.

| Setting | Default | Bounds / purpose |
| --- | --- | --- |
| `C1_WHISPER_MODEL` | `tiny.en` | tiny/base/small/medium, optional .en; large/v1/v2/v3 or turbo, explicitly prepared |
| `C1_WHISPER_MODEL_DIR` | `models/whisper` | Prepared checkpoint and JSON manifest |
| `C1_AUDIO_TEMP_DIR` | OS temp directory + `intellise-c1-audio` | Dedicated to this single instance; example uses macOS /private/tmp |
| `C1_AUDIO_MAX_BYTES` | 10,000,000 | 1,024–100,000,000 bytes; decimal 10 MB |
| `C1_AUDIO_MAX_SECONDS` | 120 | 1–600 seconds, enforced on decoded samples |
| `C1_AUDIO_QUEUE_SIZE` | 2 | 0–10 waiting/upload slots in addition to one processing slot |
| `C1_AUDIO_DECODE_TIMEOUT_SECONDS` | 20 | 1–120 seconds |
| `C1_AUDIO_PROCESSING_TIMEOUT_SECONDS` | 300 | 1–1,800 seconds; whole worker request, including cold imports/decoding/load |
| `C1_AUDIO_SILENCE_RMS` | 0.0001 | 0–0.01 normalized PCM RMS; a review aid, not a hallucination guarantee |

## API contract

The generated contract is available at `/openapi.json` and `/docs`; the checked-in
[transcription OpenAPI fragment](transcriptions-openapi.json) records the new routes.

`POST /api/v1/component-1/transcriptions` accepts multipart field **audio**, not
JSON or a filesystem path. Supported filename extensions are `.wav`, `.mp3`,
`.m4a` (case insensitive); they select the decoder, and successful decoding is
still required. Container corruption, duration and decode failures are reported
as failed jobs after acceptance.

```sh
curl --fail-with-body -i -F 'audio=@/path/to/recording.wav' \
  http://127.0.0.1:8001/api/v1/component-1/transcriptions
```

**202** returns `{ "transcription_id": "<server UUID>", "status": "queued" }`
with `Location: /api/v1/component-1/transcriptions/<UUID>`. Poll
`GET /api/v1/component-1/transcriptions/{id}`; it returns **200** with:

| Field | Meaning |
| --- | --- |
| `transcription_id`, `status` | UUID; queued → processing → completed/failed |
| `model`, `language` | Requested prepared model; always en |
| `created_at`, `updated_at`, `upload_bytes` | UTC metadata and actual uploaded bytes |
| `audio_duration_seconds`, `processing_seconds` | Decoded sample duration; measured worker time, excluding queue wait |
| `original_transcript` | Exact generated original, including whitespace; null before ASR/on failure/skipped silence |
| `segments` | Available `{start, end, text}` in seconds; generated segment text is preserved |
| `reviewed_text` | Reserved nullable field; currently null. Project discussion stores each user's reviewed copy separately |
| `review_status` | Always needs_review |
| `outcome`, `asr_performed` | review_required, silence_detected or no_intelligible_speech; whether ASR actually ran |
| `error_code`, `error_message` | Sanitized actionable failure, otherwise null |

Queued/processing fields remain nullable until available. Failed jobs have no
fabricated transcript. Silence detected before ASR completes with
`outcome="silence_detected"`, `asr_performed=false`, original null and no segments.
An empty generated original is preserved and shown as `no_intelligible_speech`.
Neither outcome approves requirements. RMS cannot reliably detect speech or
eliminate ASR hallucinations; quiet speech, noise and music still need review.

**Human review:** retrieve the immutable original, review/edit a separate copy,
then explicitly submit reviewed text as project `discussion_text` **with the
completed job's `transcription_id`**. The backend snapshots the original and model
metadata from storage and hashes both text versions. See the
[reviewed-audio project contract](project-transcription-provenance.md).
That discussion remains separate from the generated audio original. Run
the existing saved-extraction and FR/NFR classification actions explicitly.
No audio review UI or review-write endpoint was added in this backend task.
The project association records `user_reviewed`, not independently verified;
the immutable job's own `reviewed_text`/`review_status` remain unchanged.

Upload errors: **413** oversized, **415** unsupported extension, **422** empty or
invalid multipart/UUID, **429** worker saturated, **503** missing prepared runtime,
model/FFmpeg or MongoDB. GET missing ID is **404**. Accepted jobs can fail with
invalid_audio, audio_too_long, decode_timeout, invalid_model_hash,
transcription_timeout, transcription_failed or interrupted. No failed generation
is automatically retried. Database errors use the existing sanitized 503 handler.

## Worker, persistence and recovery

Run exactly **one application instance / one Uvicorn worker**. One async queue
dispatches to a separate long-lived ASR process; model loading is lazy and the
loaded CPU model is reused. Imports, decoding, RMS and inference run outside the
async event loop. The decode process has a deadline, local-only protocols, one
audio stream, mono 16 kHz PCM and a duration cap plus 0.1 seconds used to detect
overlong audio. Actual decoded sample count enforces the final limit. Upload
bytes are checked during reads; middleware also bounds the raw multipart body
before parser spooling (file limit + 65,536 bytes of envelope overhead).

Jobs are stored in MongoDB `transcription_jobs`, with majority writes, unique
UUID index and guarded atomic state transitions. The queue is in memory; audio
uses generated filenames under UUID directories. Source names are never used
as paths or retained/logged. Temp files are deleted on terminal outcomes and
shutdown; timeout/cancellation terminates the owned process group first.
Restart recovery marks leftover queued/processing jobs failed/interrupted,
cleans owned UUID directories (including uploads from crashes before insert),
and preserves completed/failed jobs. DB outages can delay recovery until a
subsequent API request succeeds; health stays available. Use a dedicated temp
root; multiple instances sharing a database/root are unsupported and would
invalidate each other's pending jobs. No Celery/Redis, durable work queue,
automatic resume, horizontal scaling, idempotent uploads or real-time promise.

An ambiguous database write can persist despite HTTP 503; later recovery fails
orphan jobs rather than re-transcribing. The existing development API has no
authentication layer. Keep it local and configure record retention/access
before external deployment. Transcripts remain in MongoDB until an operator
applies their retention policy; raw audio is not retained after processing.

## Verification

From `component-1/backend`, using an API environment with multipart installed:

```sh
.venv/bin/python -m pytest tests/test_transcriptions.py -q
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 .venv/bin/python -m pytest -q
.venv/bin/python -m pip check
.venv-whisper/bin/python -m pip check

# Separate real ASR + HTTP + MongoDB + controlled-restart check.
# Uses only generated disposable DB, its own port/temp root; no downloads.
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 .venv/bin/python scripts/smoke_transcription.py \
  --sample /path/to/short-english.wav \
  --whisper-python /absolute/path/to/.venv-whisper/bin/python \
  --model-dir /absolute/path/to/models/whisper --model tiny.en
```

Automated ASR responses are mocked; real MongoDB tests separately verify
persistence, shutdown and retrieval. The smoke script prints only metadata,
timing and a transcript hash, launches/restarts its own server, verifies health
during processing, corrupt/oversized/overlong audio, silence, saturation and
cleanup, then drops only its generated database. It does not log full transcripts.
One speech sample does not establish ASR accuracy, completeness or domain
relevance; extraction and within-corpus classifier evaluation limitations remain.

Sources: [Whisper README](https://github.com/openai/whisper/blob/main/README.md),
[Torch 2.2.2 Intel wheels](https://pypi.org/project/torch/2.2.2/),
[Intel wheel discontinuation](https://discuss.pytorch.org/t/why-no-macosx-x86-64-build-after-torch-2-2-2-cp39-none-macosx_10_9_x86_64.whl/204546/2),
[bundled FFmpeg package](https://pypi.org/project/imageio-ffmpeg/0.6.0/).
