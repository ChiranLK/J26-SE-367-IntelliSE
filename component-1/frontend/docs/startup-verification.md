# One-command startup verification — 16 October 2026

Command: `./start-component-1` from the repository root. See
[local-startup.md](local-startup.md). No backend source/dependency locks, commits,
pushes, existing environment files or client records were changed.

## Checks performed

```sh
# Repository root:
./start-component-1 --help
./start-component-1 --check
git diff --check

# component-1/frontend:
npm test
python3 -m unittest discover -s scripts -p test_startup_checks.py
npm run lint
npm run build
C1_LIVE_MODEL_TEST=1 npm run test:browser
```

- **82 Node tests passed**, no skips; **2 Python path-regression tests passed**.
- ESLint passed with zero warnings; production build passed (35 modules).
- Final browser command: **2 passed, 1 skipped**, zero failures. The existing
  mocked project/extraction/classification/audio workflow passed in 33.67 seconds.
  The actual trained-artifact browser/CSV check passed in 25.07 seconds.
  The separately opt-in live-audio browser case was skipped; actual ASR was
  checked through the launcher below.
- `--help` works even from a different working directory. Final read-only
  `--check` passed: classifier, isolated Whisper/FFmpeg, real MongoDB and installed
  configured Ollama model. It did not start services or make generation requests.
- A controlled occupied-port fixture was preserved and startup refused it with
  an actionable message. The launcher does not terminate unrelated servers.
- `git diff --check` passed.

Automated fixture/protocol tests do not establish model accuracy. The real model
browser test classified 12 CSV rows, with 9 suggested labels matching and 3
mismatches (password reset, report export and availability). This illustrative
sample is not a benchmark. The trained artifact/model version remained
`b48d2a3a87e3669957a1c5374c8879cd84fc1fe232e002a1c50c9821cb693823`.

## Actual full-stack launch and audio persistence

Used separate ports and a dedicated disposable database, leaving existing
application instances/records untouched:

```sh
C1_BACKEND_PORT=18031 C1_FRONTEND_PORT=18032 \
MONGODB_DATABASE=intellise_c1_launcher_smoke_20261016_01 \
C1_AUDIO_TEMP_DIR=/private/tmp/intellise-c1-launcher-smoke-20261016-01 \
  ./start-component-1
```

The prepared local Python environments, trusted trained artifact, tiny.en
checkpoint/manifest, decoder and already installed Ollama model were reused.
No model download, dependency installation, training or LLM generation occurred.
The existing stopped MongoDB container was started and its named volume retained.

| Actual request/check | Result |
| --- | --- |
| Launcher startup | Full backend and Vite became ready on the isolated ports |
| OpenAPI | Audio, extraction, classification and project-provenance contracts present |
| GET project listing | HTTP 200 against real MongoDB |
| POST frontend `/__local_model/classify` | HTTP 200; appointment booking predicted FR using real artifact |
| POST `/transcriptions` | HTTP 202; real synthetic English WAV, 22.2216 seconds |
| GET transcription job | Completed tiny.en / English; 294 generated characters |
| Actual ASR processing | 14.759 seconds |
| Upload through explicit review/save check | 17.204 seconds total |
| Health during transcription | HTTP 200; maximum observed response 0.200 seconds |
| POST project with edited discussion and transcription ID | HTTP 201; backend-owned provenance returned |
| GET saved project | HTTP 200; matched creation response |
| Completed source job | Unchanged after project creation |
| Ctrl+C | Managed application processes stopped; both isolated ports released |
| Re-run same launcher command | Became ready again with the same disposable database |
| GET project/job after restart | Full project response hash identical; source job remained completed |
| Cleanup | Only generated database dropped; main database and MongoDB container retained |

This sample is synthetic speech, not a real client recording or an ASR quality
benchmark. The edited review was an explicit disposable workflow action, not an
independent semantic verification. No transcripts/discussions or credential-bearing
configuration values were logged. Baseline evaluation remains within-corpus,
not project-separated; readiness does not establish extraction accuracy.

## Corrections and remaining limits

Preflight caught virtual-environment path resolution following an interpreter
symlink to base Python. Paths now remain lexical, preserving isolated dependencies;
the regression tests cover this. A copied activation script is never used.
The existing Docker container needed more than the initial client deadline;
container start/create now allows a bounded 60 seconds. No volume reset occurred.
The OpenAPI readiness check uses the actual `transcription_id` route parameter.

An initial browser run passed UI assertions but failed while removing a profile
before Chrome had closed. Test teardown now closes/awaits Chrome first, then
removes only its generated profile with bounded retries. The final browser
command exited successfully. Earlier failed-test processes were cleaned up.

Current ASR assets still reside in temporary verification locations, as the
launcher explicitly reports. Configure durable ASR interpreter/model paths before
clearing /tmp. Missing dependencies/models stop startup with instructions; they
are not installed or substituted automatically. Use only one audio-enabled
application instance per database. Actual LLM extraction was not repeated, and
the known relevance/exact-source limitations remain unresolved.
