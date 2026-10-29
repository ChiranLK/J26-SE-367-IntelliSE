# Reviewed FR/NFR labels

This additive API records explicit human feedback on saved classification runs.
It does not change prediction labels, extracted text, project discussions,
requirement `review_status`, training artifacts or evaluation metrics. The normal
`python -m intelise_c1` startup includes these routes. No new dependencies,
credentials or external providers are needed. Restart an older running process
to load the updated routes.

## HTTP contract

Prefix: `/api/v1/component-1/projects/{project_id}/extractions/{run_id}/classifications/{classification_id}`.
Project IDs are 24 hexadecimal characters; run/classification IDs are UUIDs.

- `POST /requirements/{requirement_id}/reviews`: 201 for a new append-only review;
  200 when the identical submission was already saved. JSON body:

```json
{
  "submission_id": "73dd9657-d74d-4341-869e-aa760f552966",
  "reviewed_label": "FR",
  "reviewer_id": "Research reviewer",
  "note": "Password reset is a user-facing function."
}
```

Generate a fresh submission UUID for each intentional save. Keep that same UUID
and payload for an explicit retry after an uncertain response. Do not automatically
retry. A reused UUID with changed payload or scope returns 409. The unique MongoDB
index also prevents concurrent submissions of the same UUID from appending twice.
`reviewer_id` is required, trimmed, 1–120 characters; `note` defaults to empty and
is limited to 2,000 characters; `reviewed_label` is FR or NFR. Extra fields are
rejected, including client-supplied model metadata. There is no authentication in
this local prototype: reviewer identity is explicitly self-reported.

- `GET /reviews`: 200 with `project_id`, `extraction_run_id`, `classification_id`
  and `reviews` (latest review per requirement in that exact run). An empty list
  means no reviews, not an unavailable API. Earlier review history remains stored.

Each returned review contains `review_id`, `submission_id`, the four scoped IDs,
`original_prediction`, `reviewed_label`, `reviewer_id`, `note`, `reviewed_at` (UTC),
`model_identifier`, `model_version`, `source_discussion_hash`,
`requirement_text_hash` (SHA-256 of exact UTF-8 candidate text),
`review_status: "user_reviewed"` and
`reviewer_identity_status: "self_reported"`. Model metadata, original prediction,
source/text hashes and timestamp come from backend records/code. These hashes
bind the review to saved text; they do not prove the label is correct.

404 means a referenced project/extraction/classification/requirement does not
exist in the supplied scope. 422 means malformed IDs, invalid label or invalid
input fields. 409 also covers inconsistent saved classification mappings.
503 means database unavailability or invalid saved data; errors do not expose
credentials or source text. Unsupported old backends return 404; clients must not
pretend a review was saved. Reads remain usable without a loaded classifier.

## Persistence and UI

The new `classification_reviews` collection uses majority writes and append-only
history. Existing collections are read, not rewritten. Latest-per-requirement
selection uses server timestamps with MongoDB ObjectId as a tie-breaker. A later
classification/extraction has a separate scope: old reviews are retained but not
automatically transferred. Stored mapping, hashes and model identity are checked
on retrieval. The frontend also checks these before displaying a review.

The saved-project interface shows model predictions and reviewed labels
separately. Enter reviewer ID, select label, optionally explain, and Save review.
Reopen/refresh to retrieve it. There is no automatic model retraining, client
approval or independent verification. Future exports/training need annotation
review, deduplication and strict separation from validation/test data. The existing
within-corpus evaluation limitation remains unchanged.

## Verification and exact commands

Run from the backend worktree's `component-1/backend`:

```sh
.venv/bin/python -m pytest -q
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 .venv/bin/python -m pytest -q tests/test_projects_integration.py
```

The integration fixture creates and drops only generated `intellise_c1_test_*`
databases. Never point it at an existing application database by editing the
fixture. The URI shown is the local test MongoDB instance; use your isolated test
server URI if different, without exposing credentials in reports.

Measured October 18, 2026: the final full backend suite passed 305 tests with
12 integration tests skipped without TEST_MONGODB_URI. Seven real-MongoDB project,
extraction, classification and label-review tests passed when the URI was supplied.
Included review regression tests cover concurrent duplicate-key handling and
latest-per-requirement selection. One existing Starlette/httpx deprecation warning
remains; no dependencies were changed for this feature.

The new real-MongoDB review check created a disposable project via POST (201),
a valid extraction via POST (201), a classification via POST (201), then a review
via POST (201). Repeating that submission returned the identical record (200).
GET reviews returned the saved original NFR and reviewed FR. A newer classification
returned no reviews. Closing that application lifespan and opening a new app with
the same test database preserved the exact review (GET 200) and idempotent replay
(POST 200). The original discussion/extraction stayed unchanged. Collection counts
were 1 review, 2 classifications and 1 extraction before fixture cleanup.
Extraction/classifier outputs were mocked at provider boundaries; MongoDB and
application route/validation/persistence were real. This is not an accuracy result
and does not verify a production deployment or change any existing client record.

Frontend verification: 88 unit tests passed, lint/build passed, Chrome UI fixture
workflow passed, separate live existing-classifier browser check passed. Live
Azure transcription was not run for this feature.
