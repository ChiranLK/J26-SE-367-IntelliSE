# Single-requirement baseline tester — 15 October 2026

Implemented in `component-1/frontend` on `component-1-frontend`. No applicable
AGENTS.md was found. Existing project/audio/extraction/classification/health
behavior was retained; no backend files, dependencies, model artifacts or database
records were changed. No training, commits or pushes.

## Implementation

The existing public classification API accepts a saved project/extraction, not
an arbitrary sentence. A clearly scoped **development-only** Vite adapter lets
this diagnostic panel call the existing backend `LocalClassifier` and trusted
artifact loader without creating fake extraction records or changing that API.

`RequirementTester.jsx` accepts one requirement, shows FR / Functional requirement
or NFR / Non-functional requirement, model version and actual processing time.
It handles loading/errors, rejects blank/overlong input, guards duplicate clicks,
clears stale predictions after edits and aborts browser requests on unmount.
All text is rendered as plain text. No confidence/approval claim is made.

`POST /__local_model/classify` is served only by the Vite dev server. Server-only
`C1_TEST_PYTHON` and `C1_TEST_MODEL_DIR` can override preserved local defaults;
no credentials or local paths are sent to the browser. JSON input and same-origin
checks apply. One lazy Python process reuses the loaded model; concurrent checks
receive 429. Its 60-second timeout terminates the worker without retrying.
Worker/import/artifact errors return sanitized 503 responses with configuration
guidance. No source text or full traceback is logged. Workers are closed during
server shutdown; closing their stdin also ends their input loop.

The static production build disables the tester because browser assets cannot
execute this Python artifact. There is no public standalone inference endpoint.
No model binary is included in the production bundle. See README for setup.

## Verification

Commands from `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
C1_LIVE_MODEL_TEST=1 npm run test:browser
git diff --check
```

- **71 automated tests passed**, no skips. New client/middleware tests use mocked
  responses, and worker-lifecycle tests use a pipe fixture. These test behavior,
  not model accuracy. The local HTTP middleware test requires loopback binding.
- **ESLint passed**, zero warnings; production build passed, 33 modules,
  JS 284.30 kB / 85.40 kB gzip, CSS 17.72 kB / 4.35 kB gzip.
- **Existing mocked-API Chrome workflow passed**, 28.83 seconds: project creation,
  extraction, saved classifications, recovery, refresh and audio review/provenance.
- **Actual-model Chrome test passed**, 26.13 seconds. It used the preserved
  trusted TF-IDF/logistic-regression artifact, real Python and Chrome, with the
  project API deliberately unavailable. No Ollama, Whisper or MongoDB was involved.
- The unrelated opt-in live-audio browser test was skipped; ASR was not retested.
- Python worker syntax and `git diff --check` passed.

Actual final-run observations:

| Input | Actual label | Browser request-to-result elapsed |
| --- | --- | --- |
| The system shall allow customers to book appointments. | FR | 19.781 seconds, including initial model loading |
| Search results shall appear within two seconds. | NFR | 0.130 seconds, model reused |

Model identity: `tfidf-logistic-regression`, SHA-256 version
`b48d2a3a87e3669957a1c5374c8879cd84fc1fe232e002a1c50c9821cb693823`.
These measurements include browser overhead; the UI separately displays the
worker's measured processing time. They are not a latency benchmark or accuracy
estimate. Initial loading time varies.

The live test checked blank input without a POST, two actual predictions,
duplicate-click protection, exact input/result association, valid model identity,
clearing old output on editing, model reuse and mobile width without overflow.
A real mobile-layout screenshot was inspected. Temporary browser servers and
profiles were cleaned up; the optional normal development server is separate.

The existing development server on `http://localhost:5173` was checked afterward:
updated App source returned HTTP 200 with the tester import, and the local model
endpoint returned HTTP 200 / NFR for the two-second search input, with the same
model version and 14.120 seconds processing including that server's initial load.
An attempted second dev server respected strictPort and exited because 5173 was
already in use; the existing server was left running and not replaced.

Initial verification caught and corrected an incorrect relative model path, a
browser assertion that matched the new model heading before saved classification
completed, and signal listeners that prevented temporary Vite processes exiting.
The final complete browser command exited successfully after these fixes.

## Limitations

The model always chooses FR or NFR, including for irrelevant input. Predictions
can be wrong and require review. Earlier held-out macro-F1 0.9041 reflects
within-corpus normalized-text evaluation, not project-separated evaluation and
not confidence in an individual result. This tester verifies inference and UI
behavior; it does not verify the saved-extraction/MongoDB application workflow.
