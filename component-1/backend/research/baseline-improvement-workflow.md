# Bounded baseline improvement and label review

The application baseline remains unchanged. Offline trials reuse the original
DCAI source labels; PURE is not used for training because its new labels have
not been human reviewed. No model predictions or assistant draft labels are
reference labels. No source label is automatically changed.

## Reproduction

From the backend worktree's `component-1/backend`, use the existing interpreter
directly. Outputs are local/ignored. Existing output directories are refused:

```sh
.venv/bin/python scripts/improve_baseline.py --output research/models/dcai-improvement-v2
.venv/bin/python -m pytest -q tests/test_pure_preparation.py tests/test_baseline_data.py tests/test_baseline_model.py tests/test_classifications.py
.venv/bin/python -m py_compile scripts/improve_baseline.py scripts/plot_baseline_improvement.py
```

For charts, from the main repository root, using the already prepared isolated
plotting environment (no backend dependency or lock changes):

```sh
MPLCONFIGDIR=/private/tmp/intellise-c1-matplotlib \
.worktrees/_local-reports/plotting-env/bin/python \
  .worktrees/component-1-backend/component-1/backend/scripts/plot_baseline_improvement.py \
  --run .worktrees/component-1-backend/component-1/backend/research/models/dcai-improvement-v2 \
  --baseline .worktrees/component-1-backend/component-1/backend/research/models/dcai-v1/lr-c10
```

Existing run: `research/models/dcai-improvement-v1/`. The script reuses existing
strict dataset validation, pipeline fitting, artifact persistence/loading,
freezing and evaluation. Training is offline; none occurs on API startup.
The original prepared dataset and baseline files are hash-checked after running.

`protocol.json` is saved before trials. It declares C/feature-cap combinations
`(3,20000), (30,20000), (100,20000), (10,50000), (30,50000)`, seed 42, original
training-only fitting and validation macro-F1 selection. The original C=10 model
participates through its saved validation score. Equal scores favor the original
model, then smaller feature cap and C. The six diagnostic examples are checked
only after selection; they neither train nor select the model.

Only the selected new model is frozen, reloaded and evaluated on the saved test
split. This test was already used to report the original model, so the comparison
is **supplementary reuse**, not a fresh independent test. The old test scores
are read from the original report. No candidate is selected using test scores.
Within-corpus normalized-text grouping is not project separation. A fresh
source-grouped annotated test set is still required for a stronger improvement
claim. Dependency versions, seed, dataset/split/model identities are saved by the
existing artifact pipeline. Per-trial elapsed times are recorded separately.

## Review outputs and next step

`review_batch.csv` contains up to 25 existing *training* examples about login,
passwords or authentication, followed by up to 25 new PURE examples sampled
across source documents. Source text/IDs remain unchanged; validation/test rows
are not offered as editable training annotations. This is a workload sample,
not an evaluation split. `reviewed_label`, reviewer and date start blank.

`review_batch_with_suggestions.csv` has model suggestions in a separate field.
`review_batch_assistant_draft.csv` was additionally prepared for this initial
run with assistant-proposed FR/NFR/REVIEW/EXCLUDE decisions and written reasons;
these are explicitly not human-reviewed. It is not created by the experiment
script, is not automatically imported and must not be treated as gold labels.

Review the source context and fill only genuinely reviewed FR/NFR labels plus
reviewer/date. Behaviour, permissions, authentication actions and prohibitions
are FR under the project's stated policy; a security keyword alone does not make
a requirement NFR. Quality/operational/technology constraints are NFR. Resolve
mixed, unclear and non-requirement cases with notes and adjudication rather than
forcing binary labels. Independent review is desirable; none is claimed here.

Any accepted correction must retain original label/source provenance and become
a new versioned corpus. Never edit the original DCAI files or move old held-out
rows into training. New PURE annotations need canonical related-document/project
grouping review, duplicate/conflict quarantine, and the existing `Example` and
`Provenance` schema validation before prepare/train/freeze/evaluate. All of this
must precede replacing the application's configured model.

## Audit evidence

In the original training split, the authentication keyword subset contains
24 FR and 146 NFR examples. The model fits all 170 source labels correctly in
training, yet predicts the user's login example as NFR. Source examples assign
FR to session-start authentication while assigning NFR to authentication before
access: an annotation-policy mismatch needing review. Those records are not
automatically declared erroneous under their original dataset taxonomies.

`audit.json` contains the actual local linear-model feature contributions:
positive terms favor NFR and negative terms favor FR. This explains learned
associations, not semantic reasoning. `report.json` contains selected-model
identity, measured metrics, reload check and diagnostic predictions. Charts show
validation comparison, supplementary test metrics, confusion matrix, original
authentication labels and contributions behind the login prediction.

## Measured initial run

Five new configurations were fitted on the original 1,540 training examples
and selected using the original 516 validation examples. C=30 / 20,000 features
won; C=100 / 20,000 and C=30 / 50,000 tied, so the smaller settings won under the
declared rule. The original model wins any equal-score tie with a new candidate.

| Measure | Original C=10 | Selected C=30 |
| --- | ---: | ---: |
| Validation macro-F1 | 89.25% | 90.46% |
| Reused test accuracy | 91.47% | 91.67% |
| Reused test macro-F1 | 90.41% | 90.67% |
| Reused test FR F1 | 87.21% | 87.61% |
| Reused test NFR F1 | 93.60% | 93.72% |

Selected test confusion matrix (actual rows FR/NFR, predicted columns FR/NFR):
`[[152,22],[21,321]]`. It made 43 errors versus the original 44, across 516
examples. FR precision/recall: 87.86% / 87.36%; NFR: 93.59% / 93.86%.
These are supplementary comparisons on the reused original source-label test,
not fresh independent evaluation or PURE results.

Selected artifact: `research/models/dcai-improvement-v1/lr-c30-features20000/`,
model version `bf7bfc1b9e31b505111439247d825e81c6effb19073188a553c94279a28e2658`.
Save/reload/hash/version/split checks passed. The original dataset and baseline
files remained unchanged (10 checked files). New-trial train/save durations were
24.53, 38.07, 41.14, 33.87 and 36.70 seconds respectively; these are not inference
timings or real-time performance promises.

Both models predict NFR for the login, transfer-with-notification and
administrator-deletion-permission diagnostic sentences, whose draft expected
label is FR under this project's behaviour-based policy. Both correctly predict
FR for balance viewing and NFR for the two performance/capacity examples. These
six examples are illustrative, not a generalization benchmark. **The reported
user-facing prediction failure is unresolved. The candidate was not activated.**

The next concrete dependency is human adjudication of the 50-row review batch
(25 original training label audits and 25 new PURE examples), followed by a
versioned annotation update and a properly grouped fresh evaluation set.

Verification: 49 affected automated tests passed in 9.55 seconds; one existing
Starlette/httpx TestClient deprecation warning. Both experiment/plotting scripts
compiled. Backend dependency consistency passed. No frontend, API implementation,
environment settings or dependency locks were changed. No live browser/MongoDB
check was performed for this offline research change. Nothing was staged,
committed or pushed.
