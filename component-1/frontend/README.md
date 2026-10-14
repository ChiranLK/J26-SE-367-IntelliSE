# Component 01 frontend

<<<<<<< Updated upstream
React/Vite interface for IntelliSE's AI-Powered Intelligent Requirement
Engineering Agent for Agile Software Development, a fourth-year research project.
The supported workflow is **create project → open project → extract requirements
→ review unreviewed candidates**.

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
approval. There are no editing/approval persistence controls, FR/NFR predictions,
quality scores, RAG, audio, or SRS generation. Future features remain informational.
All source and model text is rendered as text nodes, never raw HTML.
=======
React/Vite foundation for IntelliSE's **AI-Powered Intelligent Requirement
Engineering Agent for Agile Software Development**, a fourth-year research
project. The page introduces Component 01, checks backend connectivity and displays
saved project/extraction FR/NFR classifications.

## Implemented behavior

- Responsive landing page with semantic headings, a skip link, keyboard focus
  indicators, and an announced connection status.
- Automatic health request on mount, exact contract validation, a five-second
  timeout, and a retry button. Pending requests are cancelled on unmount or
  replacement; stale requests cannot update the page.
- Loading, connected, and unavailable states. The landing page remains usable
  when the backend is offline. Connectivity does not indicate database or AI
  readiness.
- Informational planned capabilities: text input, requirement extraction,
  quality validation, Agile artifacts, and draft SRS generation. These remain planned.
  Saved-extraction FR/NFR classification is available in its own panel below.

Persistence, extraction and classification are supplied by the separate backend.
The frontend does not train models or generate fallback results.
>>>>>>> Stashed changes

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

<<<<<<< Updated upstream
Open <http://localhost:5173>. Vite uses a fixed port with `strictPort`.
Stop with Ctrl+C. For later sessions use `npm run dev`. No new npm dependencies
are required; `package-lock.json` remains the reproducible dependency lockfile.
=======
Open <http://localhost:5173>. The port is fixed with `strictPort` so an occupied
port produces an error instead of silently changing the browser origin.
Stop with Ctrl+C. For subsequent sessions, run `npm run dev` from this directory.
Use npm consistently; `package-lock.json` is the reproducible dependency lockfile.

## Environment and separate backend

The example config contains:

```dotenv
VITE_API_BASE_URL=http://localhost:8001
```

Copy it to `.env` and restart Vite after editing. It should be an HTTP(S) base
URL without a query, fragment, or embedded credentials. A trailing slash is
supported. The frontend appends `/api/v1/component-1/health`.

**Every `VITE_*` value is public** and is bundled into browser code. Never put
API keys, passwords, tokens, or other credentials in these variables. Local
environment files are ignored; only `.env.example` is intended for version control.
Production configuration is selected at build time; changing `.env` requires
a new build.

The backend runs separately in another terminal. Follow the backend's own
README when its implementation is available; installing or running this
frontend does not start it. See `../backend/README.md` for the backend source and setup.
The service must allow the frontend's browser origin through CORS:
`http://localhost:5173` for development. If you use production preview, configure
`http://localhost:4173` as an allowed backend origin as well.

Expected contract:

```text
GET http://localhost:8001/api/v1/component-1/health
```

```json
{"status":"ok","component":"component-1","service":"requirement-engineering"}
```

Only a successful HTTP response containing all three expected field values
displays **Connected**. Extra response fields are ignored. HTTP failures,
invalid JSON, mismatched contracts, network/CORS failures, and timeouts display
**Unavailable** with a short explanation. Retry performs a new request; it
is temporarily inactive during a check. No continuous polling is performed.

## Verification commands
>>>>>>> Stashed changes

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

<<<<<<< Updated upstream
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
=======
- **Unsupported Node version:** Check `node --version`; use the supported 22.x
  version and repeat `npm ci`. Do not change the lockfile to bypass an engine error.
- **Dependency download fails:** Check npm registry access and retry `npm ci`.
- **Port 5173 already in use:** Stop the other process before running Vite.
  If deliberately changing ports, update the backend's allowed CORS origins.
- **Backend unavailable:** Confirm the separate backend is running and the
  configured host/port are correct. Retry after fixing the service or network.
- **CORS failure:** Check the browser console and the backend's allowed origin.
  `localhost` and `127.0.0.1`, and different ports, are distinct origins.
- **Invalid response:** Confirm the URL reaches Component 01's health endpoint,
  not a proxy error page or another component. Check the three contract fields.
- **Request timeout:** The request is cancelled after five seconds. Check the
  backend logs and network, then retry.
- **Changed environment has no effect:** Restart the development server or
  rebuild for production. An HTTPS frontend needs an HTTPS backend to avoid
  browser mixed-content blocking.

## Saved project/extraction classification

The landing page and health check remain available. This checkout initially had no
project/extraction interface; a saved-project panel now uses the existing backend
contracts without creating or rewriting discussions/extractions.

- List saved projects (20 per page), open one by its ObjectId, or reopen a bookmarked
  `?project=PROJECT_ID` URL.
- Retrieve its latest saved extraction, then retrieve saved classification for that
  exact extraction UUID. No extraction or classification is generated on opening.
- Explicit **Classify requirements** sends a body-free POST for that saved run.
  FR/NFR badges map by requirement ID, including when prediction order differs.
- Display returned model identity/version, classification timestamp and ID. The
  trained model is named TF-IDF + logistic regression. No evaluation metric,
  confidence score, generated label or approval claim is shown.
- Loading, no projects, no extraction, empty candidates, no saved classification,
  model unavailable, database unavailable, timeout and malformed-response states
  are handled separately. Empty extractions can show saved empty predictions;
  there is no classification action when there are no requirements.
- Buttons are disabled during classification, backed by synchronous UI and service
  guards. The frontend never retries POST automatically. Timeout/network failure
  warns that persistence is ambiguous and asks the user to refresh saved results.
  The backend has no idempotency contract, so prevention is limited to concurrent
  submissions in this page; another tab or reload can still submit independently.
- Responses must match the project/extraction and map every candidate exactly once
  to an FR/NFR prediction. A different run, missing/unknown/duplicate requirement ID
  or invalid label cannot supply badges. Refresh clears old badges; after POST,
  the frontend checks whether a newer extraction exists and explains when the
  saved result belongs to the older run. Only the current run's saved predictions
  are applied. The API does not expose a classification-history list across runs.
- Pending reads are cancelled when switching projects or refreshing. Stale responses
  cannot replace the new project's view. Original discussions are displayed as text.

Inspected backend source files and the actual running OpenAPI on October 14, 2026:

```text
GET  /api/v1/component-1/projects?limit=20&offset=0
GET  /api/v1/component-1/projects/{project_id}
GET  /api/v1/component-1/projects/{project_id}/extractions/latest
POST /api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications
GET  /api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications/latest
```

The classification response supplies `classification_id`, `project_id`,
`extraction_run_id`, `model_identifier`, `model_version`, `classified_at` and
`predictions: [{requirement_id, label}]`. Only the specific 404 message
`No classification found for this extraction run.` means no saved classification;
other 404s remain errors. The model-unavailable 503 is separate from persistence 503.
Health requests retain their existing five-second timeout; project reads use ten
seconds and classification uses thirty seconds, with no automatic retry.

### Verification for this change

From `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
npm run dev
```

Results: **21 tests passed**, lint passed with zero warnings, production build
passed. Existing eight health checks still pass. New tests cover route/query/body
contracts, reopening retrieval, empty/missing states, ID-based mapping, older-run
rejection, malformed output, distinct unavailable states, in-flight duplicate
protection, cancellation and timeout/network behavior without automatic retries.
These tests mock HTTP responses and do not establish actual model performance or
live persistence.

Live checks used the new frontend API service against `http://127.0.0.1:8001`:
OpenAPI returned 200 with the classification POST/latest GET routes; health
validation passed; project listing returned **503**, mapped to the database
unavailable state. Development Origin `http://localhost:5173` received health 200
with the matching `access-control-allow-origin` header. Node HTTP/header checks
are not a browser interaction test. Browser rendering/interaction and a successful
live classification/reopening check remain unverified while MongoDB is unavailable.
No client records were changed by the live checks.

After MongoDB and a valid saved extraction are available, manually verify:

1. Open the project and confirm exact extraction/requirement IDs.
2. Classify once; rapid repeated clicks must not send concurrent POSTs. Confirm
   returned FR/NFR badges, model/version and date without confidence values.
3. Open another project, return, and reload the bookmark; saved classifications
   must load by the exact extraction UUID without a POST.
4. Create a newer extraction through the backend's normal validation path, then
   refresh. Old labels must disappear and the run-change notice must explain why.
5. Test model unavailable, database unavailable, no extraction and empty extraction
   cases. Previously saved results should remain readable without a loaded model.
6. Check keyboard navigation, mobile layout and project switching during read loads.

The model's evaluation remains a within-corpus normalized-text holdout, not a
project-separated evaluation. Prediction badges do not establish requirement
correctness, relevance, completeness or client approval. No backend files were
modified for this frontend change; no commit or push was made.
>>>>>>> Stashed changes
