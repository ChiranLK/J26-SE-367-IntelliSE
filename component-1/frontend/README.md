# Component 01 frontend

React/Vite interface for IntelliSE's AI-Powered Intelligent Requirement
Engineering Agent for Agile Software Development, a fourth-year research project.
The supported workflow is **create project → open project → extract requirements
→ review candidates → classify the saved extraction**.

## Implemented behavior

- Accessible project creation with name, optional description, and original
  discussion; validates the backend's Unicode character limits and blank rules.
  Saving disables duplicate submission, retains inputs on failure, and opens the
  saved project on success.
- Saved-project list with names, `draft` status, local creation dates, loading,
  empty, failure/retry states, and offset-based Previous/Next pagination.
- Project details show the persisted discussion as plain text without rewriting.
  `#projects/<id>` in the URL restores the selected project on reload; browser
  Back/Forward works. Project creation is available at `#new-project`.
- Opening a project fetches its latest saved extraction using GET only.
  **Extraction POST runs only when the user presses “Extract requirements”.**
  Refresh, health checks, and navigation never initiate extraction.
- Latest results display run date/model/prompt/run ID, each candidate's ID, text,
  actor/action when provided, `unreviewed` status, quotes and character spans.
  A successful empty extraction is distinct from no extraction yet or failure.
- A failed extraction keeps the prior saved result visible. Network/timeouts,
  ambiguous server failures, and malformed successful POST responses require
  retrieval of the latest saved result before another extraction is enabled.
  A per-project uncertainty flag in session storage preserves that gate through
  navigation/reload in the same tab. It contains no discussion or credentials.
- The existing backend health behavior remains: automatic check on mount,
  exact contract validation, five-second timeout, cancellation of stale requests,
  connected/unavailable states, and manual retry. Health indicates connectivity
  only, not database/provider readiness.

Generated results are candidates requiring human review. Quotes establish source
traceability, not semantic correctness, completeness, accuracy, or client
approval. FR/NFR predictions are available in the saved classification panel. Editing/approval
persistence controls, quality scores, RAG and SRS generation remain future work.
All source and model text is rendered as text nodes, never raw HTML.

Optional **Upload audio → transcribe → review → use transcript** is available in
the project form. Audio-derived project saving is blocked by the provenance
contract gap described below; text-only creation retains its existing behavior.

## macOS setup and run commands

Use Node.js **22.12 or later in the 22.x series** and npm. The verified development
version is 22.14.0, pinned in `.nvmrc`. With nvm, run `nvm install` and `nvm use`
from this directory. From the repository root:

```sh
cd component-1/frontend
npm ci
cp .env.example .env
npm run dev
```

Open <http://localhost:5173>. Vite uses a fixed port with `strictPort`.
Stop with Ctrl+C. For later sessions use `npm run dev`. No new npm dependencies
are required; `package-lock.json` remains the reproducible dependency lockfile.

```sh
npm run lint
npm test
npm run build
npm run preview
```

Production preview: <http://localhost:4173>. `dist/` is ignored. Preview is for
local inspection, not production hosting.

## Backend setup and public environment

```dotenv
VITE_API_BASE_URL=http://localhost:8001
```

The configurable HTTP(S) base URL may include a deployment path and a trailing
slash, but must not contain credentials, query parameters, or a fragment. All
API calls append `/api/v1/component-1`. Restart Vite after editing `.env`;
production configuration is baked in at build time and needs a new build.
**Every `VITE_*` value is public. Provider API keys belong entirely in the backend.**

Run the completed backend from `component-1-backend` in a separate checkout or
existing worktree, following its README. Do not merge backend implementation into
this frontend branch. Backend requirements:

- Python 3.12 and the backend's locked dependencies.
- Configured, available MongoDB for saving/listing/opening projects and reading
  extraction runs. Health can succeed while MongoDB is unavailable.
- `C1_ANTHROPIC_API_KEY` and `C1_LLM_MODEL` configured in its local ignored `.env`
  for live extraction. Both are required; there is no frontend mock fallback.
- Backend CORS must allow `http://localhost:5173` (and `http://localhost:4173`
  for preview). Cookies/browser credentials are omitted by the frontend.

The contract was verified using `git show component-1-backend:<path>` at backend
commit `e78da735f54b541647c017c1bfdc14a122dc36f7`, including project/extraction
schemas, routes, repository pagination and backend configuration. A service was
not listening on port 8001 during implementation, so this source verification
was used instead of a running OpenAPI document.

## API contract and limits

| Operation | Route suffix | Success |
| --- | --- | --- |
| Health | `GET /health` | 200, `status`, `component`, `service` |
| Create | `POST /projects` | 201, full project |
| List | `GET /projects?limit=10&offset=0` | 200, `items`, `limit`, `offset`, `has_more` |
| Open | `GET /projects/{id}` | 200, full project |
| Extract | `POST /projects/{id}/extractions` (no body) | 201, saved run |
| Latest | `GET /projects/{id}/extractions/latest` | 200, saved run |
| Transcribe | `POST /transcriptions` (multipart `audio`) | 202, transcription UUID and queued status |
| Transcription status | `GET /transcriptions/{id}` | 200, saved job and available original/segments |

A project contains `id`, `name`, nullable `description`, `discussion_text`,
`status: "draft"`, `created_at`, and `updated_at`. List summaries exclude the
original discussion. IDs contain 24 hexadecimal characters. The list displays
10 records per page using the returned offset/limit and `has_more`; the backend
permits limits 1–100 and offsets 0–10,000. Pagination is not a snapshot, so new
projects can shift pages. Creating a project resets the list to its first page.

Creation limits count Unicode code points, matching Python, rather than browser
UTF-16 units: name 1–120 characters before backend trimming; optional description
0–2,000 or null; nonblank discussion 1–100,000. The frontend does not trim or
rewrite the submitted discussion. The backend extraction input limit defaults
to **30,000 characters**, configurable up to 100,000. The UI does not assume it
knows the deployed limit; it surfaces a backend 413 if extraction is oversized.

An extraction run contains `run_id`, `project_id`, `source_discussion_hash`, UTC
`created_at`, `model_identifier`, `prompt_version`, and `candidates`. Candidates
contain `requirement_id`, `requirement_text`, one or more `evidence` spans with
`quote`, `start`, `end`, nullable `actor`/`action`, and `review_status: "unreviewed"`.
The frontend verifies response structure and matches quotes against the loaded
original source using Unicode character offsets (inclusive start, exclusive end).
Runs may contain 0–100 candidates. Backend timestamps are shown in the browser's
local timezone. Successful POST always creates a separate run; this interface
shows only the latest saved run, without editing or run-history controls.

## Errors, deadlines and uncertain completion

Responses are checked before display. Malformed JSON, wrong schemas, altered
quotes/offsets, wrong project IDs, and unsupported review statuses are failures.
HTTP errors use FastAPI's `detail` string or validation-detail array. Validation
messages display fields/messages without copying the array's client `input`.
Missing projects and malformed IDs have explicit error/retry states. A latest
404 is shown as “No extraction yet” **only** when its detail is exactly
`No extraction found for this project.`; a project-not-found 404 stays an error.

Health timeout is 5 seconds; project/latest requests allow 15 seconds;
extraction allows **200 seconds**, covering the backend's provider deadline of
up to 180 seconds plus normal persistence overhead. There are no automatic
request retries, particularly no POST retries. Provider/database unavailability,
invalid output, size limits and timeouts remain visible API errors.

A timed-out/disconnected POST may still finish in the backend. Use “Retrieve
latest saved result” before sending another extraction. A failed retrieval
keeps the previous result and the recovery gate. Successful retrieval (including
no saved run) releases the gate, but it cannot cancel the earlier request or
prove it has finished; check again later if completion remains uncertain.
Backend POST has no idempotency key, so manually repeating it can create another
run. The same uncertainty applies to project creation: refresh the list before
resubmitting a failed save if completion was uncertain. Session storage may be
disabled by the browser; in-page recovery works, but then the flag cannot survive
navigation. Inputs are not stored in browser storage.

## Verification

`npm test` runs the original health tests plus request/contract tests for create,
list/pagination, detail/latest, source retention, Unicode validation, empty
results, malformed IDs/output, evidence spans, provider/database failures, POST
timeouts and no automatic retries. These use mocked `fetch` responses.

An optional, dependency-free Chromium workflow check starts temporary localhost
Vite/API fixture servers and uses the browser's DevTools protocol:

```sh
# Default executable on macOS: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
npm run test:browser
# If Chrome is elsewhere, set its executable path:
C1_BROWSER_PATH=/path/to/chromium npm run test:browser
```

This check exercises actual UI creation/failure/input retention, duplicate-click
prevention, pagination, details, explicit extraction, latest reload after
refresh, uncertainty recovery across refresh, previous-result retention, empty
results, missing/malformed IDs, list failures/retry, plain-text rendering and
mobile overflow. It uses **mocked API persistence/provider fixtures**, not the
live backend, MongoDB, or a live LLM. It requires permission to start local servers
and headless Chrome. It writes desktop/mobile screenshots in the OS temporary
directory by default; optionally set `C1_BROWSER_SCREENSHOT` to an output PNG path.
No fixture results are research findings or model accuracy evidence.

For live/manual verification with a separately running configured backend:

1. Create a project with a small synthetic discussion containing a permission
   and a prohibition. Verify the saved discussion and list entry.
2. Open it and confirm “No extraction yet”; inspect Network to ensure no
   extraction POST occurred. Press Extract once and inspect every candidate
   and evidence span. All statuses must remain unreviewed.
3. Refresh the browser: the same project/latest run should reload via GET, with
   no new extraction POST. A successful empty run must show its saved metadata.
4. Try a missing project link and a backend outage. Confirm meaningful errors,
   input retention, retry controls, and prior-result retention on POST failure.
5. Tab through labels, actions, original discussion and expandable source hash.
   Check desktop, 375px mobile, and 200% zoom for readable, reachable controls.

Live backend/provider verification was unavailable during implementation. Mocked
browser tests do not establish real MongoDB durability or extraction accuracy.

## Troubleshooting

- **Unsupported Node:** Use the 22.x version in `.nvmrc`, then repeat `npm ci`.
- **Backend unavailable:** Check the separate backend process and API base URL.
  Connected health is insufficient for project/provider readiness.
- **CORS:** `localhost`, `127.0.0.1`, and different ports are different origins;
  configure the exact frontend origin in the backend.
- **Provider unavailable:** Configure credentials/model only in the backend.
- **Malformed response:** Check the service implements the verified contract,
  rather than another component or an HTML proxy error page.
- **Changed environment:** Restart Vite or rebuild for production. HTTPS pages
  need an HTTPS API to avoid mixed-content blocking.
- **Port occupied:** Stop the other process; Vite intentionally does not switch
  ports. If changing ports, update backend CORS too.


## Audio upload and transcript review

The project form offers **Paste text** and **Upload audio** tabs immediately above
the original discussion field. Switching tabs preserves project name,
description, discussion, selected recording, job and review draft. No microphone
recording is implemented.

Choose WAV, MP3 or M4A. The UI checks nonempty files, extension and the default
10,000,000-byte limit before sending multipart field `audio`; the browser sets the
multipart boundary. It displays the default two-minute duration limit. Actual
decoding and duration checks happen server-side; configured backend limits can
differ. Formats/extensions are only hints until the server decodes the file.

The explicit **Transcribe audio** action shows uploading, queued, processing,
completed or failed state. It prevents concurrent submissions and never retries
a POST automatically. GET polling is sequential, every two seconds after the
previous reply, bounded by 150 requests or five minutes. It stops on completed,
failed, a request error or unmount. Each GET has at most a 15-second timeout and
the upload has a 60-second timeout. **Refresh transcription status** performs one
GET, preserving any edited draft. A paused/read-failed job retains its last known
status and ID; a read error is not presented as a transcription failure. Leaving
the form cancels browser requests, not the backend job. An uncertain upload
without a returned ID blocks further uploads in that form, since no job-list or
idempotency contract can resolve whether a job was created.

Completed speech shows **Editable transcript — requires review**, the original
ASR transcript separately in a disclosure, available segment timestamps/text,
job ID, model/language, creation date, audio duration and measured processing
time. Original text/whitespace stays unchanged; all text uses React text nodes
or textarea values. Editing is local and does not update the server's immutable
original. Silence/skipped ASR and no-intelligible-speech outcomes are explicit
and cannot be used as discussions. Model or FFmpeg unavailability, corrupt audio,
timeouts, saturation and server errors show actual API errors; no fake transcript
or language-accuracy claim is supplied.

**Use this transcript** copies the edited draft into the discussion field, with
an explicit Replace/Keep confirmation when that field already has any content.
It preserves project name/description and never saves, extracts or classifies
automatically. The model can invent or omit speech; human review remains required.

### Provenance contract blocker

The current `ProjectCreate` schema permits only `name`, `description` and
`discussion_text`, with `additionalProperties: false`. Project records contain
no transcription reference. Transcription jobs retain an immutable original,
but `reviewed_text` is currently null and there is no review-write or project-link
API. Sending invented provenance fields would fail validation; embedding them in
the description/discussion would corrupt those fields.

After **Use this transcript**, the form therefore retains the reviewed discussion
and its complete source-job snapshot locally, displays the source ID/model/language
and original, and **blocks project saving**. The submit handler also enforces
this guard, including Enter/programmatic submission. Later discussion edits or
tab switches do not erase the pending association. No browser storage contains
audio/transcripts; local drafts are lost when leaving/reloading the form. The
server-side original remains retrievable by job ID.

Backend follow-up is required: an explicit project input/output association to a
saved completed transcription and a persistable review association, retaining
the generated original independently. No such backend change is made here.
An explicit **Clear audio-derived discussion** confirmation clears both discussion
and pending association, retains name/description and the saved transcription,
and restores text-only creation. There is no save-without-provenance bypass.

### Contract and live verification

Inspected the actual generated transcription OpenAPI fragment at
`/private/tmp/intellise-c1-audio-backend/component-1/backend/docs/transcriptions-openapi.json`,
its result schemas, routes and upload settings. Also inspected the running 8001
OpenAPI: that server currently exposes projects/health only, with no transcription,
extraction or classification routes. Run the audio-enabled backend worktree and
point `VITE_API_BASE_URL` at it; health alone cannot prove feature availability.
The live verification used a separate server/port and an isolated disposable
MongoDB database, leaving the 8001 server and existing client records untouched.

`npm test`, `npm run lint`, `npm run build` and `npm run test:browser` cover the
new behavior and the existing workflow. Browser fixtures are explicitly mocked
ASR; unit tests cover deadlines/cancellation and response validation. The separate
opt-in live browser test uses an actual recording and real backend/MongoDB:

```sh
# Run from this frontend directory. Configure a separate audio-enabled backend
# with a disposable DB and CORS allowing http://127.0.0.1:18020 first.
C1_LIVE_AUDIO_BASE_URL=http://127.0.0.1:18021 \
C1_LIVE_UI_PORT=18020 C1_LIVE_AUDIO_FILE=/absolute/path/to/short-english.wav \
  node --test --test-name-pattern='live audio' tests/browser-workflow.test.mjs
```

This launches its own Vite and headless Chrome, uploads the supplied recording,
checks retrieval, edits/refreshes the draft and verifies the provenance save
guard. It does not train/download models or save a project. This opt-in check
creates a real transcription job; use a disposable database and apply cleanup
explicitly. The normal browser test skips live ASR unless its environment is set.
See [audio verification results](docs/audio-verification.md) for actual timings,
commands, files and remaining limitations. Existing within-corpus classifier
metrics do not establish project-held-out performance or prediction confidence.

## Saved FR/NFR classification and stash conflict resolution

ProjectWorkspace is preserved and connected to the dashboard's selected project.
Project creation, hash navigation, Back/Forward, extraction, exact evidence display,
recovery controls, and health status remain available. Classification does not add
another project picker. Existing `?project=PROJECT_ID` bookmarks remain supported
when no hash route is selected. A successfully saved/retrieved extraction refreshes
the classification panel, keeping results scoped to its latest saved run.

The explicit **Classify requirements** action posts to:

```text
POST /api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications
GET  /api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications/latest
```

Saved results load on opening/reopening the project without a POST. Badges map
FR/NFR predictions by requirement ID and display model/version, classification ID
and date. Results for a different extraction run cannot supply current badges.
Duplicate in-flight submissions are guarded; requests are never automatically
retried. Loading, empty, missing extraction/classification, model/database
unavailability and ambiguous timeout/network failures remain visible. After an
ambiguous POST, check saved results before submitting again.

The baseline is TF-IDF plus logistic regression, not BERT. No evaluation macro-F1
is displayed as confidence. Predictions and requirements remain subject to human
review; no fake results, accuracy promise or client-approval claim is supplied.

Both API services remain: api.js provides validated project creation/extraction and
health, while projectApi.js supplies classification and its standalone read helpers.
The exported DEFAULT_BASE_URL is shared. Classification CSS uses distinct project,
list and requirement-card class names to preserve existing dashboard styling.
The stash remains a recovery copy; no files were deleted or backend code changed.

Conflict markers in App.jsx, api.js, styles.css and this README were already tracked
when this resolution began; the index contained no unmerged entries. Resolution
combines the workflow rather than choosing a whole side. Related components and
API/browser tests were inspected and retained. Verify with `npm test`,
`npm run lint`, `npm run build`, and `npm run test:browser` (Chrome and local socket
permissions required). Browser fixtures test interface behavior, not actual model
performance or MongoDB persistence.


Resolution checks on October 15, 2026: `npm test` passed all 35 tests;
`npm run lint` passed with zero warnings; `npm run build` passed. The configured
browser test was run twice and failed at Chrome startup (10-second readiness
timeout, no stderr diagnostics), before application assertions. Its combined
workflow/classification assertions remain unverified in this environment.
No frontend conflict markers or unmerged index entries remain. The original
stash was retained without reapplication or dropping.
