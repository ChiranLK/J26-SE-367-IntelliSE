# Reviewed audio project provenance — verification

Verified October 15, 2026 on **component-1-backend**. Repository instructions,
project/transcription schemas, repositories, database lifespan, normal startup,
locks, existing tests and the frontend's documented blocker were inspected.
No applicable AGENTS.md was found. Existing audio implementation and unrelated
work were reused/preserved. No frontend changes, commits, pushes or stash operations.

## Durable backend source and startup

Moved the existing backend branch worktree, including its uncommitted audio
implementation, from /private/tmp into the persistent workspace:

```text
<repository-root>/.worktrees/component-1-backend
```

The outer checkout remains on component-1-frontend with its existing changes
untouched. Added only a local `.git/info/exclude` entry for `/.worktrees/` so the
outer checkout does not treat the nested worktree as project content. No branch
switch/reset occurred. The backend worktree remains on component-1-backend.

A dedicated ignored backend `.venv` was copied from the previously verified API
environment, then this durable backend package was installed editable offline:

```sh
.venv/bin/python -m pip install --no-index --no-deps --no-build-isolation -e .
.venv/bin/python -c 'import intelise_c1; print(intelise_c1.__file__)'
```

The import resolved into this worktree's `component-1/backend/src/intelise_c1`,
without a PYTHONPATH override. Original classifier/ASR environments were unchanged.
No dependency pins changed for provenance. The existing audio dependency changes
from the previous task remain in the worktree.

Normal **`.venv/bin/python -m intelise_c1`** was used for both server starts in the
live check. OpenAPI exposed audio routes and ProjectCreate.transcription_id.
Startup therefore uses the durable backend source, not the old temporary source
snapshot. The previously running server on 8001 was not restarted/reconfigured;
it must be explicitly restarted from this checkout to serve this contract.

## Changes

- `api/project_schemas.py`: optional UUID transcription_id; server-owned
  TranscriptionProvenance; optional detail response snapshot. No new fields in
  list summaries, and text-only response fields remain exactly as before.
- `services/transcription_provenance.py`: require stored completed usable speech;
  snapshot trusted original/model metadata; compute exact UTF-8 SHA-256 hashes;
  sanitized 404/409 reference errors. User-reviewed is not independently verified.
- `repositories/projects.py`: lookup/validate before project writes; one atomic
  project insert contains discussion plus snapshot; exclude original/provenance
  from summary queries. No writes to transcription jobs.
- `core/database.py`: share the real transcription repository with project
  creation and the existing worker.
- `api/projects.py`: document/reference errors, expose detail provenance, omit
  unset provenance on text-only/legacy records.
- `tests/test_project_provenance.py`, `test_project_provenance_integration.py`:
  API/schema/storage/source validation, real-MongoDB save/restart/downstream checks.
- `scripts/smoke_transcription.py`: reuse the existing live smoke flow, now use
  normal module startup; optional --verify-project-provenance explicitly creates
  one edited-review test project and checks it after restart.
- README/audio guide, historical audio-report notice,
  `docs/project-transcription-provenance.md`, `docs/project-provenance-openapi.json`
  and this report: exact frontend contract, durable startup and verification.

The source job is immutable under the application API. No transcription deletion,
TTL index or automatic job purge exists, so application writes cannot introduce
a dangling reference by deleting a completed job. Future deletion needs a linked-job
retention/restriction policy. Raw operator MongoDB deletion is outside this contract.
The project keeps a full original/metadata snapshot independently of source lookup.

## Automated results

From the durable worktree's `component-1/backend` directory:

```sh
# Focused initial run, using the existing verification interpreter:
PYTHONPATH=src /private/tmp/intellise-c1-audio-api-env/bin/python \
  -m pytest tests/test_project_provenance.py -q --tb=short

# Complete final suite through the installed durable environment:
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 \
  .venv/bin/python -m pytest -q --tb=short
.venv/bin/python -m pip check
git diff --check
```

Results: **29 focused tests passed** (2.26 seconds); **258 full-suite tests passed**
(63.14 seconds), including 11 real-MongoDB integration cases, no skips.
`pip check` and `git diff --check` pass. One existing Starlette TestClient/httpx
deprecation warning remains; no configured backend lint tool exists.

New coverage includes text-only omitted/null reference with unchanged response
and storage shape; completed job with edited Unicode/CRLF reviewed text; original
and independent hashes; trusted metadata; malformed/missing/noncompleted/failed/
silent/empty/malformed completed sources; forbidden client provenance fields;
sanitized read/write failures; no project insert on validation failure; detail
retrieval; unchanged source jobs; multiple reviewed projects from one source;
real-MongoDB persistence across fresh application lifespans; summary exclusion;
extraction using reviewed discussion/hash; candidate unreviewed status; classification
IDs mapping to the saved requirements and retrieval across restart.

Automated ASR, extraction and classifier outputs are mocked and labelled as such.
Real MongoDB integration tests reuse the documented UUID database fixture and drop
only their generated databases. These tests establish application behavior, not
speech recognition, extraction or classifier accuracy.

## Actual real-ASR / HTTP / MongoDB / restart check

Reused the existing public Whisper JFK recording (11-second WAV), explicitly
prepared tiny.en checkpoint and separate ASR interpreter. No model download or
training occurred. The smoke test created its own server/port, dedicated upload
root and UUID-named disposable MongoDB database. The existing server/client data
were not changed. Exact command:

```sh
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 \
  .venv/bin/python scripts/smoke_transcription.py \
  --sample /private/tmp/intellise-c1-jfk.wav \
  --whisper-python /private/tmp/intellise-c1-whisper-env/bin/python \
  --model-dir /private/tmp/intellise-c1-whisper-models --model tiny.en \
  --verify-project-provenance
```

Measured output and checks:

| Check | Actual result |
| --- | --- |
| Startup, initial and restarted | python -m intelise_c1, installed durable package |
| Source transcription ID | d501e5d7-2bf7-4d0a-abfd-59755855972e; disposable record, now removed |
| Model/language/device | tiny.en / en / CPU fp16=False |
| Duration | 11.0 seconds |
| Backend processing time | **17.992379813 seconds** |
| Upload-to-completion | 18.858173101 seconds |
| Original result | 105 characters, 2 segments; no full transcript logged |
| Original SHA-256 | d9447b7d0f9a53f85ec4e2f98d6a918a79da391e3462b546b7f1912622ca2e70 |
| Health during processing | 251 HTTP 200 requests; maximum 0.052220752 seconds |
| Explicit review project POST | HTTP 201, edited discussion plus transcription ID; server snapshot/hashes matched |
| Real MongoDB project record | Reviewed discussion found by provenance.transcription_id |
| Source immutability | Entire original MongoDB job document unchanged after project creation and restart |
| Project retrieval after process restart | Full response exactly matched pre-restart response, with Whisper disabled |
| Summary retrieval | One explicitly created project, no discussion/provenance payload |
| Existing audio checks | Silence review outcome, corrupt/overlong failures, oversized 413, saturation 429 all passed |
| Cleanup | Temporary upload files removed; only generated database dropped |

The edited review added a test annotation to the actual generated text solely to
verify independent preservation/hashing. This is not evidence that a human
validated the recording or that an arbitrary edit is semantically supported.
No project/extraction/classification was generated automatically: the one project
POST was explicitly requested by the verification flag. No live LLM extraction or
real classifier accuracy was evaluated in this check.

## Frontend next action and limits

The exact contract is in [project-transcription-provenance.md](project-transcription-provenance.md)
and the generated [OpenAPI fragment](project-provenance-openapi.json). Frontend
follow-up: retain the selected completed job ID and submit it as transcription_id
with the reviewed discussion; handle reference errors without dropping the ID;
show returned transcription_provenance in project detail. The frontend's current
save guard remains because frontend changes were excluded from this task.

Prepared ASR assets in the command above are temporary verification assets. Follow
the existing audio setup guide to install a durable .venv-whisper/model directory
and configure it locally. Source startup no longer depends on a temporary path.
Hash equality establishes byte-level traceability, not independent review,
transcript accuracy, requirement relevance/completeness or semantic correctness.
Baseline evaluation remains within-corpus; no new metrics or confidence claims.
