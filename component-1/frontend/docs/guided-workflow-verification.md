# Three-stage project UI — verification

## What changed

The project workspace uses a three-stage progress tracker inspired by the supplied
order-tracking example, with a green palette and compact requirement cards:
Create & review source → Classify & review labels → Export results.
The original text/audio input, explicit transcript application/replacement,
provenance checks, persistence, model predictions and saved human reviews remain.
Long identifiers, evidence and model metadata are expandable. The sentence/CSV
model tester is now isolated at `/#model-test`, and is absent from project pages.
Future capabilities remain collapsed below the workflow.
No backend files, dependencies, model artifacts or saved client records were
modified for this interface change. Existing staged and unrelated work was retained.

A new frontend acknowledgement requires reviewing discussion text before saving;
editing/replacing that text clears the acknowledgement. This does not create a
backend verified status. Source audio and original ASR output remain separate
from the user's reviewed discussion. Saved source records remain unchanged.

The combined button calls the existing extraction API, then classification for
that validated saved extraction. A classifier error preserves the saved extraction
and supports explicit classification-only retry. No generation/model fallback,
automatic retry or automatic project saving was added.

JSON/text export is generated locally on an explicit download action. It includes
project/source information, original transcription provenance if present, source
evidence and offsets, original requirement IDs, classification/model identity,
model predictions and saved label-review records. `label` uses a saved reviewed
label when available; otherwise it uses the model prediction and is explicitly
marked `model_prediction`. Exports represent the displayed run, not a claim that
no newer run exists on another client. Unsaved review edits and unavailable/loading
review retrieval block export. Review history stays in the backend; exports include
the latest retrieved review per requirement for the displayed classification.

## Actual verification

- `npm test`: **93 passed**, including five export tests. Covered preserved
  predictions/evidence/IDs, stale/mismatched reviews, explicit unreviewed labels,
  separate original audio provenance, and a valid empty export.
- `npm run lint`: passed with zero warnings.
- `npm run build`: passed.
- `C1_LIVE_MODEL_TEST=1 npm run test:browser`: **2 passed, 1 skipped**.
  Chrome with a test-only HTTP API verified source-review confirmation, the
  three-stage navigation, duplicate-submit guards, saved label editing/retrieval,
  blocked export for unsaved edits, real JSON/text file downloads and file contents,
  plain-text rendering, old-run separation, audio provenance/UI recovery, and
  combined extraction/classification success and failure. Classification-only
  retry did not create another extraction. The mobile view fit its viewport.
- The separate browser test used the existing actual local TF-IDF/logistic
  regression artifact (version
  `b48d2a3a87e3669957a1c5374c8879cd84fc1fe232e002a1c50c9821cb693823`).
  Booking example: FR, 7.931 seconds browser elapsed; two-second search example:
  NFR, 0.015 seconds. Its illustrative CSV still showed mismatches; these are
  checks of the unchanged model, not new accuracy measurements.
- The live Azure audio browser test was skipped. Mocked audio UI checks are not
  evidence of ASR performance. No paid Azure calls were made for this change.
- Read-only inspection of running `http://127.0.0.1:8001/openapi.json` confirmed
  project GET/POST, transcription POST/GET, label-review GET/POST and the optional
  `transcription_id` field in project creation. No production project was created
  or changed. Real MongoDB was not retested for this frontend-only change; prior
  review persistence checks are described in `label-review-verification.md`.

Browser fixture waits were updated for asynchronous save/navigation and the new
source-view step. Earlier attempts failed at those outdated test assumptions;
the final complete browser run passed.

## Reproduce

From `component-1/frontend`:

```sh
npm test
npm run lint
npm run build
C1_LIVE_MODEL_TEST=1 npm run test:browser
```

The browser suite requires Chrome and local socket permissions; the opt-in local
model check requires the existing configured artifact. Its workflow API is mocked,
so it needs no Azure/Ollama requests and writes no client records.

Browser fixture screenshots from the final check (temporary local files):

- `<system-temp>/intellise-c1-workspace-desktop.png`
- `<system-temp>/intellise-c1-workspace-guided-review.png`
- `<system-temp>/intellise-c1-workspace-export.png`

To try the UI, refresh the existing frontend. If services are stopped, run
`./start-component-1` from the main repository root. Stop an old launcher from its
terminal first if its ports are occupied. Backend API contracts are unchanged.

Human-reviewed labels are self-reported and do not imply client approval, independent
verification or retraining. The existing within-corpus evaluation limitations remain;
performance on unseen projects and extraction completeness/relevance need evaluation.


## October 19 layout cleanup

Step 2 now presents extraction and saved label reviews inside one continuous white
panel. The standalone “Functional or non-functional?” tester no longer appears on
the project page; optional diagnostics remain at `/#model-test`. The duplicate
“no saved extraction” panel is suppressed, and the single empty-state message
points to the visible Run extraction & classification action. Headers, inner
padding and desktop/mobile controls align within the shared panel.

Verification rerun: 93 unit tests passed; ESLint and production build passed.
Chrome: two tests passed, one live audio scenario skipped. Workflow checks use a
mock HTTP API, including assertions that no standalone tester renders on the
project page and only one empty extraction message appears. Review persistence
retrieval, exports, combined generation recovery and responsive layout checks
remain covered. The separate diagnostic route was tested using the actual saved
local classifier. No paid Azure request or live-client record mutation occurred.
The same reproduction commands above apply.

## Export filenames use project titles

Downloads now use the saved project title: `Demo Calculator.json` or
`Demo Calculator.txt`. Reserved filename characters/control characters are
replaced, reserved device names receive a prefix, and filenames are bounded in
UTF-8 bytes while retaining ordinary spaces and Unicode titles. Empty/unusable
titles fall back to `Project`. Project/run identifiers remain in the file contents.
The browser may add a numeric suffix for an existing download with the same name.

Verification: focused export tests and direct filename checks passed (normal
project title, both extensions, invalid/control characters, fallback, reserved
names, Sinhala and long emoji titles). Lint and production build passed. The
Chrome workflow downloaded JSON and text using the actual project-title filenames
and verified their contents through the mocked workflow API. No backend or model
changes were needed.
