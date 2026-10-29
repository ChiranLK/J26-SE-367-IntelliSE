# Supplied DCAI24 baseline — October 14, 2026

Live persistence follow-up: [running application verification](live-classification-verification.md)
found health/OpenAPI available, projects returning MongoDB 503, and six real-MongoDB
integration setup errors. Live classification/restart verification remains blocked.

Preparation, training, fixed held-out evaluation and local classification integration
are complete before the October 18 deadline. This is the initial **TF-IDF plus
logistic regression** baseline, not BERT. No frontend, Ollama configuration or other
component was changed. Nothing was committed or pushed.

## Source and preparation

Located the supplied file at:

`/Users/chiranserasinghe/Documents/AI-SDLC AGILE/Data Set/FR:NFR/dcai24_src_dataset.xlsx - Sheet1.csv`

Raw SHA-256:
`b39a229a62c3c28186d5deb945b175da41f3f4ac7dbfddb787e8fd3e4abea49b`

The original file is unchanged. A byte-identical copy is retained in ignored
`research/raw/dcai-v1/`. The five original columns are `Requirement`, `Type`,
`Specific_Type`, `Security_Category` and `Dataset_Name`. Only unchanged Requirement
text and Type labels enter training. Original rows/metadata remain traceable through
`source_metadata.jsonl`, `quarantine.jsonl`, logical CSV record references and
`row_assignments.json`. `exclusion_report.json` records all exclusions, duplicate
and conflict groups, input hash and final counts; `provenance.json` records what
is known and unknown about the supplied labels.

| Disposition | Rows |
| --- | ---: |
| Raw input | 3,482 |
| Raw FR | 1,117 |
| Raw NFR | 1,848 |
| Quarantined #N/A targets | 517 |
| Quarantined conflicting FR/NFR labels | 36 across 18 groups |
| Redundant same-label rows retained only as traceability metadata | 357 |
| Final unique usable requirements | **2,572** |
| Final FR | **866** |
| Final NFR | **1,706** |

Exclusions are mutually exclusive and sum to 910. Duplicate comparison uses NFKC
Unicode normalization, case folding and whitespace collapse. This is detection
only: original requirement wording, casing, whitespace and all source metadata
remain unchanged. Every row in each conflicting FR/NFR group is quarantined; no
majority label is chosen. Same-label duplicates retain the first eligible source
occurrence and references to every original occurrence. Invalid targets are never
relabeled using Specific_Type, Security_Category or a model.

Prepared dataset version:
`c96758ce53f4579de4214a3652720d8a0e9f55e8b09f449ea136bcd3ad806874`

Split ID:
`3e37a23a255cb1985f57ed3a7e389d2c2b6426e8e2b46fd9b6fa385de1fb2efd`

## Evaluation method and grouping limitation

The CSV and its adjacent source note provide no individual project IDs or project
mapping. **Zero genuine project IDs were recovered.** Dataset_Name identifies six
source collections; it is never assigned to source_project_id or presented as an
individual project ID. Missing IDs are explicitly null.

This initial evaluation uses the explicit `--grouping normalized_text` fallback:
seed **42**, stratified by FR/NFR, randomized over sorted SHA-256 normalized-text
groups, approximately 60/20/20 train/validation/test. Each holdout receives
ceil(20% of each class's groups). The manifest explicitly records
`stratified_normalized_text_holdout` and its limitation. Model metadata also records
that method. It is **within-corpus evaluation, not project-separated evaluation**.

| Split | FR | NFR | Total |
| --- | ---: | ---: | ---: |
| Training | 518 | 1,022 | 1,540 |
| Validation | 174 | 342 | 516 |
| Held-out test | 174 | 342 | 516 |

Each normalized requirement belongs to exactly one split; measured normalized-text
cross-split overlap is **zero**. Exact/case/whitespace-equivalent leakage is prevented.
Related requirements, paraphrases and near duplicates from the same unknown project
may still cross splits. These scores do not establish unseen-project generalization.
Grouping and counts were fixed before comparing models; no test-score-driven
assignment changes occurred.

The original annotation protocol, annotator identities and license were not supplied
or independently verified. Provenance states those absences without inventing names,
labels, adjudication or agreement. The user authorized local training; redistribution
rights are not asserted. Artifacts and raw data remain ignored by Git. Measured
scores evaluate agreement with the supplied Type labels, not independently
adjudicated requirement quality.

## Training, selection and measured results

Reused the existing scikit-learn Pipeline, restricted skops artifact loader,
training/validation reporting, freeze control and held-out evaluation command.
Added only a CSV adapter and explicit missing-project split fallback, with regression
checks. Existing default preparation still requires genuine project/document IDs.

Word TF-IDF uses lowercase unigrams/bigrams, no stop-word removal and a maximum
of 20,000 features. Logistic regression uses lbfgs, balanced class weights,
max_iter 1000 and seed 42. TF-IDF vocabulary/IDF and classifier coefficients/weights
were fitted **only on the 1,540 training examples**. No validation refit occurred.

The fixed candidate grid was C = 0.1, 1, 10; selection used validation macro-F1,
with smaller C as the declared tie-break. `selection_protocol.json` and
`selection.json` record the procedure and all validation trials. The final test
was not scored for any unselected candidate.

| C | Validation macro-F1 |
| --- | ---: |
| 0.1 | 0.834056 |
| 1 | 0.868428 |
| **10 — selected** | **0.892505** |

The selected C=10 artifact was frozen, then evaluated once through the existing
final-evaluation command on the held-out 516 examples. Test measurements:

| Class | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| FR | 0.882353 | 0.862069 | 0.872093 | 174 |
| NFR | 0.930636 | 0.941520 | 0.936047 | 342 |

**Test macro-F1: 0.904070.** No mocked predictions or training accuracy supply these
metrics. Full precision values and the confusion matrix are saved in
`research/models/dcai-v1/lr-c10/test_metrics.json`.

Confusion matrix, rows=true labels and columns=predicted labels, order `[FR, NFR]`:

| True / predicted | FR | NFR |
| --- | ---: | ---: |
| FR | 150 | 24 |
| NFR | 20 | 322 |

## Artifacts and checks

Selected local directory:

`/Users/chiranserasinghe/Documents/AI-SDLC AGILE/J26-SE-367-IntelliSE/component-1/backend/research/models/dcai-v1/lr-c10`

It contains `pipeline.skops`, `metadata.json`, `split_manifest.json`,
`validation_metrics.json`, `frozen.json` and `test_metrics.json`. The parent contains
all three trial artifacts, selection records and `verification.json`.

Model SHA-256/version:
`b48d2a3a87e3669957a1c5374c8879cd84fc1fe232e002a1c50c9821cb693823`

Recorded environment: Python **3.12.8**, scikit-learn **1.9.1**, numpy **2.5.4**,
scipy **1.18.1**, skops **0.16.0**. Existing optional dependencies and lock files
were reused; none were upgraded. Every model records dependency versions, seed,
configuration, dataset version, split ID, artifact hash and timestamp.

Checks completed:

- Original raw source and copied file have identical SHA-256; originals are unchanged.
- Every usable requirement belongs to one split, both labels occur in every split,
  and normalized texts have zero cross-split intersection.
- Artifact reload/hash/type/version checks pass; two independent reloads produce
  identical predictions. All vocabulary terms occur in training, and learned IDF
  values equal IDF computed from training document frequencies only.
- LocalClassifier loads the selected real research artifact. An existing classification
  POST with this real model returned 201 and FR/NFR predictions, GET latest returned
  the saved result, and original extraction documents/review status remained unchanged.
  These API checks used collection doubles, **not live MongoDB**.
- The ignored local `.env` now points C1_CLASSIFIER_MODEL_DIR at the selected model;
  no other environment setting was changed. A backend restart is required to load it.
- Affected preparation/model/classification suites: **49 passed**.
- Full backend suite: **193 passed, 6 skipped**. The skips require TEST_MONGODB_URI;
  the existing Starlette/httpx deprecation warning remains.
- `pip check`: no broken requirements. `git diff --check`: passed.

## Reproduce or inspect

From the repository root:

```sh
cd component-1/backend
.venv/bin/python -m pytest tests/test_baseline_data.py tests/test_baseline_model.py tests/test_dcai_data.py tests/test_classifications.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

Original import/preparation commands (outputs already exist; do not overwrite them):

```sh
.venv/bin/python -m intelise_c1.baseline import-dcai \
  --input '/Users/chiranserasinghe/Documents/AI-SDLC AGILE/Data Set/FR:NFR/dcai24_src_dataset.xlsx - Sheet1.csv' \
  --output research/raw/dcai-v1
.venv/bin/python -m intelise_c1.baseline prepare \
  --input research/raw/dcai-v1/examples.jsonl \
  --provenance research/raw/dcai-v1/provenance.json \
  --output research/prepared/dcai-v1 --grouping normalized_text \
  --seed 42 --validation-fraction 0.2 --test-fraction 0.2
.venv/bin/python -m intelise_c1.baseline train \
  --prepared research/prepared/dcai-v1 --output research/models/dcai-v1/lr-c01 --c 0.1 --seed 42
.venv/bin/python -m intelise_c1.baseline train \
  --prepared research/prepared/dcai-v1 --output research/models/dcai-v1/lr-c1 --c 1 --seed 42
.venv/bin/python -m intelise_c1.baseline train \
  --prepared research/prepared/dcai-v1 --output research/models/dcai-v1/lr-c10 --c 10 --seed 42
```

Compare only `validation_metrics.json` macro_f1; choose the maximum with smallest-C
tie-break. The stored selection.json records C=10. The following were run after
selection and cannot overwrite the existing freeze/test records:

```sh
.venv/bin/python -m intelise_c1.baseline freeze --model-dir research/models/dcai-v1/lr-c10
.venv/bin/python -m intelise_c1.baseline evaluate \
  --prepared research/prepared/dcai-v1 --model-dir research/models/dcai-v1/lr-c10
```

Use new versioned directories for intentional reproduction and retain the same
protocol; do not change model settings in response to the final test score.
To verify the existing artifact without training or rewriting test metrics:

```sh
.venv/bin/python - <<'PY'
from pathlib import Path
from intelise_c1.baseline.model import load_artifact
from intelise_c1.services.classifier import LocalClassifier
path = Path('research/models/dcai-v1/lr-c10')
pipeline, metadata = load_artifact(path)
print(metadata.model_identifier, metadata.model_version, metadata.evaluation_method)
print(LocalClassifier(path).predict(['Members can upload reports.', 'Reports must load within two seconds.']))
PY
```

From the repository root, also run `git diff --check`. The existing classification
API instructions in research/README.md apply unchanged.

## Exact next action

From `component-1/backend`, restart the backend with `.venv/bin/python -m intelise_c1`.
Ensure MongoDB is available, then POST classification for an actual saved project
and extraction run using the existing endpoint:

```sh
curl --fail-with-body -i -X POST \
  http://127.0.0.1:8001/api/v1/component-1/projects/PROJECT_ID/extractions/RUN_ID/classifications
```

Review the predictions. Before claiming project generalization or comparing BERT,
recover genuine project mappings and annotation provenance, assess near duplicates
and ambiguous/mixed labels, and prepare a new project-separated shared evaluation.
Do not retune this baseline against its already evaluated test split.
