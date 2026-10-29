# Experimental authentication label revision

The user's login example now predicts **FR** with a separately saved candidate.
This does not establish an overall improvement. The application model remains
unchanged because the candidate scores lower against the original test labels
and other diagnostic failures remain.

## Annotation and data

At the user's request, Codex reviewed the 146 original NFR-labelled training
examples containing authentication/login/password keywords. These are explicit
AI-assisted policy annotations, **not independently human-reviewed ground truth**.
This is a separate experimental revision; it does not change the normal corpus
policy requiring human or verified-source labels. Do not use the revision as a
gold evaluation dataset. No labels came from classifier predictions. No PURE or
synthetic examples were added. The reported login sentence was not added to
training, and there is no special-case prediction override.

Under the project's behaviour-versus-quality policy:

- 98 explicit actions, permissions, credential-management and authentication
  protocol behaviours changed from NFR to FR.
- 21 quality/design constraints remained NFR, including encryption, authentication
  strength, interoperability and specified cryptographic mechanisms.
- 27 mixed, contextual, incomplete or unclear examples were quarantined rather
  than forced into a binary class.

Every decision retains original ID, original text/label, source reference,
SHA-256 of original text, rationale, AI reviewer identity, timestamp, policy
version and `human_verified: false`. These are local ignored research files.
Original DCAI raw/prepared data, previous models and user staging remain intact.

New preparation directory: `research/prepared/dcai-auth-ai-v1/`.
Original decisions: `research/raw/dcai-auth-ai-v1/reviews.json`.
Training: 1,513 examples (616 FR, 897 NFR); validation and test: 516 each,
unchanged (174 FR, 342 NFR each). No examples move between splits. Every old
validation/test ID, text and label is preserved exactly. Existing schema,
duplicate/conflict and class-coverage checks are reused.

The new `revision_manifest.json` explicitly identifies inherited parent holdouts,
parent dataset/split hashes, new dataset/split hashes and AI annotation status.
It is deliberately not a standard freshly stratified `manifest.json`: rerunning
stratification after label changes could move old test examples into training.
The revision trainer validates its parent and all explicit amendments, preserves
the holdouts, and reuses existing fitting, metric and restricted artifact tools.

## Training and measured results

One fixed TF-IDF + logistic regression candidate used C=30, 20,000 features,
seed 42, word unigrams/bigrams, balanced class weights and training-only fitting.
Settings came from the earlier validation-only selection; there was no further
search or relabelling after checking the diagnostic predictions. Train, save,
freeze, reload, evaluation and diagnostics took **33.41 seconds** in this run.
This is not an inference timing or real-time performance claim.

| Measure | Original model | Experimental label revision |
| --- | ---: | ---: |
| Validation macro-F1 | 89.25% | 85.16% |
| Reused test accuracy | 91.47% | 84.69% |
| Reused test macro-F1 | 90.41% | 83.56% |
| Reused test FR precision | 88.24% | 72.95% |
| Reused test FR recall | 86.21% | 86.78% |
| Reused test FR F1 | 87.21% | 79.27% |
| Reused test NFR precision | 93.06% | 92.56% |
| Reused test NFR recall | 94.15% | 83.63% |
| Reused test NFR F1 | 93.60% | 87.86% |

Test confusion matrix (rows original FR/NFR; columns predicted FR/NFR):
`[[151,23],[56,286]]` (79 disagreements/errors against unchanged source labels).
Scores are supplemental reuse of the old test, **not a fresh evaluation**. The
revised training policy differs from that test's original source-label policy;
the result cannot distinguish all policy disagreements from prediction errors.
No corrected test labels were invented to raise scores. No unseen-project or
PURE evaluation claim is made; canonical project IDs remain unavailable.

Actual diagnostic predictions (illustrative, not an independent benchmark):

| Requirement | Expected | Actual |
| --- | --- | --- |
| Users must be able to log in using a username and password. | FR | FR |
| Users must be able to view their current account balance. | FR | FR |
| Users must be able to transfer funds between accounts and receive a confirmation notification. | FR | NFR |
| Only administrators can delete accounts. | FR | NFR |
| Search results must appear within two seconds. | NFR | NFR |
| The system must support 5,000 concurrent users. | NFR | NFR |
| All financial data and transactions must be encrypted using industry-standard protocols. | NFR | NFR |

## Test the saved candidate

From the backend worktree's `component-1/backend`:

```sh
.venv/bin/python scripts/check_requirement.py \
  --model-dir research/models/dcai-auth-ai-v1/lr-c30
```

Enter one requirement at a time. Type `quit` to exit. The file-based terminal
tester keeps stdin available, loads once and displays the actual model identity
and experimental annotation status. It was tested through a real terminal with
the login example (FR), two-second search (NFR), and clean exit. To test once:

```sh
.venv/bin/python scripts/check_requirement.py \
  --model-dir research/models/dcai-auth-ai-v1/lr-c30 \
  --text 'Users must be able to log in using a username and password.'
```

Model directory: `research/models/dcai-auth-ai-v1/lr-c30/`.
Model version: `2ec1251e8d4fda2a360a54fcdc5b2aa79205ba8d4c0e18544e937163a5ea6ff1`.
Its metadata, split manifest, freeze marker and measured metrics are retained.
The normal browser/application still uses its original configured model.

## Reproduce and verify

Outputs never overwrite existing paths. Keep the initial reviews file and use
fresh output names for a reproduction (same annotations, no automatic labelling):

```sh
.venv/bin/python scripts/train_reviewed_baseline.py \
  --reviews-path research/raw/dcai-auth-ai-v1/reviews.json \
  --output research/prepared/dcai-auth-ai-v2 \
  --model-output research/models/dcai-auth-ai-v2/lr-c30
.venv/bin/python -m pytest -q tests/test_baseline_revision.py tests/test_pure_preparation.py tests/test_baseline_data.py tests/test_baseline_model.py tests/test_classifications.py
.venv/bin/python -m pip check
```

Measured checks: **61 tests passed**, including rejection of holdout edits,
tampered source hashes/labels, duplicate reviews, unsupported decisions, fake
human verification, missing rationale/date and loss of class coverage. One
existing Starlette/httpx deprecation warning. Scripts compile; dependency check
passes; restricted model reload and prediction equality pass. No live browser
or database test is claimed for this offline research change.

Charts (PNG/SVG, HTML gallery and PDF) are saved under
`research/prepared/dcai-auth-ai-v1/charts/`. To reproduce from the main repo root:

```sh
MPLCONFIGDIR=/private/tmp/intellise-c1-matplotlib \
.worktrees/_local-reports/plotting-env/bin/python \
  .worktrees/component-1-backend/component-1/backend/scripts/plot_label_revision.py \
  --revision .worktrees/component-1-backend/component-1/backend/research/prepared/dcai-auth-ai-v2 \
  --original-model .worktrees/component-1-backend/component-1/backend/research/models/dcai-v1/lr-c10
```

Human adjudication of the saved review ledger and a policy-consistent, independently
reviewed, source-grouped evaluation set remain necessary before deployment or an
improved-model claim. The transfer and deletion-permission failures need separate
training-source review. Do not repeatedly tune against these diagnostics and call
them unseen evaluation. No frontend files, APIs, environment settings or locks
were modified; nothing was committed or pushed.
