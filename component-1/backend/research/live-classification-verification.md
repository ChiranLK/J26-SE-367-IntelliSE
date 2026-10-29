# Running application and MongoDB verification — October 14, 2026

Status: **blocked at database access**. The backend at `http://127.0.0.1:8001`
is running, but live FR/NFR classification and persistence have not been verified.
No existing client record was modified. No extraction was fabricated, inserted
through database code, or created using a substituted provider. No frontend change,
commit or push was made.

## Actual running routes and requests

`GET http://127.0.0.1:8001/openapi.json` returned **200**. The actual route set is:

| Method | Route |
| --- | --- |
| GET | `/api/v1/component-1/health` |
| POST, GET | `/api/v1/component-1/projects` |
| GET | `/api/v1/component-1/projects/{project_id}` |
| POST | `/api/v1/component-1/projects/{project_id}/extractions` |
| GET | `/api/v1/component-1/projects/{project_id}/extractions/latest` |
| POST | `/api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications` |
| GET | `/api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications/latest` |

There is **no manual requirement-entry endpoint**, extraction-upload endpoint,
project-delete endpoint or classifier-readiness endpoint in the observed OpenAPI.
Classification takes no request body and requires an actual saved extraction UUID
scoped to an actual project ObjectId. No POST was attempted against client records.

`GET http://127.0.0.1:8001/api/v1/component-1/health` returned **200**:

```json
{"status":"ok","component":"component-1","service":"requirement-engineering"}
```

`GET http://127.0.0.1:8001/api/v1/component-1/projects?limit=100&offset=0`
returned **503**:

```json
{"detail":"Project persistence is unavailable. Check MongoDB configuration and availability."}
```

The initial sandboxed OpenAPI connection was blocked; approved local access
returned the responses above. These observations distinguish sandbox connectivity
from the application's actual MongoDB failure.

## Configuration and model checks

Inspected Settings, the MongoDB lifespan, classification routes, artifact loader,
and the documented isolated integration fixture. Credentials/connection strings
from local configuration were never printed.

Local Settings loaded from the backend directory reported:

- MONGODB_URI: unset/empty; no database credentials were displayed.
- MONGODB_DATABASE: `intellise_component_1`.
- MongoDB connection/operation timeout: 2,000 ms.
- TEST_MONGODB_URI: initially unset.
- C1_CLASSIFIER_MODEL_DIR: the previously selected `research/models/dcai-v1/lr-c10`
  directory, with its pipeline present.
- Current local extraction provider: Anthropic, with neither credentials nor a
  requested Anthropic model configured. Provider selection was not changed.

These are local Settings observations, not a claim to have read the running
process's private environment. The running API's own 503 confirms that its
persistence is unavailable.

The configured model was successfully loaded locally through the existing
restricted artifact loader. Its hash/type/dependency/Python checks passed:

- Identifier: `tfidf-logistic-regression`.
- Model version:
  `b48d2a3a87e3669957a1c5374c8879cd84fc1fe232e002a1c50c9821cb693823`.
- Purpose: research.
- Evaluation method: `stratified_normalized_text_holdout`.

This establishes artifact availability locally. It **does not establish loading
inside the running application**: classification reads MongoDB before invoking the
lazy classifier, and no valid saved extraction could be retrieved.

## Real MongoDB integration run

A read-only ping of the documented local test server at `127.0.0.1:27017` failed
with ServerSelectionTimeoutError. Driver error details were suppressed.

Then ran the documented isolated configuration explicitly, without falling back to
application storage:

```sh
cd component-1/backend
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 \
  .venv/bin/python -m pytest tests/test_projects_integration.py -q --tb=no
```

Actual result: **6 setup errors, 0 passed, 13.23 seconds**, plus the existing
Starlette/httpx deprecation warning. These are errors with a configured unreachable
server, not skipped or successful tests. Each fixture generates an
`intellise_c1_test_<uuid>` database name, pings before application setup, and cleans
up only that generated database after a successful connection. No fixture reached
database writes or cleanup drops because every connection ping failed.

The affected tests are:

- `test_create_and_retrieve_original_discussion`
- `test_paginated_newest_first_listing`
- `test_nonexistent_id`
- `test_persistence_across_application_restart`
- `test_extraction_runs_persist_across_restart`
- `test_classification_runs_survive_restart_without_model`

The existing extraction/classification persistence tests use mocked generation and
mocked classifier responses with real MongoDB. Even when they pass, they establish
persistence mechanics rather than live model extraction or real-artifact inference.
Their controlled restart closes the first application lifespan/client and creates
a fresh application/client against the same generated database. No restart check
could execute in this run. The user's running process was left running.

## Requested checks and blockers

| Check | Actual outcome |
| --- | --- |
| Running API available and routes inspected | Passed: health/OpenAPI 200 |
| Configured artifact loads locally | Passed |
| Model loads through running application's classification request | Blocked by MongoDB access |
| Valid saved extraction available | Not established; projects cannot be listed/retrieved |
| Predictions map to actual saved requirement IDs | Not tested live |
| Classification has correct model/run identity | Not tested live |
| Classification written to and retrieved from real MongoDB | Not tested live |
| Retrieval after controlled restart | Not tested; integration setup failed |
| Manual-entry alternative | Absent from actual OpenAPI |

Do not interpret the database failure as proof that no extraction exists. The
blocker is that no valid saved extraction can be obtained while persistence is
unavailable. There is no authorized API route for entering one manually. Existing
collection-double results remain historical mechanical checks, not live evidence.

## Exact next action

Start or restore the intended MongoDB server and configure its URI in the ignored
backend `.env` locally, then restart the backend from `component-1/backend` with:

```sh
.venv/bin/python -m intelise_c1
```

Use the intended server/database containing real existing records; do not change
to an arbitrary empty database and claim those records disappeared. Keep credentials
local. For the documented local MongoDB setup, the URI is
`mongodb://127.0.0.1:27017`; research/README.md and the backend README describe setup.

Once `GET /api/v1/component-1/projects` returns 200, find a valid saved extraction.
Use an isolated test database/application or a clearly identified disposable project
for writes. If no valid extraction exists, stop and report that blocker; there is
no manual entry route and validation must not be bypassed. A real extraction requires
an explicitly configured, available provider and successful source validation.

Rerun the isolated integration command above against a dedicated available test
server. Then classify an actual saved extraction, compare every prediction's
requirement_id with that run's candidates, record the model/run identities and
MongoDB acknowledgement, GET the result, perform a controlled restart, and GET the
same classification again. Preserve client records and report any cleanup separately.

## Evaluation limitation remains

The DCAI model's prior measured test macro-F1 is 0.904070 under an explicit
within-corpus normalized-text holdout, not project-separated evaluation. Project IDs
were unavailable. Duplicate normalization prevents identical requirements crossing
splits but cannot establish unseen-project performance or eliminate paraphrase
leakage. Persistence/model-load checks do not validate label correctness, extraction
relevance or completeness, and never make a candidate client-approved.
