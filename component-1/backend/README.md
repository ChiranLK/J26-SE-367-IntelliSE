# Component 01 backend

Component 01 is the AI-Powered Intelligent Requirement Engineering Agent for
Agile Software Development in the IntelliSE fourth-year research project.
The proposed 50% prototype deadline is October 18, 2026. This directory provides
the backend foundation only; it does not represent the completed prototype.

## Current behavior

FastAPI serves an availability response, project creation/list/retrieval,
interactive API documentation, and configurable development CORS origins.
Projects and their original client discussions are persisted in MongoDB.
The health endpoint works
without MongoDB, an LLM API key, downloaded models, or any external service.
It confirms application availability only, not database or AI readiness.

Requirement extraction, FR/NFR classification, quality
validation, RAG, LangGraph, audio processing, and SRS generation remain future
work. No frontend or research results are included.

## macOS setup

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
shutdown. Network access is deferred until a project request. A compound
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

Limits count Unicode characters in the submitted strings, before name trimming.
Discussion text is saved without trimming, rewriting, normalizing line breaks,
or processing through AI. Unknown fields, including client-supplied status,
IDs, or timestamps, are rejected. Invalid input returns HTTP 422.

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

There is no authentication, AI processing, extraction, classification,
quality validation, or artifact generation in these endpoints.

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
