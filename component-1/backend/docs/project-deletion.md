# Project deletion — retained records

The normal backend startup now exposes:

`DELETE /api/v1/component-1/projects/{project_id}`

- 204, empty body: project hidden from dashboard/listing and normal retrieval.
- Repeating DELETE for the same retained project also returns 204.
- 422: project ID is malformed (must contain 24 hexadecimal characters).
- 404: no project with that ID exists, including retained deleted records.
- 503: persistence unavailable; existing sanitized error handling applies.

CORS now permits DELETE alongside the existing GET/POST methods for configured
origins. No provider or model needs to be available to delete a project. Health
remains available when database access fails.

This is **soft deletion, not permanent erasure**. A single atomic MongoDB
`update_one` sets `deleted_at` only if it is absent. Active project listing and
retrieval exclude records with that field; downstream extraction/classification/
review APIs already scope their access through active project retrieval and thus
return 404 for deleted projects. Existing undeleted documents require no migration.
The first deletion timestamp is preserved on an explicit retry. Existing public
creation/list/detail response schemas remain unchanged.

Source text, provenance snapshots, extraction runs, classifications and label-review
history are retained. Completed transcription jobs are unchanged and may be shared
by other projects. No cascade purge occurs, so provenance is not left pointing to
a deleted transcription. In-flight generation that obtained its source before
deletion may still finish and append retained history, but normal project/run APIs
continue hiding that deleted project. This local prototype does not introduce a
restore UI or permanent-purge API; recovery requires a deliberate operator action.
The endpoint uses the same access model as the existing local project APIs.

No actual client project was deleted during verification. Tests generate isolated
`intellise_c1_test_*` databases and drop only those test databases afterward.

```sh
.venv/bin/python -m pytest -q
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 .venv/bin/python -m pytest -q -m integration
```

Measured October 19: 309 tests passed, 13 integration tests skipped without the
explicit test URI. With the URI, all 13 integration tests passed. Actual MongoDB
checks verified deletion across application restart, retained source/provenance/
job/run/review records, idempotence and another unaffected project. ASR, extractor
and classifier outputs in those tests were mocked; persistence and application
routes/validation were real. One pre-existing Starlette/httpx deprecation warning
remains. No dependencies or model artifacts changed for this feature.

Restart `python -m intelise_c1` (or the normal root `./start-component-1` launcher)
to load these routes. An already-running older backend may return 405. The frontend
reports this rather than pretending deletion succeeded. Do not test by deleting
existing client projects. The OpenAPI schema at `/openapi.json` includes the route.
