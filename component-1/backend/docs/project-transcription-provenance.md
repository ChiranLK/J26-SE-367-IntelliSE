# Reviewed audio project creation — frontend contract

`POST /api/v1/component-1/projects` adds one optional field:
**transcription_id**, a completed transcription's UUID. No additional frontend
model/original-transcript/hash fields are accepted. Existing name/description/
discussion limits and text-only requests remain unchanged.

```json
{
  "name": "Client portal",
  "description": "Reviewed stakeholder recording",
  "discussion_text": "Customers can book appointments. Only administrators can delete accounts.",
  "transcription_id": "668a97af-dda2-48ef-969a-1eb4d9a86076"
}
```

This is an illustrative payload; replace the UUID with an actual completed job.
The server parses/canonicalizes UUIDs and looks up that job in the configured
MongoDB database. It requires completed, usable speech (`asr_performed=true`,
`outcome=review_required`, nonblank original, valid duration/timing/segments and
model metadata). Silence/skipped/empty-speech results cannot back a project.
It never runs Whisper again or requires Whisper assets just to save this reference.

`discussion_text` is the user's reviewed copy. It can be edited freely and need
not equal, resemble or contain the original. It is preserved exactly, including
whitespace, CRLF and Unicode. Name trimming and description behavior remain as
before. Including the reference records a **user-reviewed** action; this API
does not independently verify who reviewed it, whether speech was transcribed
correctly, or whether the edit is supported by the audio.

## Successful response and stored fields

POST still returns **201** with the full project. `GET /projects/{project_id}`
returns the same project/provenance. For an audio-derived project the additional
read-only field is **transcription_provenance**:

| Field | Backend source / meaning |
| --- | --- |
| `schema_version` | `c1-transcription-provenance-v1` |
| `transcription_id` | Canonical stored job UUID |
| `provider` | whisper, the backend's transcription implementation |
| `model`, `language` | Copied from stored completed job, currently language en |
| `original_transcript` | Exact generated ASR original copied from storage |
| `original_transcript_hash` | Lowercase SHA-256 hex of original UTF-8 bytes |
| `reviewed_discussion_hash` | Lowercase SHA-256 hex of project's exact discussion_text UTF-8 bytes |
| `segments` | Copied original `{start, end, text}` segments, seconds |
| `audio_duration_seconds`, `processing_seconds` | Stored decoded duration and measured worker time |
| `transcription_created_at` | Job created_at, UTC |
| `transcription_completed_at` | Completed job updated_at, UTC |
| `review_recorded_at` | Server timestamp when recording the submitted review; equals project created_at |
| `review_status` | user_reviewed |

Reviewed text lives in the project's existing **discussion_text**, so it has one
authoritative stored value. Original text lives both in the unchanged source job
and the immutable project snapshot. Hashes use SHA-256 of `.encode("utf-8")`,
without trimming, whitespace/case normalization or Unicode normalization. They
provide reproducible byte-level traceability, not a digital signature or proof
of semantic correctness. Timestamps have MongoDB millisecond precision.

Project status stays **draft**. This action does not make requirements or FR/NFR
predictions client-approved. Source-job reviewed_text stays null and its
review_status stays needs_review: reviews belong to individual projects, allowing
the same completed job to back different reviewed copies without mutating it.

For text-only requests, omit transcription_id or set it to null. Neither the
reference nor a null provenance field is stored/returned for legacy/text-only
records; their existing JSON shape remains unchanged. Listing summaries remain
unchanged and exclude discussion **and provenance at the database query**. Detail
retrieval never re-transcribes or needs the Whisper model to load.

## Errors and atomicity

| Status | Condition |
| --- | --- |
| 422 | Malformed UUID, invalid existing project fields or unknown client metadata/provenance fields |
| 404 | Referenced job does not exist in this database |
| 409 | Job queued, processing or failed; or a completed result is missing/malformed/unusable, including skipped silence or no intelligible speech |
| 503 | MongoDB/reference lookup/index/insert unavailable; existing sanitized persistence error contract |

Examples of actionable details: `Referenced transcription not found. No project
was saved.` and `Referenced transcription must be completed before saving a
reviewed discussion. No project was saved.` Invalid stored result errors contain
no full transcript, provider body or database details. Reference validation
finishes before any project index/insert. There is **no text-only fallback** on
failure, and no automatic retry. An ambiguous database write may still persist
despite a 503, as with existing project creation; check project listing/retrieval
before manually resubmitting.

A single majority-acknowledged project insert stores discussion and its complete
provenance together. Completed jobs have no application update/delete endpoint;
creation reads them without modifying them. No cross-collection transaction is
needed under that immutable-source contract, including standalone MongoDB.
There is **no transcription deletion/retention API or automatic job purge**.
Introducing deletion later must restrict deletion of referenced jobs or preserve
their source through an explicitly designed atomic retention policy. Raw operator
database deletions are outside this application contract; MongoDB does not enforce
foreign keys. The project snapshot retains original text/metadata independently,
but an operator must retain linked source jobs to keep source lookup available.

## Frontend integration

1. Upload audio and poll the existing transcription endpoint to completed speech.
2. Keep original text available and let the user edit a separate review draft.
3. On explicit Use, confirm replacement if discussion already contains text;
   retain the selected job ID alongside that discussion, name and description.
4. On explicit Save, send only the normal project fields plus transcription_id.
   Do not send the original, model, hashes, review flags or timestamps.
5. Handle 404/409 by retaining the draft/reference and explaining the failure.
   Do not drop the ID and retry as text-only.
6. Display returned transcription_provenance with project detail. The returned
   discussion is the reviewed copy; provenance.original_transcript is ASR output.
7. Keep extraction/classification as separate explicit actions. Their existing
   source text/hash is the reviewed project discussion.

The frontend's existing provenance save guard can be removed once it sends this
contract and handles these errors. Frontend files were deliberately unchanged in
this task; the current UI guard therefore remains until that follow-up.

## Normal backend startup

Use the component-1-backend checkout, installed in its own environment:

```sh
cd component-1/backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e '.[dev]'
.venv/bin/python -c 'import intelise_c1; print(intelise_c1.__file__)'
.venv/bin/python -m intelise_c1
```

Set MongoDB and optional ASR/classifier configuration using the existing ignored
`.env` and `.env.example`. The normal entry point includes transcription routes
even with no Whisper configured; health stays available. This session's durable
worktree is `.worktrees/component-1-backend` inside the outer repository, on the
expected backend branch. Its source and dedicated .venv are no longer under
/private/tmp. Reinstall editable after moving worktrees to avoid importing an
older checkout. No PYTHONPATH override or temporary application snapshot is needed.
Existing separately running servers need an explicit restart from this checkout
before they serve the new contract.

Actual generated schema: [project provenance OpenAPI fragment](project-provenance-openapi.json).
Verification: [results and exact commands](project-provenance-verification.md).
