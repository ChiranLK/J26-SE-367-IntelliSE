# Audio-derived project saving verification

Verified October 15, 2026 on component-1-frontend. Inspected repository instructions
(no applicable AGENTS.md), current form/detail/API code, locks, the live 8001
OpenAPI, and the durable backend's generated project-provenance OpenAPI/schema.
No backend source files, dependency locks, commits, pushes or stashes changed.
Existing unrelated backend README/research changes remain untouched.

## Contract inspection and behavior

The existing server on 127.0.0.1:8001 still exposes only project/health routes;
ProjectCreate has no transcription_id. That server correctly keeps the audio
save block. It was not restarted/reconfigured. A separately launched server using
the durable component-1-backend checkout's normal entry point exposed the new
contract and was used for the real browser check.

Required contract: optional UUID transcription_id on project creation; read-only
transcription_provenance on POST 201 and GET detail, with version
c1-transcription-provenance-v1, user_reviewed, source/model/language, original
ASR text, original/reviewed SHA-256 hashes, segments and timestamps. Discovery
resolves local refs/nullable schemas from the configured server's OpenAPI.

The form checks capability on mount and again before each audio-derived save.
Unavailable/older schemas block the button and submit handler; a downgrade found
at preflight prevents a POST. Manual discovery retry preserves the draft/source.
Text-only creation remains independent of capability discovery. Save submits only
name, description, reviewed discussion_text and transcription_id; client model,
hash, original or review metadata is not submitted. A reference error never
causes a text-only retry or drops the association.

Successful audio-save responses must retain the requested source ID and submitted
discussion. All full project responses with provenance are structurally validated,
and Web Crypto recomputes both UTF-8 SHA-256 hashes. Invalid/missing source data
is an error rather than a silent text-only success. A malformed POST acknowledgement
is marked uncertain because the write may already have happened. Reopened details
display reviewed text and the saved original/metadata separately, including model,
language, source/review dates, duration/time, segments, hashes and version.
User-reviewed is not independently verified; hashes establish byte traceability.

## Files changed

| Frontend file | Purpose |
| --- | --- |
| `src/services/projectProvenance.js` | OpenAPI capability detection; v1 structure and SHA-256 verification |
| `src/services/api.js` | Central OpenAPI access, guarded audio save and validated project retrieval |
| `src/services/contracts.js` | Validate optional saved provenance while accepting legacy text-only records |
| `src/components/CreateProjectForm.jsx` | Conditional save guard, explicit reference submission, retained drafts and capability retry |
| `src/components/AudioTranscription.jsx` | Correct save guidance based on confirmed backend support |
| `src/components/ProjectDetail.jsx`, `ProjectSource.jsx` | Separate reviewed discussion and persisted original/source information |
| `tests/projectProvenance.test.js`, `project-provenance-fixture.js` | Capability/save/error/hash and compatibility regressions |
| `tests/browser-workflow.test.mjs` | Save/reload/reopen, reference errors and backend downgrade; real opt-in browser flow |
| README, historical audio-report notice and this report | Current contract, commands and evidence |

## Automated verification

From component-1/frontend:

```sh
npm test
npm run lint
npm run build
npm run test:browser
```

- **62 unit/API tests passed**, including 13 new provenance cases.
- **ESLint passed**, zero warnings.
- **Production build passed**: 32 modules, JS 280.17 kB (84.49 kB gzip),
  CSS 16.41 kB (4.11 kB gzip). No new dependencies/lock changes.
- **Mocked browser workflow passed**, 26.66 seconds for its test body; default
  live check skipped unless explicitly configured. Existing project, extraction,
  classification, health, recovery and navigation behavior passed.
- `git diff --check` passed.

New automated cases cover current/older/incomplete OpenAPI, deployment-root URLs,
minimal save payloads, unavailable discovery, rejected 404/409/422 references,
no POST retry, missing/cross-job provenance acknowledgements, corrupt hashes,
Unicode/CRLF API preservation, unchanged text-only creation and invalid versions.
Browser checks retain the original upload/review states and replace/keep/clear
confirmations, exercise backend downgrade after initial discovery, retry capability
discovery, retain drafts/IDs after a 409, prevent double-click saves, and retrieve
source details after page refresh and project-list reopen without new POSTs.
Markup from the mocked ASR original remains plain text.

The first browser run failed a test assumption that a textarea exposes CRLF.
Native textarea values normalize to LF. Corrected the assertion to compare the
actual edited draft; the rerun passed. API-level tests still verify exact UTF-8
hashing of supplied CRLF/Unicode strings. The original ASR remains separate and
is never normalized by review controls.

## Real browser / ASR / MongoDB result

Reused the prepared tiny.en model and public 11-second Whisper JFK WAV from prior
verification. No model download, synthetic speech or mocked ASR was used. The
existing isolated UI harness now starts the durable backend using its dedicated
.venv and normal `python -m intelise_c1` entry point, with a generated disposable
MongoDB database, separate free ports, matching CORS and a dedicated temp root.
It inspects the actual running OpenAPI before invoking the browser test.

Actual sequence in Chrome:

1. Enter project name, description and existing discussion; select the real WAV.
2. Click Transcribe; wait for actual completed tiny.en output.
3. Edit the separate review draft; manual status refresh preserves edits.
4. Use transcript; explicitly confirm discussion replacement.
5. Save with transcription reference; inspect saved reviewed/source sections.
6. Refresh the document; retrieve the saved project/source.
7. Open a new form, then reopen the saved project from the list; verify source ID,
   reviewed discussion and health without re-transcribing or re-saving.

| Measured check | Actual result |
| --- | --- |
| Browser test | Passed, 17.80 seconds including startup/UI steps |
| Transcription ID | 15e792c1-ff29-45b8-b7f8-4b41e45671e6 |
| Project ID | 6ad086b54dc1f4c6d75c4c26 |
| Model / language | tiny.en / en |
| Audio duration | 11 seconds |
| Actual backend processing time | **10.076597756 seconds** |
| Generated original | 105 characters, 2 segments; matched the initial editor exactly |
| Direct MongoDB | One completed source job and one explicitly saved project |
| Source association | Project ID reference matched job; original text/model and both hashes verified |
| Reviewed discussion | Edited draft preserved independently of ASR original |
| Name / description | Preserved through use/save/retrieval |
| Source job | Original intact, reviewed_text null, needs_review; project snapshot user_reviewed |
| Automatic extraction / classification writes | Zero |
| Cleanup | Temporary audio removed; only generated database dropped |

The listed records were disposable and have been removed. The edited text is a
workflow test draft, not an accuracy claim about the speech. Full live transcripts
were not printed/logged; diagnostics contain IDs, sizes and timings only. This
measurement differs from previous runs and is not a real-time performance promise.

## Reproduce

Start the provenance-enabled backend from its own checkout/environment with
prepared ASR assets, a disposable MongoDB database and CORS allowing the test
frontend origin. For example, from the backend directory:

```sh
MONGODB_URI=mongodb://127.0.0.1:27017 \
MONGODB_DATABASE=intellise_c1_audio_ui_test_REPLACE_WITH_UNIQUE_SUFFIX \
C1_CORS_ORIGINS='["http://127.0.0.1:18020"]' \
C1_BACKEND_PORT=18021 \
C1_WHISPER_PYTHON=/absolute/path/to/.venv-whisper/bin/python \
C1_WHISPER_MODEL_DIR=/absolute/path/to/models/whisper \
  .venv/bin/python -m intelise_c1
```

Then from component-1/frontend:

```sh
C1_LIVE_AUDIO_BASE_URL=http://127.0.0.1:18021 C1_LIVE_UI_PORT=18020 \
C1_LIVE_AUDIO_FILE=/absolute/path/to/short-english.wav \
  node --test --test-name-pattern='live audio' tests/browser-workflow.test.mjs
```

This test creates a real job/project and does not drop the database itself. Stop
the disposable server and clean only that generated test database afterward.
The actual local run used the reused temporary harness, which handles startup,
MongoDB assertions and cleanup automatically while its local assets remain:

```sh
/private/tmp/intellise-c1-audio-api-env/bin/python /private/tmp/intellise-live-audio-ui-check.py
```

## Remaining limits / next action

Configure VITE_API_BASE_URL to the running provenance-enabled backend and restart
Vite/rebuild. The existing 8001 server still needs an explicit restart from the
durable backend checkout; the frontend safely blocks audio saving there meanwhile.
Web Crypto requires HTTPS or localhost for provenance verification. Unsaved review
drafts stay local and are lost on navigation; saved original/review/provenance is
retrieved from MongoDB through project detail. Unknown upload outcomes without
job IDs still cannot be reconciled by this prototype API. Audio language quality,
ASR completeness, extraction relevance and within-corpus classifier generalization
still require evaluation. Nothing is independently verified or client-approved
merely because the source hashes match.
