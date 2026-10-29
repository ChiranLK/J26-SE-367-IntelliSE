# Component 01 frontend

For MongoDB + the full audio backend + frontend in one terminal, run
`./start-component-1` from the repository root. See
[local startup](docs/local-startup.md) for prerequisites and stop/restart guidance.

## Quick test: type a requirement and classify it

From the repository root:

```sh
cd component-1/frontend
npm run dev
```

For this optional diagnostic only, open http://localhost:5173/#model-test
and use **Functional or non-functional?**. The tester is separate from the project
workflow and no longer appears below it. Enter one requirement and click **Check requirement**. The panel
shows the actual FR/NFR prediction, saved model version and processing time.
The initial request includes lazy model loading and can take longer.

To test a file, click **Download sample CSV (12 requirements)**, choose that file
under **Requirements CSV**, then click **Check uploaded file**. The same sample is
at `public/samples/fr-nfr-test.csv`. It contains six illustrative FR and six NFR
expected labels, including cases the model may get wrong. Predictions are not
pre-filled. The table shows actual labels and Match/Mismatch comparisons; this is
not a benchmark or a new measured general accuracy score.

Custom files must be UTF-8 CSV, up to 100 KB / 50 requirements, with a required
`requirement` column and optional `id` / `expected_label` columns. Expected labels
can be FR, NFR or blank. IDs must be unique. Quote fields containing commas,
quotes or newlines using CSV conventions. The file is parsed in the browser;
only requirement text is sent for inference, one row at a time. Expected labels
never go to the model. Failed checks stop and mark remaining rows unchecked;
there is no automatic retry, project creation or persistence. Replacing the file
clears previous results. Single and file checking share an in-flight guard.

This development-only tester uses a same-origin Vite adapter at
`POST /__local_model/classify`, not a new public backend API. It reuses the
backend's `LocalClassifier` and trusted artifact loader in a reusable Python
worker. It does not train/download a model, invoke Ollama, create projects or
write to MongoDB. The existing saved-extraction classification workflow stays
unchanged. The public backend currently requires a saved extraction and has no
single-sentence inference endpoint.

Defaults use the preserved environment and selected model in
`.worktrees/component-1-backend/component-1/backend`:

- Interpreter: `.venv/bin/python`
- Artifact: `research/models/dcai-v1/lr-c10`

For a different trusted local installation, set absolute paths in the frontend's
ignored `.env` and restart Vite:

```dotenv
C1_TEST_PYTHON=/absolute/path/to/backend/.venv/bin/python
C1_TEST_MODEL_DIR=/absolute/path/to/backend/research/models/dcai-v1/lr-c10
```

These are server-only settings, never `VITE_*` browser settings. Keep the existing
working classifier environment; do not install Whisper dependencies into it.
Missing artifacts/dependencies report an error without substituting predictions.
Only one check runs at a time, with a 60-second worker deadline and no automatic
retry. Input is limited to 5,000 characters; no requirement or model paths are
logged. Closing Vite terminates its worker. Keep the development server local.

This model predicts FR/NFR for any supplied text; it does not establish that the
input is a valid requirement. Results require review and have no displayed
confidence score. The earlier 0.9041 test macro-F1 is within-corpus evaluation,
not project-held-out accuracy or confidence for the typed sentence.

The static production build/preview disables this local tester. Deploying a
standalone tester requires a separately implemented public inference endpoint;
Python code and model binaries are never bundled into browser assets.

Checks (from this directory):

```sh
npm test
npm run lint
npm run build
npm run test:browser
# Optional actual local-artifact check in Chrome (no ASR/LLM/MongoDB required):
C1_LIVE_MODEL_TEST=1 node --test --test-name-pattern='live local model' tests/browser-workflow.test.mjs
```

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

Optional **Upload audio → transcribe → review → use transcript → save** is available
when the configured backend exposes the provenance contract described below.
Older/incompatible backends keep the audio-saving guard; text-only creation
retains its existing behavior.

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

### Provenance contract and saving

The frontend reads the configured backend's **/openapi.json** on opening a form
and rechecks immediately before an audio-derived POST. It requires ProjectCreate's
optional UUID **transcription_id**, and project POST/detail responses advertising
the **transcription_provenance** v1 snapshot. Local schema references and nullable
fields are resolved. An unavailable/malformed/older contract keeps saving blocked
for audio-derived drafts, with **Check audio saving support** to retry discovery.
Text-only saves do not require OpenAPI availability. A deployment path in
VITE_API_BASE_URL also prefixes the OpenAPI URL.

After **Use this transcript**, the complete source-job snapshot remains separate
from discussion_text. Further discussion edits and tab changes retain its ID.
When the contract is available, **Save and open project** sends only:

```json
{
  "name": "Client portal",
  "description": "Reviewed stakeholder discussion",
  "discussion_text": "The user's edited review text.",
  "transcription_id": "668a97af-dda2-48ef-969a-1eb4d9a86076"
}
```

Replace the illustrative ID with the selected completed job. Model, original
text, timestamps and hashes are never sent as client metadata. The backend
retrieves them from storage. Omit the ID for text-only creation. HTTP 404/409/422,
network failures and bad acknowledgements retain the draft/reference; there is
no retry with the reference removed. A fresh contract check prevents a POST after
a backend downgrade. The response must retain the requested source ID and exact
submitted discussion; an absent/mismatched provenance is an uncertain failed save.

Full project responses are checked against the v1 snapshot structure, and browser
Web Crypto recomputes SHA-256 of both original and reviewed UTF-8 text before
accepting a save/detail response. Mismatches show an error rather than degrading
to a text-only project. Audio source verification needs Web Crypto in a secure
browser context (HTTPS or localhost); legacy text-only records are unaffected.
Native textarea editing normalizes line endings to LF; API submission/hashing
does not otherwise normalize text, and the separate original stays unchanged.

Reopening or refreshing a saved project shows **Reviewed client discussion** and
**Saved audio source**: transcription ID, provider/model/language, source/review
timestamps, duration/processing time, original ASR text/segments, hashes and
provenance version. User-reviewed does not mean independently verified. All text
is rendered safely as text nodes. Extraction/classification remain explicit and
use the saved reviewed discussion. The source transcription job stays unchanged.

Unsaved drafts/source snapshots stay local to the form and are lost on navigation
or reload; saved provenance is retrieved from the project API. An explicit
**Clear audio-derived discussion** confirmation clears discussion and pending
association together, retaining name/description and the source job. There is no
save-without-provenance bypass.

### Contract and live verification

Inspected the actual generated project-provenance/transcription OpenAPI and schemas
in the durable `.worktrees/component-1-backend` backend checkout, then verified
the contract from the separate live backend used by the browser. Also inspected the running 8001
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
checks retrieval, edits/refreshes the draft, confirms replacement, saves with
provenance, refreshes the page and reopens from the project list. It does not
train/download models. This opt-in check creates one real transcription job and
one explicitly saved project; use a disposable database and apply cleanup
explicitly. The normal browser test skips live ASR unless its environment is set.
See [audio-save verification results](docs/audio-save-verification.md) for actual timings,
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

### Reviewed FR/NFR labels (October 18, 2026)

Open a saved project and classify its saved extraction. Below the predictions,
enter a **Reviewer name or ID**, select the **Reviewed label** for a requirement,
optionally add a note, and choose **Save review**. Reopen the project to retrieve
saved reviews. The badge remains the original model prediction; the reviewed
label and reviewer/date are shown separately. Reviewer names are self-reported,
not authenticated identities. No training or client approval happens here.

Reviews belong to the exact project, extraction, classification and requirement.
Running classification again creates a separate run with separate reviews; older
reviews remain stored. A missing review API shows an unavailable state and blocks
saving instead of pretending the review was saved. Restart the backend from its
worktree after updating its source; an already-running process may lack these routes.

The frontend shares `api.js` request handling through `reviewApi.js`. Ambiguous
save errors offer an explicit retry using the same submission UUID; requests are
not retried automatically. Saves are guarded against duplicate clicks, and reads
and pending requests are aborted on unmount. Text and notes render as plain text.
See `docs/label-review-verification.md` for checks and limitations.

### Guided project workflow

The main interface now follows three stages, with a progress tracker:

1. **Create & review source**: name/description, Paste text or Upload audio, edit
   the discussion and confirm that you reviewed it, then Save and open project.
   Audio still requires the explicit Use this transcript action and retains its
   backend transcription provenance. Saving never happens automatically.
2. **Classify & review labels**: Run extraction & classification calls the existing
   saved extraction API followed by the existing classification API. Select FR or
   NFR and Save review for each label you review. A compact comparison table shows readable
   numbers, requirement text, model predictions and human reviews; original
   IDs/evidence and model metadata remain in expandable details.
   Classification-only retry is available if extraction saved successfully but
   classification failed. No automatic retries or provider fallback were added.
3. **Export results**: preview and download minimal JSON or text containing only
   the project title, description, functional requirements and non-functional
   requirements. Saved human-reviewed labels take priority over model labels.
   The page warns when labels are still model predictions. Unsaved edits and
   failed/loading review retrieval block export. Empty groups stay empty.
   Evidence, review history, model/run identity and audio provenance remain in
   the project rather than in these simplified downloads.

A saved project reopens at stage 2; use Review saved source to inspect stage 1.
The progress tracker records availability of saved source/classification in this
view, not approval or completion of every review. Confirmation before project
saving is a frontend acknowledgement, not an independently verified review or a
new backend text-source audit field. Saved source records remain immutable.
The unsaved sentence/CSV model tester is available separately at `/#model-test`;
it is not rendered on project pages. Planned capabilities have been removed. Health status remains visible. Step 2 uses one continuous panel
for extraction and saved label review, with one empty state before extraction.
See [guided workflow verification](docs/guided-workflow-verification.md).


UI cleanup on October 19: the duplicate standalone tester was removed from the
project page, the extraction/review panels were joined, and desktop/mobile control
spacing was aligned. The tester's source and optional diagnostic route remain.
Verification: 93 frontend tests passed; lint/build passed; Chrome browser checks
passed (mocked workflow API plus the actual existing local classifier), with live
Azure audio skipped. No backend/model changes or client-record writes were made.

### Delete projects and review unclear points

Each dashboard project now has **Delete**. Confirm the named project before the
request is sent. Deletion removes it from the list and normal project/result
retrieval; its database source, transcription and extraction/classification/review
history remain retained for recovery. This is not permanent erasure. Cancel sends
no DELETE, duplicate clicks are guarded, and failures remain visible without
optimistic removal or automatic retries. Deleting the open project returns to
Create a project. Restart the backend to load the new DELETE route.

Step 2 requirement cards now contain **Unclear points**. English wording rules
flag exact phrases such as “quickly”, “user-friendly”, vague quantities, open-ended
lists and tentative obligations. Each flag provides a clarification question.
The checker is separate from the FR/NFR model, does not rewrite source or labels,
and is **not a trained ambiguity model**. A flag is a review hint; no rule match
is not a proof of clarity. Permissions such as “administrators may delete” are
not automatically treated as ambiguous because they contain “may”.

Hints stay in the application and are omitted from the simplified downloads.
They are recomputed locally from saved candidates,
not stored as independent ambiguity-review records in MongoDB. Human FR/NFR label
reviews still use the existing backend records; saving a label does not resolve
an ambiguity flag. See [deletion and ambiguity verification](docs/deletion-ambiguity-verification.md).


Export downloads use the project title, for example `Demo Calculator.json` and
`Demo Calculator.txt`. Characters that filenames cannot contain are replaced,
reserved names are prefixed, and exceptionally long names are shortened. Project
and run IDs remain available in the project details. The browser
may add a numeric suffix when a file with that name is already downloaded.


### Requirement review table

Step 2 displays **ID | Requirement | Model prediction | Human review | Details**.
Each row retains its own select, optional note and explicit Save review action.
The model prediction stays separate from a saved human label. Expand a saved label
for reviewer/date/note, or choose View details for source evidence and Unclear points.
Opening/closing details preserves unsaved selections. Draft review edits still block
export, and saved reviews remain scoped to the original run/requirement IDs.

On mobile the table scrolls horizontally inside its focusable panel. The source,
classification, review and export APIs are unchanged. Long requirement IDs remain
available under Details. See
[table verification](docs/requirement-table-verification.md).

The Human review label selector now uses a styled accessible combobox: green FR
and blue NFR badges, short option descriptions and a checkmark for the selected
value. Open it with click, Enter or Space; use arrows/Home/End, then Enter/Space
to select. Escape dismisses without changing the value; Tab leaves the control.
F/N navigate to FR/NFR. Clear selection clears only the unsaved picker value,
not a saved review. Save review remains an explicit separate action.

The menu renders above the table's scroll clipping, follows its trigger during
scrolling and closes on outside click/blur/resize or when its row leaves the
viewport. Disabled/saving/uncertain states still lock the selection. No API or
model changes were needed. See `docs/review-label-selector-verification.md`.

### Unclear wording in the full saved discussion

At the bottom of Step 2, below the review table, the app checks the **full saved discussion**, using the same
English wording rules. If flags exist, “Unclear wording in saved discussion” opens
to show the phrases and clarification questions. This is independent of Ollama:
it works before extraction and remains available when extraction omits sentences.
The per-requirement hints are still under each table row's Details.

Source hints are **not recovered requirements** and receive no invented FR/NFR
labels. Conversation can also trigger the rules, and context can resolve a flagged
term. A one-row extraction remains one row until an actual new valid run is saved.
This change does not establish or repair extraction completeness.

Simplified JSON/text downloads omit wording hints. Internal analyses keep
scope-specific Unicode character positions; these are end-exclusive. The UI shows
at most the first 20 flags per panel. Scans and hints remain local and do not
modify source, saved runs, predictions, reviews or backend records.
See [minimal UI and export verification](docs/minimal-ui-export-verification.md)
for the current layout and download contract; earlier verification reports
record the richer export format used before this simplification.

### Text/audio source styling

The source tabs use a glass surface and sliding selected highlight, with a short
panel transition. Arrow keys/Home/End still switch tabs; reduced-motion settings
turn animations off. The audio picker remains a native file input with its
associated label, visible focus ring and styled file button. Transcription
buttons now distinguish hover, pressed and disabled states; disabled actions show
a not-allowed cursor. Source-review spacing and mobile upload alignment were
adjusted. These are frontend presentation changes only.

Verified on 2026-10-20: 106 frontend tests passed; lint, production build and
whitespace checks passed. The affected Chrome workflow passed with mocked API
responses, including keyboard tab switching, cursor states, reduced motion,
mobile width and audio review/provenance flows. Desktop/mobile screenshots were
inspected. No live Azure/Whisper request or model evaluation was performed.

### Saving human classification reviews

Each row now has one Save review action; Discard edits was removed. Select FR or
NFR, enter the required reviewer name/ID above the table, and save. Selecting a
label enables Save; if the reviewer field is empty, clicking Save shows an inline
message and focuses that field without sending a request. Enabled Save buttons
use a pointer cursor and green hover/pressed states. Busy/unavailable/unselected
states remain disabled with a not-allowed cursor. Original model predictions,
explicit saving, duplicate protection and safe same-submission retries remain.
Unsaved label edits still block export; save them or restore the existing selection.

Review-save verification (2026-10-20): 106 unit tests, lint, production build and
whitespace checks passed. New browser assertions cover missing-reviewer focus,
zero submissions without reviewer identity, pointer cursor and absence of Discard.
The browser check could not run: Chrome startup timed out twice before application
checks began. This change therefore has no completed browser verification yet.

### Step 4: SRS and client review

Open a saved project and choose **SRS & client review** in the progress tracker,
or **Continue to SRS** from the export stage. Enter a reviewer name, then choose
**Generate draft SRS**. Model labels are used automatically; save corrections only where needed.
The backend constructs the draft from
stored source and reviews; no LLM/RAG call is made.

Record **Request changes** or **Needs clarification** for exceptions; both
require comments. Confirm and choose **Accept remaining requirements** to accept
pending requirements in one action. Existing exceptions are preserved. Individual
acceptance remains optional. An analyst
can expand **Create a revised draft**, edit a requirement/type and give a reason.
Saving creates a new version and resets client acceptance for every requirement;
it never rewrites the original discussion or an earlier version. Once all items
are accepted, tick the confirmation and approve the exact displayed version.
Historical versions are read-only and downloadable as separate SRS JSON/text.
Existing minimal requirement exports remain unchanged.

Client names are self-reported, not authenticated identities. This is a
requirement-focused template, not a complete standards-compliant SRS. New
extractions/label edits do not silently update an existing SRS. This phase supports
revising existing requirements, not adding/removing them or rebasing a new source
run. Agile stories, acceptance criteria, RAG validation and automatic UML/code/test
handoff are not implemented in this phase.

Restart the backend from `.worktrees/component-1-backend/component-1/backend`
using its normal `.venv/bin/python -m intelise_c1`, or stop your existing launcher
with Ctrl+C and restart `./start-component-1` from the main root. Do not launch a
second backend on an occupied port. The backend's OpenAPI must contain
`/api/v1/component-1/projects/{project_id}/srs`; an old backend gives an actionable
route-unavailable message rather than fake local storage/results.

Verification on 2026-10-20: **113 frontend tests passed**, lint and production
build passed. The Chrome executable timed out at startup; the existing cached
Chromium headless shell successfully ran the full browser workflow with mocked
APIs, including SRS generation, missing reviewer validation, duplicate clicks,
change feedback, revision, fresh acceptance, approval, saved refresh, historical
read-only viewing and actual JSON download. The backend's separate real-MongoDB
suite passed persistence and restart checks; this is not a combined browser/real
MongoDB test or a new model-performance measurement.

Reproduce from `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
# Default browser, when available:
node --test --test-name-pattern='project creation, extraction' tests/browser-workflow.test.mjs
# Alternative already-installed browser used in this session:
C1_BROWSER_PATH="$HOME/Library/Caches/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-mac-x64/chrome-headless-shell" \
  node --test --test-name-pattern='project creation, extraction' tests/browser-workflow.test.mjs
```


### Exception-based reviews — 2026-10-21

FR/NFR model labels are retained by default. The optional row picker displays
“Use model label (FR/NFR)” until a correction is saved. Only corrections need a
reviewer name. Saved reviews show “✓ Saved”; changing the label/note enables Save
again. No fabricated review is written for an unchanged model prediction.

SRS generation now works with no or partial label reviews. Each requirement's
source details distinguishes model predictions, saved human reviews and authored
revisions. Existing SRS snapshots remain unchanged; to change an existing snapshot
use its revision workflow.

The client decision picker now reuses the keyboard-accessible styled listbox with
status colors, icons and descriptions. Optional accept comments are collapsed;
change/clarification comments are shown and required. A successful response shows
“✓ Saved” and disables repeat saving until the decision/comment changes. Saving
and failed/uncertain requests are distinct; no success is displayed on failure.

Bulk acceptance requires the explicit confirmation checkbox and reviewer name.
It submits once, accepts only pending items, preserves change/clarification
requests and does not approve the document. Final SRS approval is still separate.
Original predictions, source records and version history are preserved.

Verification for this update: **115 frontend tests passed**; lint/build and
whitespace checks passed. The browser workflow passed with mocked APIs using the
previously installed Chromium headless shell. It covered draft generation without
label reviews, no fabricated review writes, saved correction precedence, styled
client decision selection, saved/disabled state, explicit bulk confirmation,
duplicate clicks, revision/approval and mobile layout. Two test issues were fixed:
a navigation wait read document.body before it existed, and an old details
selector matched the newly collapsed comment section. Real MongoDB verification
was performed separately in the backend suite (**336 tests passed**); no new
ASR/model-performance measurement or existing-client-record edits were performed.

After updating, stop your existing launcher with Ctrl+C and run
`./start-component-1` again from the repository root, then refresh the browser.
The backend restart loads the optional-label policy and `/srs/accept-remaining`
route. Older SRS versions retain their stored labels, decisions and approval.

### Required reviewer before export

The classification reviewer name/ID is now required before moving to Export
results, even when no label corrections are needed. Both Continue to export and
the progress-tracker Export button reject blank/whitespace-only values, display
“Please provide your reviewer name or ID.”, return to label review and focus the
field. The inline error is associated with the input for assistive technology and
clears when a nonblank value is entered. The name remains available during
classification/result refreshes in the same project and resets on page reload or
project change. This is a frontend workflow acknowledgement; it does not invent
saved label reviews or add reviewer metadata to the minimal export/backend data.

Verified: 115 unit tests passed, lint/build passed, and the mocked browser workflow
passed. Browser assertions cover blank and whitespace-only names, both navigation
paths, input focus/invalid state and proceeding with a valid name. No backend
changes were needed for this frontend-only validation.

### Stale SRS backend diagnosis — 2026-10-21

The UI's old “Review and save every FR/NFR label” 409 was traced to a backend
process started before the optional-correction update. Live OpenAPI on port 8001
still advertised `reviewed-requirements-template-v1` only and had no bulk-accept
route; the source on disk already used the corrected policy. The identified
launcher was gracefully restarted after checking zero queued/processing audio
jobs. Existing MongoDB, models and project records were retained. Live OpenAPI
then confirmed the corrected draft policy, v2 generation method and bulk route;
health and frontend returned HTTP 200. No SRS was generated in an existing project.

Launcher readiness now requires the current SRS contract and bulk route. If an
older backend still returns the old review gate, the UI explicitly explains that
the running backend must be restarted rather than instructing users to review all
labels. Affected frontend API/startup tests (14) and SRS backend tests (13) passed;
lint/build passed. No automatic retries, label-review fabrication, dependency
changes, commits or pushes were introduced.

### Header cleanup — 2026-10-22

Removed the Backend connectivity card, its retry button and dashboard-only health
request hook. The heading now uses the full row without an empty card column.
Backend health endpoints, launcher readiness checks and workflow error handling
remain unchanged. Existing status-hook/service files are retained for reuse.


### Extraction timeout recovery — 2026-10-22

The local extraction configuration now allows 180 seconds and 768 output tokens;
the launcher prints those budgets. A known backend provider-timeout response is
reported as unsaved and allows an explicit retry, while unknown 504s/network
failures still require saved-result retrieval. Recovery controls automatically
open when that check is needed. Nothing automatically retries or fabricates a run.
For a warning retained from before this update, choose Retrieve latest saved
result once before explicitly running extraction again.

The synthetic GPA live extraction completed in 37.55 seconds with valid exact
source evidence, but returned 10 of 11 statements. It omitted course editing/
deletion. This remains an extraction completeness limitation, not an FR/NFR
classifier issue. The backend docs/ollama-timeout-recovery.md records the actual
response, configuration, checks and reproduction commands.

### Workflow connector and audio explanation — 2026-10-22

The connector from Export to SRS now turns green when Step 4 is reached, with the
line spanning the grid gap. Earlier step circles show the reached path without
claiming that an export download occurred or that an SRS was approved. Mobile
keeps its existing two-column layout without crossing connector lines.

After applying an audio transcript, the pending source reference is now explained
as “Audio transcript linked”: saving keeps the edited discussion and original
transcript together. Supported saving uses a calm green information panel;
actual missing-contract errors keep their warning state. Technical recording
IDs/model information are under Recording details, and the original transcript
remains separately available under View original transcript (before your edits).
Source references, replacement/clear confirmation and saving behavior are unchanged.

Verified: lint and production build passed. The mocked browser workflow passed,
including the green Step 3→4 connector, navigation-versus-completion distinction,
collapsed recording details and unchanged original transcript/provenance flows.
No backend, source-record, commit or push changes were made for this UI update.
