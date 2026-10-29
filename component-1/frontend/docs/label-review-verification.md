# FR/NFR label review verification — October 18, 2026

A user can review a saved model prediction without replacing it. The model is
still TF-IDF plus logistic regression. No retraining, improved benchmark score,
authenticated review identity or client approval is claimed.

## Use

1. Stop the existing launcher in its terminal with Ctrl+C, so the backend reloads
   the new routes. From the main repository root, run `./start-component-1`.
   If port 8001 is occupied, stop its existing server from its terminal first.
2. Open the frontend URL printed by the launcher (normally http://127.0.0.1:5173).
3. Open a project with a saved extraction and classification. If none is saved,
   use the existing explicit Extract and Classify actions first.
4. Enter a reviewer name/ID, select a reviewed label, optionally add a reason,
   and click Save review. For example, password reset is a user-facing function,
   so review “Users shall be able to reset their passwords.” as FR if the baseline
   predicted NFR. The NFR model badge stays visible beside the reviewed FR value.
5. Refresh/reopen the project. Its latest saved reviews should reappear.

Reclassifying creates a new classification run and a separate set of reviews.
Earlier history remains stored; it is not automatically applied to the new run.
Reviews are append-only; the interface retrieves the latest per requirement in
that exact run. No reviewed-label feature exists for the unsaved sentence tester.

## Measured checks

- Frontend unit suite: 88 passed, including five review API tests for saved mapping,
  hashes, stale/wrong identities, invalid inputs, unavailable API and uncertain saves.
- ESLint: passed with zero warnings. Vite production build: passed.
- Chrome browser workflow with a mocked HTTP API: passed. Verified save, duplicate
  click guard, unchanged original badge, safely rendered note, retrieval after
  reload, and absence of reviews from an older extraction. These are UI checks,
  not real database or model accuracy evidence.
- Separate real local classifier browser check: passed (existing model version
  `b48d2a3a87e3669957a1c5374c8879cd84fc1fe232e002a1c50c9821cb693823`).
  Its sample CSV still had mismatches. Corrections do not improve model predictions.
- Live audio browser scenario was skipped; no Azure calls were made for this change.
- Actual MongoDB API persistence/restart checks passed in generated disposable
  databases. Extraction and classifier outputs in these database tests were mocked;
  reviews were written/read through the normal API, not inserted as fake source runs.

## Reproduce

From `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
C1_LIVE_MODEL_TEST=1 npm run test:browser
```

The browser suite needs Chrome, local socket permissions and the existing model
for its opt-in model check. Its API fixture checks do not need Azure or Ollama.
Backend commands and exact HTTP schema are documented in the backend worktree's
`component-1/backend/docs/label-reviews.md`.

Reviewer IDs are self-reported. Human-reviewed labels need a consistent annotation
policy before future training. Deduplicate and prevent held-out test leakage if
reviews are later exported for training. Existing within-corpus evaluation does
not establish performance on unseen projects or prove any individual prediction.
