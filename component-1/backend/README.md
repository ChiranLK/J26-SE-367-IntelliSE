# Component 01 backend

Component 01 is the AI-Powered Intelligent Requirement Engineering Agent for
Agile Software Development in the IntelliSE fourth-year research project.
The proposed 50% prototype deadline is October 18, 2026. This directory provides
the backend foundation, source-grounded requirement candidate extraction, and
optional TF-IDF/logistic FR/NFR baseline tooling;
it does not represent the completed prototype.

## Current behavior

FastAPI serves an availability response, project creation/list/retrieval,
source-grounded extraction runs, interactive API documentation, and configurable development CORS origins.
Projects and their original client discussions are persisted in MongoDB.
The health endpoint works
without MongoDB, an LLM API key, downloaded models, or any external service.
It confirms application availability only, not database or AI readiness.

FR/NFR baseline classification requires a trusted locally trained model. The supplied
DCAI labels now have a locally trained TF-IDF/logistic baseline; see
[the measured evaluation report](research/dcai-baseline-report.md). Genuine source project IDs and
project-separated evaluation remain unavailable. LLM-based quality validation,
RAG and LangGraph remain future work. A template SRS/client-review first phase
is now available; see the SRS section below. Measured baseline results and their limitations are documented in the report.

Optional audio transcription now accepts bounded WAV/MP3/M4A uploads and retains
Whisper originals for human review. See [audio setup and API contract](docs/audio-transcription.md)
and [actual verification results](docs/audio-verification.md). It neither creates
projects nor extracts/classifies requirements automatically.
Project creation can now explicitly associate a completed transcription with the
user's edited discussion and save backend-owned provenance. See the
[frontend integration contract](docs/project-transcription-provenance.md) and
[verification report](docs/project-provenance-verification.md).

## macOS setup

Azure Speech is now an optional transcription provider alongside local Whisper.
Run `.venv/bin/python scripts/configure_azure_speech.py` from this backend to enter
KEY 1 privately and preserve existing settings. See [Azure setup and verification](docs/azure-speech.md).
Azure uses the same upload/review/project workflow; no SDK, model training or
classifier dependency changes are required. Cloud transcription is billed usage,
not an automatic free student service. No cloud call runs at startup.

Supported runtime: **Python 3.12** (verified with 3.12.8). Install Python 3.12
first if `python3.12 --version` is unavailable. Dependency management uses pip
and `pyproject.toml`; `requirements.lock` pins the resolved runtime and test
dependencies for reproducible installation. No other package manager is needed.

From the repository root, run:

```sh
cd component-1/backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e '.[dev]'
cp .env.example .env
python -m pip check
python -m pytest
python -m intelise_c1
```

Use the **component-1-backend** checkout for these commands. This session's durable
backend worktree is `.worktrees/component-1-backend` under the main repository;
from there, enter `component-1/backend`. Its dedicated `.venv` is installed against
that source. Reinstall the editable package after changing checkouts, then verify:

```sh
python -c 'import intelise_c1; print(intelise_c1.__file__)'
python -m intelise_c1
```

The import path must point into the backend checkout you intend to run. Normal
startup registers project, extraction, classification **and transcription** routes
without Whisper installed/configured. Check `/openapi.json` for
`/api/v1/component-1/transcriptions` and `ProjectCreate.transcription_id`.
Health alone does not establish route/model/database readiness. All source for
these routes is in this backend checkout; startup needs no temporary source
snapshot or custom `PYTHONPATH`. Optional ASR execution still needs the separately
prepared model/interpreter described in the audio guide. Run one backend instance.

The virtual environment isolates this backend's dependencies from other
components. Run all commands below from `component-1/backend` with it active.
For subsequent sessions:

```sh
cd component-1/backend
source .venv/bin/activate
python -m intelise_c1
```

Stop the server with Ctrl+C. The equivalent installed command is
`component-1-backend`.

## Environment setup

`.env` is optional and ignored by Git. `.env.example` contains only example
development values, with no credentials. Defaults are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `C1_BACKEND_HOST` | `127.0.0.1` | Local bind address |
| `C1_BACKEND_PORT` | `8001` | TCP port (1–65535) |
| `C1_CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | Exact allowed browser origins |
| `MONGODB_URI` | Unset (health-only operation) | MongoDB connection string; credentials remain local |
| `MONGODB_DATABASE` | `intellise_component_1` | Application database name |
| `C1_MONGODB_TIMEOUT_MS` | `2000` | Database operation/connection timeouts; 100–10000 ms |

Environment variables override `.env`. The `.env` file is read from the current
working directory; run from this backend directory. CORS origins use a JSON
array of HTTP(S) origins, including the port where applicable. Wildcards,
paths, and trailing slashes are rejected. An empty array disables cross-origin
access. Browser credentials are disabled; GET and POST with Content-Type are
allowed for preflight requests. CORS is a browser policy, not authentication; unlisted origins do not
receive an allow-origin header.

For example, temporarily override the port:

```sh
C1_BACKEND_PORT=8011 python -m intelise_c1
```

For development reload, Uvicorn's CLI requires its own explicit host/port flags
(it does not read `C1_BACKEND_HOST` or `C1_BACKEND_PORT`):

```sh
python -m uvicorn intelise_c1.main:app --host 127.0.0.1 --port 8001 --reload
```

## Verify the running API

At the default host and port:

- Health: <http://127.0.0.1:8001/api/v1/component-1/health>
- Swagger UI: <http://127.0.0.1:8001/docs>
- ReDoc: <http://127.0.0.1:8001/redoc>
- OpenAPI schema: <http://127.0.0.1:8001/openapi.json>

From another terminal:

```sh
curl --fail-with-body -i http://127.0.0.1:8001/api/v1/component-1/health
```

Expected HTTP status: `200`. Expected JSON:

```json
{"status":"ok","component":"component-1","service":"requirement-engineering"}
```

Check the default allowed-origin response:

```sh
curl --fail-with-body -i \
  -H 'Origin: http://localhost:5173' \
  http://127.0.0.1:8001/api/v1/component-1/health
```

Expect `access-control-allow-origin: http://localhost:5173`.
Run automated health, CORS, configuration, validation, and availability checks
with `python -m pytest`. Integration tests skip unless `TEST_MONGODB_URI` is set.

## MongoDB setup on macOS

Use a separate local MongoDB Community instance or an existing dedicated
development database. MongoDB 8.0 is supported. If Docker Desktop is installed
and running, the following creates a local-only development instance with a
persistent named volume:

```sh
docker run --name intellise-c1-mongodb \
  --publish 127.0.0.1:27017:27017 \
  --volume intellise-c1-mongodb-data:/data/db \
  --detach mongo:8.0
```

For later sessions use `docker start intellise-c1-mongodb`. The named volume
retains records across backend and container restarts. `.env.example` supplies
the corresponding local settings:

```dotenv
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=intellise_component_1
```

For a different server, set the URI in the ignored `.env`, then restart the
backend. Never commit real credentials or include URIs in logs. Database names
must be 1–63 ASCII letters/digits/underscores/hyphens, with the first character
a letter, digit, or underscore. Use a database dedicated to this component.
The database user needs read/write and index-creation permissions on it.

The async PyMongo client is created in application lifespan and closed on
shutdown. Audio-job recovery attempts a bounded database operation in a background
startup task; it does not delay health startup. Project operations remain deferred
until requests. A compound
`created_at`/`_id` index is created lazily on the first create or list request
per process. Writes require majority acknowledgement. There is no in-memory
fallback. Missing/invalid URI, unavailable server, permission errors, and
driver failures return a generic HTTP 503 without driver details. MongoDB
failure never changes the health response. Normal application code does not
log connection strings or discussion content.

## Project API and validation

`POST /api/v1/component-1/projects` accepts JSON:

```json
{
  "name": "Client portal",
  "description": "Initial client discussion",
  "discussion_text": "The client described an internal request portal.\nFollow-up discussion remains pending."
}
```

| Input | Rules |
| --- | --- |
| `name` | Required string; 1–120 characters; whitespace-only rejected; leading/trailing whitespace trimmed |
| `description` | Optional string or null; maximum 2,000 characters; omitted becomes null |
| `discussion_text` | Required string; 1–100,000 characters; whitespace-only rejected |
| `transcription_id` | Optional completed transcription UUID; omitted/null retains text-only creation |

Limits count Unicode characters in the submitted strings, before name trimming.
Discussion text is saved without trimming, rewriting, normalizing line breaks,
or processing through AI. Unknown fields, including client-supplied status,
project IDs, model metadata or timestamps, are rejected. Invalid input returns HTTP 422.
With `transcription_id`, discussion text is the user's reviewed draft; it may differ
from the ASR original. The backend validates the stored completed speech job and
saves a provenance snapshot atomically with the project. Missing jobs return 404;
queued/processing/failed jobs and unusable completed results return 409. No project
is inserted on reference-validation failure. See the exact
[provenance request/response and errors](docs/project-transcription-provenance.md).

Example request from another terminal:

```sh
curl --fail-with-body -i \
  -H 'Content-Type: application/json' \
  --data '{"name":"Client portal","discussion_text":"Original client discussion text."}' \
  http://127.0.0.1:8001/api/v1/component-1/projects
```

Successful creation returns **201** with the saved record. Illustrative shape
(ID and timestamps are generated by the service):

```json
{
  "id": "507f1f77bcf86cd799439011",
  "name": "Client portal",
  "description": null,
  "discussion_text": "Original client discussion text.",
  "status": "draft",
  "created_at": "2026-10-09T00:00:00Z",
  "updated_at": "2026-10-09T00:00:00Z"
}
```

IDs are MongoDB ObjectIds serialized as 24-character hex strings. Timestamps
are timezone-aware UTC ISO 8601 strings with BSON millisecond precision.
`created_at` and `updated_at` are equal at creation; this API does not update
projects, discussions, or statuses.

`GET /api/v1/component-1/projects?limit=20&offset=0` returns **200**:

```json
{
  "items": [
    {
      "id": "507f1f77bcf86cd799439011",
      "name": "Client portal",
      "description": null,
      "status": "draft",
      "created_at": "2026-10-09T00:00:00Z",
      "updated_at": "2026-10-09T00:00:00Z"
    }
  ],
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

- Default `limit`: 20; allowed range: 1–100.
- Default `offset`: 0; allowed range: 0–10,000. Invalid values return 422.
- Newest first by `created_at`, with descending `_id` as a stable tie-breaker.
- `discussion_text` is excluded in the MongoDB query and the summary schema.
- `has_more` is calculated using one extra record, with no total-count query.
  Increase offset by limit for the next page within the allowed offset range.
- An empty collection or offset beyond available records returns `items: []`
  and `has_more: false`. Pagination is offset-based, not a snapshot; concurrent
  creations can shift pages. Offset is capped; deeper traversal is not supported.

Retrieve a full record with its original discussion, using an actual returned ID:

```sh
curl --fail-with-body -i \
  http://127.0.0.1:8001/api/v1/component-1/projects/REPLACE_WITH_RETURNED_ID
```

`GET /api/v1/component-1/projects/{project_id}` returns **200** and the same
full-record shape as POST; malformed IDs return **422** and valid-but-missing
IDs return **404** with `{"detail":"Project not found."}`. Valid persistence
requests return **503** when MongoDB is unavailable:

```json
{"detail":"Project persistence is unavailable. Check MongoDB configuration and availability."}
```

There is no authentication. Project create/list/get endpoints do not invoke AI.
Extraction is available through the separate endpoints below.

## Isolated integration tests

Integration tests never use `MONGODB_DATABASE`. Each test generates an
`intellise_c1_test_<uuid>` database on `TEST_MONGODB_URI`, then drops only that
generated database. Use a dedicated local test server/account that permits
creating and dropping these test databases. Without the variable, integration
tests are explicitly skipped; configured but unreachable servers fail tests.

For a running local MongoDB:

```sh
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 python -m pytest
```

These tests verify real creation and retrieval, exact original-text retention,
UTC timestamps, newest-first pagination without discussions, missing IDs, and
persistence after closing the first application lifespan/client and starting
a fresh application/client. The remaining tests cover blanks, input-length
limits, malformed IDs, unavailable database behavior, sanitized errors, and CORS.

## Dependency updates

The lock includes development dependencies and the pinned setuptools build
backend. To intentionally refresh it, use a fresh Python 3.12 virtual
environment, install `setuptools==80.9.0`, then install `-e '.[dev]'` and export
`python -m pip freeze --exclude-editable`. Review the version changes, replace
the pinned lines in `requirements.lock`, and repeat setup and verification.
Do not export unrelated system or other-component packages into the lock.

## Troubleshooting

- **`python3.12: command not found`:** Install Python 3.12 for macOS and open a
  new terminal. Confirm `python3.12 --version` before creating the environment.
- **`No module named intelise_c1`:** Activate `.venv` and repeat the editable
  installation from this directory. Check `which python` points inside `.venv`.
- **Dependency download fails:** Check network access to PyPI and retry the
  locked installation. Do not remove version pins to bypass a download error.
- **Address already in use:** Stop the process using port 8001 or choose a free
  `C1_BACKEND_PORT`. Use that port in health and documentation URLs.
- **Invalid settings:** Check the port range and the CORS JSON array in `.env`.
  Match the browser origin exactly; `localhost` and `127.0.0.1` differ.
- **Connection refused:** Keep the backend terminal running and check startup
  logs, bind host, and port. MongoDB is required for project operations; health
  requires no database or AI service.
- **CORS error:** Add the actual development browser origin to
  `C1_CORS_ORIGINS` and restart. An OPTIONS preflight for an unlisted origin
  returns 400; an ordinary GET remains available without an allow-origin header.
- **Projects return 503:** Confirm MongoDB is running, check the host/port and
  database name, and verify read/write/index permissions. For Docker, inspect
  `docker ps` and `docker logs intellise-c1-mongodb`. For remote MongoDB, check
  network access and URI/TLS settings. Do not paste credential-bearing URIs
  or full discussions into logs. After an invalid/missing URI is corrected,
  restart the backend; transient server outages can recover without a restart.
- **Docker name already exists:** Use `docker start intellise-c1-mongodb`; do
  not delete an existing container or volume containing project data.
- **Database appears empty:** Check `MONGODB_DATABASE` and the server URI match
  the values used when the records were created. Backend restarts do not clear
  MongoDB data. The test suite intentionally uses separate generated databases.
- **Integration tests skipped:** Set `TEST_MONGODB_URI` explicitly. A passing
  health or unit test alone does not establish real persistence.

No shared repository files or other components are required to run this service.

## Source-grounded requirement extraction

Select the provider explicitly in the local ignored `.env`, then restart:

```dotenv
C1_LLM_PROVIDER=ollama
C1_OLLAMA_BASE_URL=http://localhost:11434
C1_OLLAMA_MODEL=llama3.2:1b
C1_OLLAMA_CONTEXT_LENGTH=2048
C1_OLLAMA_MAX_TOKENS=256
C1_LLM_TIMEOUT_SECONDS=60
C1_LLM_MAX_TOKENS=8192
```

Ollama must already be running and the requested model must already be installed.
Inspect installed models with `ollama list` and start the server with `ollama serve`
if needed. Install models manually according to your environment; the application
never downloads models, retries generation, or silently changes providers.
The adapter uses non-streaming `POST /api/chat`, JSON Schema in `format`,
`temperature: 0`, `num_ctx` and `num_predict`. Ollama requests only
`{"quotes": ["exact source statement"]}`; requirement text/evidence reuse those
quotes, actor/action are null, and IDs, offsets and review metadata are generated
in backend code. `C1_OLLAMA_MAX_TOKENS` controls Ollama output independently of
Anthropic's `C1_LLM_MAX_TOKENS`. See the official
[chat API](https://docs.ollama.com/api/chat) and
[structured output documentation](https://docs.ollama.com/capabilities/structured-outputs).
The base URL accepts an HTTP(S) origin without credentials or paths.

The default `C1_LLM_PROVIDER=anthropic` preserves existing external-provider setup.
Set `C1_ANTHROPIC_API_KEY` and `C1_LLM_MODEL` for a model supporting JSON outputs
in your account. It uses HTTPS `POST https://api.anthropic.com/v1/messages`
with `anthropic-version: 2023-06-01` and `output_config.format` JSON Schema.
See [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
Provider clients are created only for extraction requests; health requires neither
provider, credentials, models nor MongoDB.

```sh
curl --fail-with-body -i -X POST \
  http://127.0.0.1:8001/api/v1/component-1/projects/REPLACE_WITH_PROJECT_ID/extractions
curl --fail-with-body -i \
  http://127.0.0.1:8001/api/v1/component-1/projects/REPLACE_WITH_PROJECT_ID/extractions/latest
```

POST reads the project's saved original discussion and returns **201** only
when the entire result has validated and MongoDB acknowledged a new run.
GET latest reads existing runs without contacting a model. Each run contains
`run_id`, `project_id`, `source_discussion_hash` (SHA-256 of unchanged UTF-8
source), `created_at` (UTC, millisecond precision), `provider`,
`model_identifier` (requested model), `prompt_version` (`c1-ollama-quotes-v3` for Ollama, `c1-exact-source-v2` for Anthropic)
and `candidates`. Old runs without `provider` read as `anthropic`, the sole
previous adapter; they are neither rewritten nor revalidated under the new policy.

Candidate fields remain `requirement_id` (server UUID), `requirement_text`,
`evidence` (one or more `{quote, start, end}` spans), nullable `actor`/`action`,
and `review_status: "unreviewed"`. Generated candidates are never client-approved.
The provider wire schema requests quotes without offsets. The backend locates
each exact quote and computes Unicode code point offsets (Python characters,
not UTF-8 bytes or JavaScript UTF-16 units). Start is inclusive, end exclusive.
Repeated identical quotes resolve deterministically to the first occurrence;
this establishes textual traceability, not which utterance the model intended.
Every persisted span must equal `discussion_text[start:end]`, preserving
whitespace, CRLF and Unicode exactly. Actor/action must occur in evidence or be null.

The discussion is JSON source data in a user message, with a separate system
prompt treating embedded instructions as untrusted. The prompt extracts only
explicit software requirements, preserves permissions, prohibitions, negation,
conditions and numeric limits, and excludes greetings and meeting arrangements.
It prohibits inferred features and asks for an empty list when no requirements exist.

The initial policy requires each candidate text to equal one complete supporting
quote exactly. Paraphrasing and rewritten splits are rejected, even beside valid
source evidence. Compound statements may remain combined to preserve wording and
restrictions. Multiple context quotes are retained. Blank text, duplicate candidate
text, missing fields, unknown fields, invalid evidence and malformed output reject
the **whole run** before an insert; no partial candidates are saved. A valid empty
list is saved as a successful run. The supplied booking/admin/search example is
only a test fixture, not a production rule or required candidate count.

### Limits and errors

| Setting / field | Default and bounds |
| --- | --- |
| `C1_LLM_PROVIDER` | `anthropic`; explicit `anthropic` or `ollama` |
| `C1_OLLAMA_BASE_URL` | `http://localhost:11434` |
| `C1_OLLAMA_MODEL` | `llama3.2:1b`; nonblank, maximum 200 characters |
| `C1_OLLAMA_CONTEXT_LENGTH` | 2,048; configurable 512–131,072 tokens |
| `C1_EXTRACTION_MAX_CHARACTERS` | 30,000; configurable 1–100,000; oversized source returns 413 without truncation |
| `C1_LLM_TIMEOUT_SECONDS` | 60; configurable 1–180; whole-operation deadline |
| `C1_LLM_MAX_TOKENS` | Anthropic: 8,192; configurable 256–16,384 output tokens |
| `C1_OLLAMA_MAX_TOKENS` | Ollama: 256; configurable 32–16,384 output tokens |
| `C1_LLM_RESPONSE_MAX_BYTES` | 262,144; configurable 1,024–1,048,576 decoded bytes |
| Candidates per run | 0–100 |
| Requirement text | 1–2,000 characters; nonblank |
| Evidence per candidate | 1–8 quotes, each 1–4,000 characters |
| Actor / action | null or nonblank source substrings, maximum 200 / 500 characters |

Strict Pydantic validation enforces local bounds, including constraints removed
from Anthropic's supported schema subset. Source length is bounded in characters,
not tokens; configure context for the chosen model and discussion size. The compact
2,048/256 defaults target short discussions. Long discussions require deliberate
context/output adjustments; the character limit does not establish token fit, and
Ollama may discard input context without a detectable output stop. Do not treat a
completed response as proof of source completeness. Ollama must return `done: true`
and `done_reason: "stop"`; a missing completion indicator, token-limit stop,
empty output, invalid JSON/schema, oversized response or failed evidence validation
returns **502** with no insert. Anthropic must return one text block and `end_turn`.
Ollama unavailable, missing requested model/endpoint (404), rejected requests and
external-provider configuration failures return **503**; generation timeouts return
**504** and are never automatically retried. Error details give checks to perform
without echoing credentials, discussions, provider bodies or driver details.
MongoDB write/index failures return **503** via the existing sanitized handler.
Malformed project IDs return **422**, missing projects/runs return **404**.

Runs remain append-only in `extraction_runs`, with majority writes, a unique
`run_id` index and `(project_id, created_at, _id)` latest ordering. Projects,
original discussions and existing successful runs are never updated by extraction.
Repeated POSTs create separate runs; concurrent requests may finish out of order.
An ambiguous network/write failure may reach MongoDB despite a 503; no automatic
retry or idempotency token is provided. Failed validation never issues an insert.

### Verification and research limits

Run from `component-1/backend`:

```sh
.venv/bin/python -m pytest tests/test_extractions.py tests/test_ollama_extraction.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
# Optional single live generation: real adapter, supplied synthetic discussion, no DB write.
C1_OLLAMA_BASE_URL=http://localhost:11434 C1_OLLAMA_MODEL=llama3.2:1b \
  .venv/bin/python scripts/smoke_ollama.py
```

The smoke script ignores `.env`, reads environment overrides, prints the actual
bounded model response, validation result and elapsed seconds, and exits nonzero
for unavailability, invalid output or disagreement with the fixture. It performs
one request, never downloads a model and never persists results. It reports source
validation separately from the fixture's relevance/completeness comparison. The
malformed `We will meet onFriday.` fails evidence matching without repair; exact
`We will meet on Friday.` passes source checks but fails the fixture evaluation.
An exact meeting quote can therefore still be saved as unreviewed; the prompt
excludes it, but the backend does not claim a general semantic relevance validator. Its source and
expected count live only in this separate verification script and tests.

Automated provider responses are mocked: passing them verifies application behavior,
not model performance or accuracy. Tests cover the booking/admin/search regression,
meeting exclusion in the mocked fixture, fabricated text with real quotes, permissions,
negation, duplicates, Unicode offsets, empty extraction, errors/timeouts/truncation,
provider configuration, old-run compatibility and preservation of successful runs.
Optional real MongoDB tests use isolated disposable databases and mocked generation,
as described above. See [extraction verification report](docs/extraction-verification.md)
for the actual checks and live result from this change.

Exact quotes provide traceability but do not prove extraction completeness,
relevance, correct context selection or semantic correctness. A model may omit
requirements, select a nonrequirement sentence, or quote only part of a restriction;
these still require evaluation and human review. Temperature zero and structured
JSON do not guarantee faithful extraction. This policy disallows rewritten splits
and paraphrases; any future support needs separate evaluation and full contextual
evidence while remaining explicitly unreviewed. No research accuracy claim is made.

## Initial FR/NFR baseline

See [research/README.md](research/README.md) for dataset provenance and annotation
requirements, exact preparation/training/freeze/evaluation commands, algorithm,
trusted local model loading, classification API contract and future BERT work.
This baseline uses **TF-IDF + logistic regression**, not BERT. No suitable real
labeled dataset was found; the tiny test-only fixture cannot be used for research
training or served by the API. Research metrics remain unavailable.

Classification is separate from extraction and operates on a saved run:

- `POST /api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications`
- `GET /api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications/latest`

Install the optional `requirements-baseline.lock`, prepare genuine reviewed
labels with canonical source groups, train offline, then explicitly configure
`C1_CLASSIFIER_MODEL_DIR` to your operator-trusted local artifact directory.
The DCAI baseline uses the existing loader and is configured in the ignored local
`.env`; the example keeps model configuration explicit. Missing/invalid models
return 503; health still works without a classifier.
Previous classification runs and original extraction text/evidence/status are
preserved. Predictions contain FR/NFR labels without probability scores or an
approval claim. Nothing trains automatically on API startup.

## Local baseline artifacts and persistence troubleshooting

See [local model storage and reproducibility](research/local-artifacts.md),
[aggregate DCAI run identities and metrics](research/dcai-v1-summary.json), and
[the sanitized MongoDB diagnosis](research/mongodb-diagnosis.md). Datasets,
row-level reports and learned binaries remain local under the existing research
ignore rules; no redistribution permission is asserted.

### Reviewed classification labels

Saved FR/NFR predictions can now receive explicit, append-only human label reviews.
The original prediction remains unchanged. Reviews retain model/run identity,
source/text hashes, self-reported reviewer and timestamp; new extraction or
classification runs have separate reviews. No automatic retraining or client
approval occurs. Start the normal backend with `python -m intelise_c1` (restart
an existing process to load routes). See [label-reviews.md](docs/label-reviews.md)
for HTTP contracts, UI steps and isolated MongoDB verification commands.

### Dashboard project deletion

`DELETE /api/v1/component-1/projects/{project_id}` removes a project from listing
and normal retrieval, retaining source/audio/run/review records for recovery.
This is soft deletion rather than permanent data erasure. Repeated explicit
DELETE requests are idempotent (204). Restart the normal backend to load the new
route. See [project-deletion.md](docs/project-deletion.md) for behavior, errors,
isolated MongoDB tests and limitations.

## SRS drafts and client review (phase 1)

The normal backend now includes template-based SRS drafts from classified
saved requirements with optional human corrections, individual or bulk client decisions, explicit versioned revisions and approval
of an exact version. MongoDB retains history separately from source records and
FR/NFR label reviews. Client names are self-reported; no LLM/RAG generation or
Agile artifacts are claimed. See [API, limits and verified results](docs/srs-client-review.md).
