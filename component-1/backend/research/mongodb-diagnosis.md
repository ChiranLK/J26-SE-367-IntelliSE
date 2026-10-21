# MongoDB project persistence diagnosis

This is a sanitized historical account of the October 14, 2026 local diagnosis,
not a current readiness or live-model performance claim. The original detailed
report remains in the local source copy and verified organization backup.
No private client text, credentials, user filesystem paths or process IDs are
included here.

## Demonstrated cause and fix

The ignored local backend configuration had no MONGODB_URI key, and no MongoDB
listener was available at the documented localhost target. An unset URI deliberately
leaves project persistence unconfigured; the API's generic 503 does not establish
an Atlas authentication problem. No configured Atlas target was demonstrated.

The explicitly tested local target failed a bounded ping in 2.027 seconds with
sanitized category connection_refused. After starting Docker Desktop, creating
the documented local MongoDB service and adding the missing local configuration,
the bounded ping passed in 0.027 seconds. Existing classifier configuration was
preserved. There was no application repository/API defect to fix, storage mock,
in-memory substitution, data reset or provider fallback.

Example local settings, without credentials:

```dotenv
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=intellise_component_1
```

Run from this backend directory because .env resolves from the working directory.
Reuse the documented container with `docker start intellise-c1-mongodb`; create it
using the backend README only when absent. Keep its named data volume. Restart
the backend after correcting a missing/invalid URI. An already configured backend
can recover from a transient MongoDB outage without replacing records.

## Historical verification and current procedure

Real MongoDB integration checks passed: 6 tests in 2.18 seconds. Each used a
generated disposable database. Project create/list/retrieve and controlled-restart
persistence passed. Extraction/classification persistence cases used explicitly
mocked model outputs with real storage; they do not establish live model quality.
After repair, health and project listing returned 200 with an empty project list.

At that diagnosis, no valid saved extraction existed in the application database,
so live classification for an actual saved run remained blocked. No fake extraction
was inserted to bypass evidence validation. Later work must report its own checks.

Use the full component-1-backend checkout and its documented normal startup.
Historical temporary operational source snapshots are not startup instructions.
Health is availability only, not MongoDB/model readiness; background audio recovery
may now attempt bounded database work independently of project requests.

```sh
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 \
  .venv/bin/python -m pytest tests/test_projects_integration.py -q
```

Use only a dedicated test target; the fixture creates/drops its own databases.
Never print .env, secret-bearing URIs, driver exception messages or discussions.
Classify only a valid saved extraction through the existing API, and report
source validation, model inference and storage verification separately.
