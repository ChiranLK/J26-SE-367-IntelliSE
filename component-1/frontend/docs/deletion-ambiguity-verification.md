# Dashboard deletion and unclear wording review — October 19, 2026

## Dashboard deletion

Delete is a separate button beside each project; selecting it opens a confirmation
naming the project. Cancel is initially focused. Cancel/Escape do not send DELETE.
The confirmation explicitly states that database records are retained for recovery,
not permanently erased. A confirmed DELETE removes only that project from normal
listing/retrieval. Original discussions, completed transcription jobs and run/review
history remain stored. Deleting the current project opens the new-project form.

`DELETE /api/v1/component-1/projects/{id}` returns 204 with no body. The frontend
validates this response. 404/405 from an old or mismatched backend is an error,
not a successful deletion. Database/network failures remain visible. Requests
are not automatically retried; repeated explicit deletion of the same retained
project is idempotent. The pending-request guard prevents duplicate clicks.

Restart the backend using its normal launcher after updating source; do not stop
an unrelated process or delete client data to test this feature. Verification below
uses generated test databases and a fixture dashboard only.

## Where ambiguity review fits

The current three-step flow remains:

1. Capture and review text/audio source.
2. Extract/classify saved requirements, inspect **Unclear points**, discuss the
   questions with the client, and save human FR/NFR label reviews separately.
3. Export source evidence, predictions, saved labels and wording hints as JSON/text.

Example input: “The calculator should respond quickly and be user-friendly.”
The v1 rules identify tentative obligation (“should”), vague timing (“quickly”)
and subjective usability (“user-friendly”), and suggest questions about mandatory
scope, maximum response time/workload and a measurable user task. These are not
answers or rewritten requirements. Numeric limits must come from the client.

Rule version: `c1-ambiguity-rules-v1`; method: rules; language: English. Exact
matched phrases retain case and have end-exclusive Unicode character offsets
within candidate `requirement_text`, not the original discussion. Each offset
resolves to its matched phrase. Results are computed from the saved candidates
in the browser on each view/export; there is no new MongoDB ambiguity-analysis
record or ambiguity-resolution API. Saved classification label-review status does
not mean an unclear point has been resolved.

Limitations: English phrase rules have false positives and false negatives,
miss context/coreference/domain-specific ambiguity, and do not check requirements
that extraction omitted. A match may already be clarified elsewhere; no match
is not proof of clarity. This is not a trained ambiguity model or a new accuracy
result. The FR/NFR artifact, source/evidence validation and within-corpus research
evaluation limitations remain unchanged.

## Reproduce checks

From `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
C1_LIVE_MODEL_TEST=1 npm run test:browser
```

From the backend worktree's `component-1/backend`:

```sh
.venv/bin/python -m pytest -q
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 .venv/bin/python -m pytest -q -m integration
```

Measured checks: 102 frontend tests passed, lint/build passed. Full backend suite:
309 passed and 13 integration tests skipped without TEST_MONGODB_URI. Separately,
all 13 integration tests passed against actual local MongoDB in generated isolated
databases. The new deletion test created an audio-derived project, valid extraction,
classification and label review through normal APIs with mocked ASR/extractor/
classifier outputs; DELETE returned 204, project/run/review retrieval returned 404,
the completed transcription remained retrievable, another project stayed intact,
and retained raw collection counts were checked. A fresh application lifespan
preserved deletion and repeated DELETE returned 204 without changing the first
`deleted_at` timestamp. No existing client record was used.

Browser verification includes cancellation, duplicate-submit guard, database-error
feedback, safe manual retry, dashboard removal and reload; ambiguity UI, unchanged
candidate text, exact flags/questions and exported versioned hints are also checked.
The workflow browser API is mocked; the separate model tester uses the existing
actual local classifier. Live Azure audio is skipped; no paid request was made.
