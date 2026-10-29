# Experimental classifier: completed test workflow

The terminal testing workflow is ready. Run `./test-classifier` from this backend
directory, or invoke that file by its full path from any directory. It loads the
explicit local `research/models/dcai-behaviour-ai-v2/lr-c30` artifact, prints its
identity and AI annotation status, and accepts one requirement at a time. Type
`quit` to stop. There are no downloads, fallback models, background servers or
application configuration changes. MongoDB, Ollama and Whisper are not required
for this terminal model test.

```sh
./test-classifier
# Or a single request:
./test-classifier --text 'Users must be able to log in using a username and password.'
```

The normal browser still uses the original application model. This experiment
does not justify an automatic replacement: its labels are AI-assisted, some
diagnostic cases still fail, and scores against original test labels fell.

## Data and annotation

Original DCAI files and all earlier model versions are preserved. The new revision
contains explicit AI-assisted decisions on 382 original NFR training records:
229 behaviour/permission examples changed to FR, 45 constraints retained NFR,
108 ambiguous, mixed, incomplete or contextual statements quarantined. No
correction is claimed to be independently human-verified. The initial 146
authentication reviews are retained verbatim; 236 additional permission,
notification and transaction-related examples were reviewed. This is a selected
training-source audit, not a claim to have adjudicated every dataset row.

Every review retains original ID, source reference, unchanged text, original
label, proposed decision, rationale, text hash, reviewer identity, date, policy
version and `human_verified: false`. No classifier prediction supplied these
labels. This is an explicitly experimental exception to the ordinary human/
verified-source annotation workflow, authorized by the user's instruction to
perform the corrections; it does not turn AI annotations into ground truth.

Data paths (local and ignored):

- `research/raw/dcai-behaviour-ai-v2/reviews.json`: immutable decision ledger.
- `research/prepared/dcai-behaviour-ai-v2/`: revised examples, copied ledger,
  provenance, inherited-split manifest, quarantine and reports.
- `research/models/dcai-behaviour-ai-v2/lr-c30/`: frozen, reload-checked pipeline.

Training uses 1,432 examples: 747 FR, 685 NFR. Validation/test each retain exactly
516 original examples, with 174 FR and 342 NFR each. Their IDs/text/labels remain
unchanged; no old held-out row moves into training. Original source wording is
not rewritten. No PURE or synthetic examples are added. Existing schema,
duplicate/conflict, split-separation and class-coverage checks are reused.
The inherited assignment is clearly recorded in `revision_manifest.json`, not
passed off as a new stratified preparation. No project IDs were fabricated.

## Actual results and limitations

One fixed model used word TF-IDF unigrams/bigrams (20,000 features) plus logistic
regression C=30, balanced weights, seed 42. Vocabulary/IDF/coefficients fit only
training examples. Settings were retained from earlier validation selection;
no further parameter or annotation changes followed the final diagnostics.
Train/save/freeze/reload/evaluate/diagnostic processing took **33.39 seconds**.

Model version:
`21be863112146515a369e33543adab8f8ed30d36d6d4eb87dd927afaede6ee5c`.

| Measure | Experimental result |
| --- | ---: |
| Validation accuracy | 73.06% |
| Validation macro-F1 | 72.68% |
| Reused original test accuracy | 75.19% |
| Reused original test macro-F1 | 74.52% |

Test confusion matrix (rows original FR/NFR, columns predictions FR/NFR):
`[[152,22],[106,236]]`. Complete precision/recall/per-class F1 are saved in
`report.json` and the artifact's `test_metrics.json`. The original model had
91.47% accuracy and 90.41% macro-F1 against those original labels. The revised
training policy differs from those unchanged source labels; this disagreement
has not been independently adjudicated. Do not describe this candidate as an
overall improvement, or explain every disagreement away as a test-label error.
This is supplementary reuse of an already exposed within-corpus test set, not
fresh independent or unseen-project evaluation, and not PURE evaluation.

All seven saved development probes now match their expected labels, including
login, transfers, administrator-only deletion, performance and encryption.
Those probes were known during development and motivated the source review;
they are not independent validation. Their exact sentences were not injected
into training and there are no keyword rules or sentence-specific overrides in
prediction code.

The separate check of the user's twelve original banking/food-delivery examples
matched 9/12. Three remaining failures:

| Example | Expected | Actual |
| --- | --- | --- |
| Track the real-time location of a delivery driver | FR | NFR |
| Restaurant menus load in under one second | NFR | FR |
| Intuitive design allowing a first-time order without a tutorial | NFR | FR |

The exact source sentences, results and timing are in `scenario_checks.json`.
The twelve-example agreement is a diagnostic count, **not measured general
classification accuracy**. Model load in that run took 10.18 seconds; subsequent
per-prediction timings excluding loading are retained separately. No real-time
performance promise is made. The terminal loads only once per session.

## Checks and artifacts

61 automated tests passed in 6.09 seconds, with one existing Starlette/httpx
deprecation warning. Checks cover inherited holdout preservation, source hash/
label validation, duplicate reviews, class coverage, truthful AI review status,
baseline artifacts and classification API regressions. Backend dependency check
passes. The saved artifact was hash/type/version checked and reloaded; predictions
matched. Actual interactive launcher checks returned FR for login, transfer and
administrator deletion, NFR for two-second search, then exited cleanly. Launcher
also worked from outside the backend directory. These are actual local model
checks, not mocks. API regression tests are automated checks; no live MongoDB or
browser verification is claimed for this offline-only change.

Final charts: `research/prepared/dcai-behaviour-ai-v2/charts-final/` contains three
PNG/SVG pairs, HTML gallery and `experimental-label-revision.pdf`. They show
unchanged-test-label comparison, confusion matrix and reviewed training counts.
Use `charts-final`; the earlier generated `charts` copy has a stale audit-count
title and is superseded. Both are retained locally rather than deleting files.

## Reproduce

From the backend worktree's `component-1/backend`; use fresh output names:

```sh
.venv/bin/python scripts/train_reviewed_baseline.py \
  --reviews-path research/raw/dcai-behaviour-ai-v2/reviews.json \
  --output research/prepared/dcai-behaviour-ai-v3 \
  --model-output research/models/dcai-behaviour-ai-v3/lr-c30 \
  --revision-name dcai-behaviour-ai-v3 \
  --review-scope 'authentication, permissions and transaction behaviour'
.venv/bin/python -m pytest -q tests/test_baseline_revision.py tests/test_pure_preparation.py tests/test_baseline_data.py tests/test_baseline_model.py tests/test_classifications.py
.venv/bin/python -m pip check
```

From the main repository root, using the existing isolated plotting environment:

```sh
MPLCONFIGDIR=/private/tmp/intellise-c1-matplotlib \
.worktrees/_local-reports/plotting-env/bin/python \
  .worktrees/component-1-backend/component-1/backend/scripts/plot_label_revision.py \
  --revision .worktrees/component-1-backend/component-1/backend/research/prepared/dcai-behaviour-ai-v3 \
  --original-model .worktrees/component-1-backend/component-1/backend/research/models/dcai-v1/lr-c10
```

Technical testing can proceed now. The research/deployment prerequisite remains
human adjudication and a policy-consistent independently reviewed, grouped
evaluation set. No frontend/API/environment/lock files changed; nothing was
staged, committed or pushed. The existing application model remains configured.
