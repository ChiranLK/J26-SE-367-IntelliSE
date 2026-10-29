# Audio transcription verification

Historical transcription-only verification below. The backend worktree has since
moved into `.worktrees/component-1-backend` under the main repository. See
[reviewed-audio project verification](project-provenance-verification.md) for the
current durable startup path and provenance contract; the earlier temporary
source paths below describe the historical run only.

Verification performed locally on October 15, 2026. All implementation changes
are in the isolated `component-1-backend` worktree
`/private/tmp/intellise-c1-audio-backend`, based on `ab15712`. The original
checkout remains on `component-1-frontend`; its seven staged frontend files,
prior backend README edits and untracked work were preserved. No frontend/other
component files changed, and no commit, push or stash operation was performed.

## Preflight and dependencies

- No applicable `AGENTS.md` found. Root/backend README, config, source, locks,
  lifespan, persistence, classification loader and existing tests inspected.
- Host: Intel x86_64 macOS 14.6.1; Python 3.12.8.
- Original classifier env: NumPy 2.5.4, SciPy 1.18.1, scikit-learn 1.9.1,
  skops 0.16.0. No original Torch/Whisper/multipart/global FFmpeg/ffprobe.
- API verification copied the working env to
  `/private/tmp/intellise-c1-audio-api-env`, adding python-multipart 0.0.32 there
  only. Original env unchanged; its `pip check` passes.
- ASR installed separately in `/private/tmp/intellise-c1-whisper-env`:
  openai-whisper 20240930, Torch 2.2.2, NumPy 1.26.4, numba 0.60.0,
  llvmlite 0.43.0, tiktoken 0.9.0, imageio-ffmpeg 0.6.0; full resolved pins in
  `requirements-whisper.lock`. Imports and `pip check` pass on actual Python 3.12
  Intel hardware. Do not install this lock into the classifier venv.
- First source-build attempt exposed removed `pkg_resources` in newest
  setuptools. Pinned setuptools 80.9.0 / wheel 0.45.1 and no build isolation
  resolve that issue. Intel Torch 2.2.2 cannot share the classifier's NumPy 2.x;
  interpreter separation preserves the working classifier.
- Bundled executable: imageio-ffmpeg's `ffmpeg-macos-x86_64-v7.1`.
  Explicit preparation successfully encoded/decoded actual WAV, MP3 and M4A
  fixtures. FFmpeg demuxer/codec behavior, not file extension alone, was checked.
- Original baseline successfully reloaded through its configured artifact path
  with the unchanged original venv: model `tfidf-logistic-regression`, version
  `b48d2a3a87e3669957a1c5374c8879cd84fc1fe232e002a1c50c9821cb693823`.
  Standard booking/search fixture predictions were FR/NFR. This is a load check,
  not new classifier evaluation; within-corpus evaluation limitations remain.

## Implemented files

| Files under backend | Change |
| --- | --- |
| `src/intelise_c1/audio/runtime.py` | Explicit preparation/checksum/decoder checks; standalone lazy reusable CPU ASR process |
| `src/intelise_c1/audio/worker.py` | One bounded queue, subprocess timeout/termination, cleanup and recovery |
| `src/intelise_c1/api/transcriptions.py`, `transcription_schemas.py` | Multipart POST/GET, raw-body/file limits, validated jobs/results |
| `src/intelise_c1/repositories/transcriptions.py` | Real MongoDB jobs, guarded atomic transitions, interrupted-job recovery |
| `src/intelise_c1/api/router.py`, `main.py`, `core/config.py`, `core/database.py` | Route/middleware/settings/lifespan integration |
| `tests/test_transcriptions.py`, `test_transcriptions_integration.py` | Mocked ASR behavior and isolated real-MongoDB persistence tests |
| `scripts/smoke_transcription.py` | Actual ASR/HTTP/Mongo/health/restart check with metadata-only output |
| `pyproject.toml`, `requirements.lock`, `requirements-whisper.lock` | Verified multipart addition; separate pinned ASR environment |
| `.env.example`, `.gitignore`, `README.md`, `docs/audio-transcription.md`, `docs/transcriptions-openapi.json`, this report | Configuration, ignored assets, setup, API contract and evidence |

## Automated results

Initial existing suite: **193 passed, 6 skipped**, 62.71 seconds (real MongoDB
not enabled). New mocked transcription tests: **25 passed**, 3.07 seconds.
Full final backend suite with real local MongoDB: **226 passed**, 16.82 seconds,
no skips. Eight integration cases use UUID-named isolated databases and drop
only those databases. ASR/extraction/classification outputs in integration tests
are mocked; they establish persistence/state behavior, not model quality.
One pre-existing Starlette TestClient/httpx deprecation warning remains.

Covered: upload empty/type/byte/body-stream limits; generated safe filenames;
queued/processing/completed/failed state behavior; original whitespace/segments;
human-review separation; saturation/health; missing runtime/model/FFmpeg;
decode failures/timeouts; overlong decoded samples; transcription deadline with
one attempt; invalid worker protocol; sanitized DB errors; silence result
consistency; cleanup; recovery preserving completed jobs; real-MongoDB retrieval
after restart with model unavailable and graceful shutdown interruption.

All three environments pass `pip check`. `git diff --check` passes. No configured
backend lint tool exists. OpenAPI was generated from the actual app, and the
fragment preserves existing route contracts while adding the two requested routes.

## Actual ASR and persistence check

No local English sample was supplied. Used the public
[Whisper JFK test recording](https://github.com/openai/whisper/blob/main/tests/jfk.flac),
converted from FLAC to mono 16 kHz WAV with the verified bundled FFmpeg. No private
recordings, synthesized voice or mocked transcript were used in this check.

Explicit tiny.en preparation downloaded and verified the published checkpoint:
SHA-256 `d3dd57d32accea0b295c96e26691aa14d8822fac7d9d27d5dc00b4ca2826dd03`.
Python's initial download hit a certificate-trust error; system-trusted curl
fetched it and the same preparation command verified it. The first bounded curl
download reached 39,124,992 bytes before 180 seconds; an explicitly invoked
resume completed it. No API startup performed any download.

The first smoke invocation failed without a transcript: the verification script
resolved the ASR venv Python symlink to the global interpreter. Corrected it to
retain the absolute venv path. A new explicit verification invocation then passed.
The API never automatically retried the failed job. Both disposable databases
were removed by the verification script.

Actual successful run:

| Check | Measured result |
| --- | --- |
| Upload | multipart audio POST, HTTP 202, queued |
| Job ID | 668a97af-dda2-48ef-969a-1eb4d9a86076 (disposable test record, now removed) |
| Provider/model/device | pretrained Whisper tiny.en / CPU / fp16=False / English transcribe |
| Decoded duration | 11.0 seconds |
| Worker processing time | 4.281117510 seconds |
| Upload to completion | 4.562670102 seconds |
| Generated original | 105 characters, 2 timestamped segments; needs_review |
| Transcript SHA-256 | d9447b7d0f9a53f85ec4e2f98d6a918a79da391e3462b546b7f1912622ca2e70 |
| GET states observed | processing, completed; upload response was queued |
| Concurrent health | 66 HTTP 200 responses; maximum 0.048380298 seconds |
| Saturation | HTTP 429 with one processing slot occupied |
| Silent 1-second WAV | completed, silence_detected, ASR skipped, original null |
| 121-second WAV | failed, audio_too_long, original null |
| Corrupt MP3 | failed, invalid_audio, original null |
| 10,000,001-byte file | HTTP 413 |
| Real MongoDB | original/model fields read directly and matched GET; saved original never rewritten |
| Controlled restart | fresh server/client, Whisper disabled; GET HTTP 200, entire saved job identical |
| Cleanup | upload/decoded directories empty after server shutdown |
| Existing workflow | isolated project listing stayed empty; no automatic projects/extractions/classifications |

The full transcript was neither printed nor logged; only metadata/hash were
reported. Worker time includes decoding and first lazy model load, excluding
queue wait and pre-request process-import overhead. Assets were already prepared
and filesystem caches may be warm. One recording does not establish real-time
performance, ASR accuracy, completeness or relevance. No accuracy score is claimed.

## Exact commands used / next action

From `/private/tmp/intellise-c1-audio-backend/component-1/backend`:

```sh
PYTHONPATH=src /private/tmp/intellise-c1-audio-api-env/bin/python -m pytest tests/test_transcriptions.py -q --tb=short
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 PYTHONPATH=src \
  /private/tmp/intellise-c1-audio-api-env/bin/python -m pytest -q --tb=short
/private/tmp/intellise-c1-audio-api-env/bin/python -m pip check
/private/tmp/intellise-c1-whisper-env/bin/python -m pip check

/private/tmp/intellise-c1-whisper-env/bin/python src/intelise_c1/audio/runtime.py prepare \
  --model-dir /private/tmp/intellise-c1-whisper-models --model tiny.en

curl --fail --location --max-time 60 --output /private/tmp/intellise-c1-jfk.flac \
  https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac
/private/tmp/intellise-c1-whisper-env/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-x86_64-v7.1 \
  -nostdin -loglevel error -i /private/tmp/intellise-c1-jfk.flac -ac 1 -ar 16000 /private/tmp/intellise-c1-jfk.wav
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 PYTHONPATH=src \
  /private/tmp/intellise-c1-audio-api-env/bin/python scripts/smoke_transcription.py \
  --sample /private/tmp/intellise-c1-jfk.wav \
  --whisper-python /private/tmp/intellise-c1-whisper-env/bin/python \
  --model-dir /private/tmp/intellise-c1-whisper-models --model tiny.en
git diff --check
```

Next action: review the backend worktree, use the durable installation steps in
`audio-transcription.md` to prepare `.venv-whisper`/`models/whisper`, configure the
absolute venv interpreter path and model directory in that backend's ignored
`.env`, then explicitly run **one** backend instance. The existing server on
8001 was not restarted or reconfigured by this feature task; the smoke server
used an automatically allocated separate port. Existing client data remains
untouched. Temporary verification environments/models under /private/tmp are
not a durable installation. No frontend upload/review interface was added.

Review every transcript before manually submitting edited text to the existing
discussion workflow. Silence thresholds cannot eliminate ASR hallucinations.
Extraction evidence matching establishes traceability, not relevance/completeness;
the FR/NFR baseline's within-corpus evaluation still lacks genuine project-held-out
evidence. No result was promoted to client-approved status.
