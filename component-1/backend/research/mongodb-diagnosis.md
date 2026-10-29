# MongoDB 503 diagnosis and real persistence verification — October 14, 2026

**Project listing is restored: HTTP 200.** The demonstrated causes were missing
local configuration and an absent local MongoDB listener. No API/repository code
change, mock database, in-memory fallback, data reset or provider substitution was
used. No frontend files were modified and nothing was committed or pushed.

## Inspection and demonstrated cause

The active checkout is `component-1-frontend`. Root/backend README instructions,
Settings, database lifespan, repository methods, exception handling and integration
fixtures were inspected. No applicable AGENTS.md was found. The full backend's
files were also read from `component-1-backend` without switching branches.

Before the fix, backend Settings loaded from `component-1/backend` showed:

- `.env` existed, but had **no MONGODB_URI key**.
- No process-environment override was present in the diagnostic process.
- Effective MongoDB URI was unset, so no local or Atlas target was configured.
- Database default: `intellise_component_1`; driver operation/connect timeout: 2,000 ms.
- The existing classifier directory setting was retained.

The lifespan deliberately leaves `application.state.projects` unset when URI is
missing/blank. `get_project_repository` immediately returns the existing sanitized
503 in that case. With a configured URI, networking is deferred until repository
requests; MongoDB connection/index/write errors also use the generic 503 handler.
Health does not test database readiness. No defect in those semantics was demonstrated.

Actual requests before repair:

| Request | Status / observed result |
| --- | --- |
| GET `/openapi.json` | 200; seven paths, including extraction/classification |
| GET `/api/v1/component-1/health` | 200; standard availability response |
| GET `/api/v1/component-1/projects?limit=1` | 503; persistence unavailable |

The project's documented development target was tested explicitly, not inferred
from an unavailable Atlas URI. A bounded ping to localhost:27017 failed after
**2.027 seconds**, with ServerSelectionTimeoutError and sanitized underlying
category **connection_refused**. Neither credential strings nor driver messages
were printed. No Atlas authentication/network-list diagnosis is claimed.

`mongod` was not installed on PATH or in the checked Homebrew MongoDB locations.
Docker Desktop was installed, but its daemon socket was absent. Once Docker Desktop
started, inspection found no existing containers.

## Fix performed

1. Added only the missing local key to the ignored backend `.env`:
   `MONGODB_URI=mongodb://127.0.0.1:27017`. Other settings were preserved.
2. Started installed Docker Desktop with approval.
3. Created the existing README's local-only MongoDB 8 setup, with approval:

   ```sh
   docker run --name intellise-c1-mongodb \
     --publish 127.0.0.1:27017:27017 \
     --volume intellise-c1-mongodb-data:/data/db --detach mongo:8.0
   ```

   The initial image download took substantial time; it eventually completed.
   Its digest was
   `sha256:6657bf2413fefc5be649390318f5b4cd7328e982722f8ce2ac6dfa6f0a42cb03`.
   The named volume was not deleted or reset. Only localhost exposes the database.
4. Repeated the bounded ping after service startup: **passed in 0.027 seconds**.
   Read-only counts showed no projects, extraction runs or classification runs in
   the configured application database.
5. Performed an approved controlled backend restart so the missing URI correction
   was read at startup. The original listener was stopped gracefully; the replacement
   process is PID **11641**, serving `http://127.0.0.1:8001`.

The currently checked-out frontend branch contains an older project-only backend.
Restarting that source would remove the existing extraction/classification routes.
To preserve them, an immutable snapshot of `component-1-backend` commit
`ab157127700207c55e088feefa91f909d6a98e2d` was extracted to:

`/private/tmp/intellise-c1-mongo-mxwfm2no/component-1/backend`

No checkout, merge or implementation rewrite occurred. The running replacement
uses this full backend's src through PYTHONPATH, the existing Python environment,
and the original backend directory's corrected `.env`. The existing model path
was not changed. Keep this snapshot until the backend is launched from an equivalent
full backend source checkout; it is a temporary operational source location.

## Real-MongoDB verification

Ran the full backend's documented integration suite against actual MongoDB:

```sh
cd component-1/backend
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 \
  PYTHONPATH=/private/tmp/intellise-c1-mongo-mxwfm2no/component-1/backend/src \
  .venv/bin/python -m pytest \
  /private/tmp/intellise-c1-mongo-mxwfm2no/component-1/backend/tests/test_projects_integration.py \
  -q --tb=no
```

Actual result: **6 passed in 2.18 seconds**, with the existing Starlette/httpx warning.
Each fixture generated a separate `intellise_c1_test_<uuid>` database and dropped
only that test database on completion. The configured application database was never
used for test creates or cleanup.

Verified against real MongoDB:

- Project POST returned **201**, producing a MongoDB ObjectId and UTC timestamps.
- Project GET returned **200** and the exact saved original discussion; no client
  discussion was printed in diagnostic output.
- Paginated project GET returned **200**, correct newest-first ordering, bounded
  pages and no discussion field in summaries.
- A missing ObjectId returned **404**.
- A created project remained retrievable after closing the first application/client
  and starting a fresh application/client against the same isolated database.
- Extraction/classification run persistence and retrieval across the same controlled
  lifespan restart passed using the suite's **mocked extraction provider/classifier**.
  Storage was real MongoDB, never a collection double or in-memory replacement.

The last tests establish append-only storage/restart mechanics, not actual model
extraction quality or inference by the trained DCAI artifact. Their valid synthetic
fixtures exist only in generated disposable databases and were cleaned up. They
were not copied into the application database or presented as real client records.

## Running application after restart

Actual post-restart responses:

`GET /api/v1/component-1/health` — **200**:

```json
{"status":"ok","component":"component-1","service":"requirement-engineering"}
```

`GET /api/v1/component-1/projects?limit=20&offset=0` — **200**:

```json
{"items":[],"limit":20,"offset":0,"has_more":false}
```

`GET /openapi.json` — **200**; seven paths remain, including:

- POST `/api/v1/component-1/projects/{project_id}/extractions`
- GET `/api/v1/component-1/projects/{project_id}/extractions/latest`
- POST `/api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications`
- GET `/api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications/latest`

These are actual application responses after the environment/service repair, not
mocked success. Listing may create the existing lazy index in the empty application
project collection; no existing client record was changed.

## Remaining blocker and next actions

The configured local application database contains **no valid saved extraction
records**. Live classification with the trained model and retrieval for an actual
saved extraction therefore remain unverified. No manual requirement-entry route is
available, and no synthetic/fake extraction was inserted to bypass source validation.
No model or provider fallback was selected.

Create a clearly identified disposable project through the normal project API,
then obtain a valid saved extraction through the explicitly configured provider and
existing evidence validation. Only then classify the saved run, compare prediction
requirement IDs and model/run identities, and retrieve its saved classification.
If the intended records actually live on another MongoDB server, supply that intended
URI locally and verify it before changing targets; this empty local database is not
proof those remote records do not exist. No remote target was supplied or replaced.

For later sessions, start Docker Desktop, then:

```sh
docker start intellise-c1-mongodb
```

The volume retains data across container/application restarts. Do not remove it.
To restart the current full backend, stop the current server gracefully first,
then run from the existing backend directory:

```sh
PYTHONPATH=/private/tmp/intellise-c1-mongo-mxwfm2no/component-1/backend/src \
  .venv/bin/python -m uvicorn intelise_c1.main:app --host 127.0.0.1 --port 8001
```

For durable development, run an equivalent `component-1-backend` source checkout
separately from the frontend source checkout, with its own local configuration.
No branch integration or push was performed as part of this diagnosis.

The prior trained baseline remains TF-IDF/logistic regression, evaluated using an
explicit within-corpus normalized-text holdout rather than genuine project separation.
Restored persistence does not establish unseen-project accuracy, extraction relevance,
completeness or client approval; evaluation macro-F1 is not individual confidence.
