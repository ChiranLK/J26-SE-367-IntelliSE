# Component 01 frontend

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
