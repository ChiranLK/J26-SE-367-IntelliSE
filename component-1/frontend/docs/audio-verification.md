# Audio upload and transcript review verification

Verified October 15, 2026 on `component-1-frontend`. No applicable AGENTS.md was
found. Root/frontend instructions, existing form/API/classification/health code,
dependency lock and actual backend schemas/OpenAPI were inspected. Existing
staged frontend work and unrelated backend/untracked changes were preserved.
No backend source files, dependency locks, commits, pushes or stashes changed.

## Contract findings and implementation

Audio contract inspected from the backend worktree's actual generated fragment:
`/private/tmp/intellise-c1-audio-backend/component-1/backend/docs/transcriptions-openapi.json`.
Verified again against OpenAPI from the separately running audio-enabled server
during the live check. POST is multipart field `audio`, returning 202 queued with
`transcription_id`; GET returns queued/processing/completed/failed and stored
original, segments, timing, model, language and review metadata.

The existing server on 127.0.0.1:8001 currently exposes only health/projects. Its
OpenAPI has no audio, extraction or classification routes. It was not stopped or
reconfigured. Source inspection and a separate audio-enabled server were used
instead. Its lack of feature routes remains a deployment blocker for that URL.

**Project provenance is a real contract gap.** Both inspected project schemas
accept only name/description/discussion_text and forbid additional fields.
Project responses contain no transcription reference; transcription reviewed_text
is reserved null, with no review/project-link write endpoint. The frontend
therefore never invents payload fields or hides provenance in descriptions.
After Use this transcript, it retains the job snapshot and reviewed discussion
locally and blocks project saving with a visible explanation. The original job
remains unchanged in MongoDB. A backend project/transcription review association
is required to enable this save path. Text-only saving retains its previous
contract and behavior. Explicitly clearing an audio discussion requires
confirmation, clears both discussion and pending association, and keeps name,
description and the backend job.

Implemented files:

| Frontend path | Change |
| --- | --- |
| `src/components/CreateProjectForm.jsx` | Paste/audio tabs, replacement confirmation, discussion copy, provenance guard |
| `src/components/AudioTranscription.jsx` | File selection, upload/job states, original and editable draft, manual refresh |
| `src/services/api.js` | Centralized multipart POST and validated job GET; existing JSON requests preserved |
| `src/services/transcriptionContracts.js` | File limits and exact job/result shape validation |
| `src/services/transcriptionPolling.js` | Sequential bounded GET polling, deadline/count cap and abort cleanup |
| `src/styles.css` | Tabs/audio review styles within existing layout |
| `tests/transcriptions.test.js`, `tests/transcription-fixture.js` | API, polling, validation and explicitly mocked ASR fixtures |
| `tests/browser-workflow.test.mjs` | Existing regression flow extended with audio; separate opt-in real-ASR browser check |
| `.env.example`, `README.md`, this report | Configuration notes, contract gap and reproduction instructions |

## Automated checks

From `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
npm run test:browser
```

- **49 unit/API tests passed**, including 14 new transcription cases.
- **ESLint passed**, zero warnings.
- **Production build passed**: 30 modules; JS 273.17 kB (82.93 kB gzip),
  CSS 16.41 kB (4.11 kB gzip).
- **Mocked browser workflow passed**, with the opt-in live test skipped by default.
  Existing project creation, extraction, saved classification, health, navigation,
  failure recovery, reload and mobile behavior still pass.
- `git diff --check` passed. No npm dependencies/lock changes required.

New checks exercise real multipart construction without a JSON Content-Type;
extension/empty/size validation; malformed/cross-job responses; queued/processing/
failed/completed/silence/empty-speech contracts; no POST retry; polling request
and time caps; in-flight and delayed cancellation; manual GET recovery; double
click submission guards; unchanged initial discussion; independent editable/original
text; replacement Keep/Replace paths; name/description preservation; repeated
refresh preserving edits; provenance guarding both button and submit handler;
explicit clear confirmation; status-error polling pause; terminal polling stop;
unmount cleanup; safe rendering of markup as text; mobile width without overflow.
No audio action automatically saved, extracted or classified anything.

The first browser launch was blocked by sandbox loopback binding; reran with
explicit execution approval. The first executed browser test then reached all
review checks but expected a removed fixture project at the unmount destination.
Corrected that assertion to expect the fixture's actual 404; the full rerun passed.
That failure was in the test expectation, not an ASR/model result.

Browser screenshots use mocked test text, not live transcript logging:
`$TMPDIR/intellise-c1-workspace-desktop.png`, `intellise-c1-workspace.png` and
`intellise-c1-workspace-audio-review.png`. The mobile audio review screenshot was
also visually inspected. Mocked tests establish UI behavior, not ASR accuracy.

## Actual browser → API → Whisper → MongoDB check

Used the existing prepared tiny.en checkpoint and the public Whisper JFK recording
from the backend task, converted to WAV. No new model download, synthetic speech
or mocked ASR was used. A separate backend process used the audio worktree's source,
the isolated API/Whisper interpreters and a UUID-named disposable real MongoDB
database. Its CORS allowed only the temporary frontend origin. The test launched
its own Vite/headless Chrome and selected the actual local WAV through the file
input, then clicked Transcribe audio. The existing 8001 process/client data were
left untouched.

Actual result:

| Check | Measured/observed result |
| --- | --- |
| Job ID | a77a3497-a40e-42e4-92dc-5fbb764869e8; disposable record, now removed |
| Model / language | tiny.en / en |
| Final job | completed, needs_review |
| Audio duration | 11 seconds |
| Actual backend processing time | **19.840503527 seconds** |
| Generated original | 105 characters, 2 segments; matched the initial editor exactly |
| Review edit + manual refresh | Edited draft preserved; original unchanged |
| Use action | Copied only the edited draft; name/description preserved |
| Project save | Disabled due to missing provenance contract |
| Health retry | Connected after explicit retry |
| Direct real-MongoDB check | One completed tiny.en job; nonempty original; reviewed_text null; needs_review |
| Automatic project/extraction/classification writes | Zero in all three collections |
| Cleanup | No upload files after shutdown; only generated test DB dropped |

The live browser test passed in 35.96 seconds including its browser/startup/UI
steps; total test-process duration including teardown was 54.17 seconds.
Neither duration is a real-time guarantee. Performance differed from the earlier
backend-only check; these are separate measured runs. Full live transcript/audio
contents were not printed or logged. One public recording does not establish
language accuracy, completeness, relevance or robustness to silence/noise.

## Reproduce the live check

Use a separately running audio-enabled backend and a disposable MongoDB database.
Follow the backend's existing audio preparation instructions; no download occurs
in frontend startup or tests. For example, from that backend directory:

```sh
# Use a new disposable database name for each verification; never a client DB.
MONGODB_URI=mongodb://127.0.0.1:27017 \
MONGODB_DATABASE=intellise_c1_audio_ui_test_REPLACE_WITH_UNIQUE_SUFFIX \
C1_CORS_ORIGINS='["http://127.0.0.1:18020"]' \
C1_WHISPER_PYTHON=/absolute/path/to/.venv-whisper/bin/python \
C1_WHISPER_MODEL=tiny.en C1_WHISPER_MODEL_DIR=/absolute/path/to/models/whisper \
  /absolute/path/to/api-venv/bin/python -m uvicorn intelise_c1.main:app \
  --host 127.0.0.1 --port 18021 --workers 1 --no-access-log
```

Then from `component-1/frontend`:

```sh
C1_LIVE_AUDIO_BASE_URL=http://127.0.0.1:18021 C1_LIVE_UI_PORT=18020 \
C1_LIVE_AUDIO_FILE=/absolute/path/to/short-english.wav \
  node --test --test-name-pattern='live audio' tests/browser-workflow.test.mjs
```

The actual local run used automatically allocated free ports and an external
temporary harness `/private/tmp/intellise-live-audio-ui-check.py` to launch/stop the
API, invoke exactly the opt-in Node test above, inspect the isolated MongoDB
collections and drop only its generated DB. The harness can be rerun locally
while its temporary environments/model/sample still exist:

```sh
/private/tmp/intellise-c1-audio-api-env/bin/python /private/tmp/intellise-live-audio-ui-check.py
```

The repository test command itself does not drop a database. Shut down the
disposable backend and remove only that test database after manual verification.
The frontend test leaves the transcription original untouched and saves no project.

## Remaining limitations and exact next action

Use the audio-enabled backend URL in `VITE_API_BASE_URL`, with matching CORS, to
enable upload/review locally. Port 8001 currently lacks these routes. Before
audio-derived projects can be saved, extend the backend project/review contract
to retain a validated transcription reference and reviewed-text association,
then wire that documented contract into the centralized frontend save request.
No backend changes were made in this task.

Local reviewed drafts/source snapshots are not persistent across navigation or
reload. The saved original can be retrieved by its job ID; this prototype has no
job-list, resumable upload, review-write or microphone recording UI. Polling can
pause before a long queue/model finishes; use manual status refresh. Unknown
upload outcomes without IDs cannot be safely reconciled under the current API.
All generated text needs human review; neither silence detection nor exact source
quotes prove relevance/completeness. Existing TF-IDF/logistic classifier metrics
remain within-corpus results, not individual prediction confidence or project-held-out
performance. No BERT model or new evaluation claim was introduced.
