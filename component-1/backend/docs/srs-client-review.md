# SRS draft and client review — phase 1

Implemented on 2026-10-20. This is a deterministic requirement-focused SRS
snapshot, not a complete standards-compliant SRS, an LLM/RAG validation system or
Agile artifact generator. No provider calls, training or dependency changes occur.
The normal `python -m intelise_c1` startup includes the SRS routes.

## Workflow

1. Save an extraction and classification through the existing APIs.
2. Model FR/NFR labels are used by default. Save human corrections only where
   needed. A saved correction takes priority; unchanged predictions are not
   misrepresented as human-reviewed. This remains distinct from client acceptance.
3. Generate an SRS draft from the explicit extraction/classification identities.
   The server retrieves project metadata, source hash, exact original wording and
   model predictions and any validated label reviews. No client-supplied model metadata or inferred scope.
4. Record exceptions with request changes / needs clarification. Explicitly
   **Accept remaining requirements** in one confirmed action for pending items,
   or save individual accept decisions if desired.
   A change/clarification requires a comment. Latest decision per requirement
   governs approval; earlier decisions remain in the feedback history. Bulk
   acceptance never overwrites existing change/clarification decisions and never
   approves the document automatically.
5. An analyst can explicitly revise text or label with a reason. A new version
   preserves source IDs/original text and earlier versions. New wording is marked
   an authored revision, not verified source evidence. All decisions reset.
6. Approve the latest version only after every included requirement is accepted
   and the reviewer explicitly confirms. The approval stores the version content
   SHA-256 and timestamp. Approved versions are frozen; future changes create a
   new draft without invalidating the historical approval of the older version.
7. Read historical versions or download a selected SRS as JSON/text. Existing
   minimal requirement exports remain unchanged.

Reviewer/client names are **self-reported**. There is no authenticated client
portal or role enforcement. A name does not independently establish identity.
A generated draft is never automatically approved. Label corrections and client
feedback do not retrain the classifier.

## API contract

Prefix: `/api/v1/component-1/projects/{project_id}/srs`.

- `GET ""`: saved aggregate, or `{schema_version:"c1-srs-v1",project_id,revision:0,versions:[]}`.
- `POST ""`: initial draft from reviewed source. Body:
  `submission_id` UUID, `expected_revision:0`, `reviewer_id`,
  `extraction_run_id` UUID, `classification_id` UUID.
- `POST /feedback`: common fields `submission_id`, `expected_revision`,
  `reviewer_id`, plus `version_id`, `requirement_id`,
  `decision` (`accepted`, `request_changes`, `needs_clarification`), `comment`.
- `POST /accept-remaining`: common fields plus `version_id` and `confirm:true`.
  Atomically accepts only requirements without a saved decision, preserving all
  existing exceptions. No pending items returns 409.
- `POST /revisions`: common fields plus `base_version_id` and nonempty `changes`.
  Each change has `requirement_id`, `text`, `label` (`FR`/`NFR`), `reason`.
- `POST /approval`: common fields plus `version_id` and `confirm:true`.

Every successful call returns HTTP 200 and the current SRS aggregate. It contains
`schema_version`, `project_id`, monotonic `revision`, and `versions`. A version
contains its UUID/number/parent, project title/description, source run IDs/hash,
created timestamp/author, generation method, status, content hash, requirements,
feedback history and optional approval. Requirements retain original wording,
source text hash and nullable label-review ID (null means model prediction).
New snapshots use `classified-requirements-template-v2`. Existing v1 snapshots
remain readable and their content hashes are unchanged. Internal submission receipts are excluded.
See `srs-openapi.json` (only SRS routes and referenced schemas).

Errors: 422 invalid request; 404 project/source record absent; 409 empty source, stale revision/version, reused submission with different payload,
invalid transition, missing feedback comment, no-op/unknown/duplicate changes,
unaccepted requirements or bounded-history limits; 503 unavailable MongoDB or
invalid/corrupt saved SRS. Source extraction/classification context validation
continues to use its existing error contract.

## Atomic storage and concurrency

MongoDB collection `srs_projects` contains one aggregate per project, with `_id`
set to the project ID. Each action uses a compare-and-swap on `revision`; feedback,
receipts, approval and snapshots are saved in one atomic document operation with
majority write concern. Competing stale writers receive 409. A failed write never
replaces earlier valid content. Submission UUID + canonical request hash allow
safe explicit replay; reuse with different content is rejected. A retry can
return the subsequently updated aggregate, not necessarily the first response.
There are no automatic retries. The UI blocks new mutations after an uncertain
write until the same action is explicitly retried/resolved.

Content hashes cover immutable version content and source identities, excluding
mutable feedback/status/approval. Hashes and approval consistency are validated
on retrieval. SHA-256 provides integrity checking, not authenticated signatures.
Original project/extraction/classification/label-review/transcription records are
never rewritten. Existing soft deletion hides project SRS access but retains
history. Limits: 20 versions, 500 feedback events per version, 1,000 total actions,
and a 4 MB encoded aggregate. Limits return actionable conflicts, preserving data.

## Current limits and next phase

- Only existing requirements can be revised; additions/removals and rebasing a
  newer extraction are not implemented. Later extraction/label edits do not
  silently update the SRS snapshot.
- The UI revises one requirement per new version; the API supports multiple.
- All approvals/acceptances reset on revision, including unchanged requirements.
- No semantic validation, completeness guarantee, automatic requirement repair,
  stories, acceptance criteria or affected-artifact regeneration yet.
- No UML/code/testing service is invoked. Exports provide a manual handoff.
- Existing baseline evaluation remains within-corpus; the GPA demo or SRS tests
  do not establish new accuracy or research novelty.

Next phase: source-linked draft user stories and acceptance criteria, clearly
marking proposed/inferred behavior for human confirmation and versioning artifacts
against their source SRS before adding selective regeneration.

## Verification commands

From this backend worktree's `component-1/backend`:

```sh
.venv/bin/python -m pytest tests/test_srs.py -q
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 .venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

MongoDB tests use newly generated `intellise_c1_test_<uuid>` databases, then clean
only those test databases. Never use the application database as a test target.

Actual results: **330 backend tests passed**, including real MongoDB tests. SRS
checks include initial draft, all-reviewed gating, source preservation, feedback
history, stale/conflicting submissions, database failures, no-op revision,
content tampering rejection, approval gating, historical approval preservation,
concurrent client decisions (one accepted write, one 409) and retrieval after a
controlled application lifespan restart. Upstream extraction/classification are
mocked through normal APIs in the real-MongoDB scenario; no fake extraction
records are inserted and no model accuracy/ASR claim is made.

Dependency check passed. One existing Starlette/httpx TestClient deprecation
warning remains; no dependency or lockfile changes were made for this feature.
Frontend verification is documented in its README. No existing application
server was stopped/restarted and no existing client records were modified.


## Exception-based update — 2026-10-21

The previous all-label-reviews gate was removed. Initial SRS generation now uses
saved model predictions with optional reviewed corrections. Client decisions still
require explicit consent: one confirmed bulk action replaces per-row acceptance,
while existing exceptions remain unresolved until explicitly changed. Approved
versions remain frozen and all client decisions reset on revision.

Verification: 336 backend tests passed, including real isolated MongoDB, concurrent
writes, bulk replay, preserved exceptions, approval blocking and restart retrieval.
Tests cover drafts without reviews, partial corrections, correction precedence,
no fabricated label-review IDs, legacy hash stability and atomic bulk failure.
No existing client project was edited, no model/provider calls were made, and no
dependency or lock changes were required.
