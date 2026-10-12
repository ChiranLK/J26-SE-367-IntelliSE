# Initial FR/NFR research baseline

This is a **TF-IDF + logistic regression** baseline implemented with a
scikit-learn `Pipeline`. It is not BERT, not the final proposed model, and not
an established research result. There is currently **no suitable real labeled
FR/NFR dataset in this repository**, so research training/evaluation is blocked.
Unreviewed extraction candidates do not supply ground-truth FR/NFR labels.

The only included labeled file is `tests/fixtures/fr_nfr_test.jsonl`: twelve
clearly fictional examples from six fictional documents, with test-only
provenance. Automated tests can fit a temporary test-purpose pipeline to verify
mechanics. The research training CLI and API loader reject test-purpose data and
artifacts. No trained research model, held-out research metrics, or accuracy
claim is supplied.

## Provenance and annotation

Store a permission-backed real labeled dataset outside Git, for example in the
ignored `research/raw/` directory. Dataset rows are UTF-8 JSONL, one object per
line, conforming to `dataset.schema.json`:

| Field | Requirement |
| --- | --- |
| `example_id` | Unique stable annotation/example identifier, 1–200 characters |
| `text` | Original atomic requirement text, nonblank, 1–10,000 characters |
| `label` | Exactly `FR` or `NFR`, provided by human annotation or a verified labeled source |
| `source_project_id` | Explicit canonical source project/document identifier, 1–200 characters |
| `source_reference` | Traceable original location: dataset row, document/page/paragraph, or saved extraction run + requirement/evidence IDs; 1–2,000 characters |

All fields are required. Unknown fields, missing/blank text, unsupported labels,
missing source groups, and padded IDs are rejected. The tooling never invents
IDs, fills missing groups, predicts annotation labels, or infers grouping from
row numbers. A source document can be the group when no project identifier
exists, using its **actual canonical document identifier**, recorded explicitly
in `source_project_id`. Related documents from the same project must use the
same project group. Review aliases and related/copy documents manually before
splitting: a grouping column cannot establish genuine independence by itself.

Include a separate provenance JSON conforming to `provenance.schema.json` with
`purpose: "research"`, `dataset_name`, `dataset_version`, `source_description`,
`license_or_permission`, `annotation_protocol`, nonempty `annotators`, and
`label_review`. These must describe actual sources, permission, annotation and
review, not placeholders. The tooling validates required metadata but cannot
independently authenticate its claims. Do not commit private discussions,
personal information, licensed corpora, or unapproved source documents.

Annotation procedure:

1. Establish an authorized corpus and a canonical source-group inventory. Check
   licenses/permission and retain genuine source references. **Do not assume
   PURE documents already have FR/NFR labels**; imported unlabeled documents
   require a documented annotation process. Verify any existing labels before use.
2. Identify atomic requirement examples while preserving actors, permissions,
   prohibitions, negation, conditions and constraints. FR describes a system
   capability/behavior, including permissions and prohibitions. NFR describes a
   quality attribute or constraint on operation, such as performance,
   availability, security or maintainability. Numeric business rules are not
   automatically NFR; security-related behavior is not automatically NFR.
3. Use independent annotators and record disagreements/adjudication. Consult
   source context for ambiguous cases. Mixed FR/NFR statements should be split
   into traceable atomic annotations where justified; quarantine unresolved or
   non-requirement examples instead of forcing a binary label. Record any
   segmentation policy and resulting references in the annotation protocol.
4. Resolve duplicate/conflicting labels with source review before freezing the
   corpus. Do not silently drop examples, choose a majority label, or create a
   new source ID to evade duplication/leakage checks. Measure annotation
   agreement only when genuine independent annotations exist; none is claimed here.
5. Record an immutable version and provenance. Review near duplicates manually;
   the automated detector handles exact text after NFKC Unicode normalization,
   case folding and whitespace collapse, not paraphrases/semantic similarity.
   This normalization is for duplicate detection only; saved example text stays
   unchanged.

## Install and prepare

From `component-1/backend` with its Python 3.12 environment active:

```sh
python -m pip install -r requirements-baseline.lock
python -m pip install --no-build-isolation --no-deps -e '.[dev,baseline]'
python -m pip check
```

The optional lock extends the unchanged API runtime/test lock. API health,
projects and extraction work without these baseline dependencies or a model.
The lock was resolved on Python 3.12.8/macOS x86_64; wheels/platform support may
vary elsewhere. Do not loosen version checks to load a different environment's
artifact. Regenerate and verify the optional lock deliberately when upgrading.

Once real reviewed labels and provenance exist, run:

```sh
python -m intelise_c1.baseline prepare \
  --input research/raw/requirements.jsonl \
  --provenance research/raw/provenance.json \
  --output research/prepared/v1 --seed 42 \
  --validation-fraction 0.2 --test-fraction 0.2
```

`prepare` validates all rows, rejects duplicate example IDs and duplicate text
(including conflicting labels), and records class/source-project counts. On
row-validation failure it writes `validation_report.json` and exits nonzero;
no split assignments are produced. Invalid JSON/provenance is a hard failure.
Reports contain IDs/counts/errors, not full requirement texts. Input is bounded
to 50 MiB, 50,000 rows, and 10,000 Unicode characters per requirement.

Successful output contains original `examples.jsonl`, `provenance.json`,
`validation_report.json`, and `manifest.json`. Dataset version is a SHA-256 digest
of canonical original examples and provenance, so annotation/provenance changes
invalidate it. The manifest records seed 42, split identifiers and example IDs,
source groups, counts and fractions. Existing output directories are never
overwritten.

Splits operate on whole `source_project_id` groups, not random rows. Validation
and test each use `ceil(group_count * fraction)` groups; the rest are training.
These are **group fractions**, not promised row fractions. There must be enough
independent groups for all three splits, and every split must contain both
classes. The splitter chooses the first coverage-valid assignment from at most
1,000 permutations of sorted groups under the fixed seed. It uses label coverage
only, never model performance; the chosen attempt is recorded. Inadequate class
coverage is a blocker, not a reason to invent groups or move individual rows.
Loading preparation output revalidates dataset hashes, assignments, coverage,
group separation, counts, seed/fractions and split identifier.

## Train, select on validation, freeze, evaluate

```sh
python -m intelise_c1.baseline train \
  --prepared research/prepared/v1 --output research/models/lr-c1 \
  --c 1.0 --seed 42
```

The pipeline uses lowercase word TF-IDF with unigrams/bigrams, no stop-word
removal (including negation), a 20,000-feature cap, and logistic regression with
`C=1.0`, `solver="lbfgs"`, `class_weight="balanced"`, `max_iter=1000`, and the
saved seed. Vocabulary, IDF, class weights and model coefficients are fitted
**only on training examples**. Failed vocabulary/convergence checks abort;
training is never performed during API startup or a classification request.

Output includes `pipeline.skops`, `metadata.json`, `split_manifest.json`, and
`validation_metrics.json`. Metadata records label mapping, exact artifact
SHA-256/model version, configuration, dataset version, split ID, creation time,
Python version and exact scikit-learn/numpy/scipy/skops dependency versions.
Validation metrics include per-class precision/recall/F1/support, macro-F1,
confusion matrix (rows=true, columns=predicted, label order `[FR,NFR]`), class and
source counts and dataset/split sizes. **No training accuracy is substituted for
held-out evaluation.** Training produces no final-test predictions or metrics.

If comparing values of C, train each to a new directory, e.g. `--c 0.5` with
`--output research/models/lr-c05`, and compare validation macro-F1/per-class
metrics only. Document the choices and selection procedure. Keep the final test
held out for model selection. Structural label coverage checks during preparation
are separate from using test data to fit/tune/score the model.

After settings are fixed using validation, freeze the chosen artifact:

```sh
python -m intelise_c1.baseline freeze --model-dir research/models/lr-c1
python -m intelise_c1.baseline evaluate \
  --prepared research/prepared/v1 --model-dir research/models/lr-c1
```

Final evaluation requires a matching freeze marker, dataset version and split ID
and writes `test_metrics.json` with measured held-out test metrics and sizes.
An existing report is never overwritten; rerunning final evaluation is rejected.
The marker/report are procedural controls, not protection against deliberate
operator changes. Do not remove them or train new variants based on test scores.
Retain all artifacts and the agreed evaluation protocol for reproducibility.

**Current measured research results: unavailable.** Run these commands only
when a suitable real annotated dataset has passed preparation. The test fixture
is not a substitute and must not be cited as a corpus/evaluation result.

## Trusted local model loading

Set `C1_CLASSIFIER_MODEL_DIR` to the chosen locally produced model directory in
the backend's ignored environment file, then restart. This is an explicit
operator trust decision: use artifacts from these tools in an operator-owned
protected directory, never downloaded/uploaded client artifacts. There is no
request parameter for artifact paths, no remote model fetch, and no upload API.

The lazy loader uses skops, **not pickle/joblib loading**. It rejects unknown
skops types rather than trusting a dynamically discovered list; checks the
producer/format, FR/NFR mapping, research purpose, file hash, model/split metadata,
matching dependencies/Python major-minor, and exact Pipeline/TF-IDF/logistic
estimator types/configuration. It rejects symlinked artifact files, oversized
files (1 MiB metadata, 64 MiB pipeline, 20 MiB split manifest), and mismatched
classes. A hash detects corruption; it does not prove origin or make an
untrusted directory safe. See [scikit-learn model persistence](https://scikit-learn.org/stable/model_persistence.html).

A successful load is cached per process; restart to switch artifacts. Loading
and prediction run in a worker thread. Missing dependencies/model, unsupported
versions, corrupt files, test-purpose artifacts and inference failures return
sanitized 503 responses. Health remains available. There is no keyword or LLM
fallback and no scores are returned; labels are model predictions, not approval.

## Classification API

Prefix: `/api/v1/component-1`. Use the actual saved project ObjectId and
extraction run UUID returned by the existing extraction POST:

```sh
curl --fail-with-body -i -X POST \
  http://127.0.0.1:8001/api/v1/component-1/projects/PROJECT_ID/extractions/RUN_ID/classifications
curl --fail-with-body -i \
  http://127.0.0.1:8001/api/v1/component-1/projects/PROJECT_ID/extractions/RUN_ID/classifications/latest
```

POST takes no body; it reads that exact saved extraction run, passes original
candidate texts unchanged to the trained pipeline, validates the complete
prediction-to-requirement mapping, and returns 201 after MongoDB acknowledges
a separate `classification_runs` document:

| Field | Value |
| --- | --- |
| `classification_id` | Server-generated UUID |
| `project_id` | Canonical saved project ObjectId string |
| `extraction_run_id` | Saved extraction UUID |
| `model_identifier` | `tfidf-logistic-regression` |
| `model_version` | SHA-256 of the locally produced pipeline artifact |
| `classified_at` | UTC ISO timestamp with BSON millisecond precision |
| `predictions` | Array of `{requirement_id: <original candidate ID>, label: "FR" or "NFR"}` in candidate order |

A valid empty extraction produces `predictions: []` **only when a trained model
is available**. Classification never rewrites original text, evidence, manual
requirements, extraction review status, or earlier classification runs. Results
remain predictions for human review; classification does not approve candidates.
GET latest returns 200, ordered by `classified_at` then ObjectId; it requires
MongoDB but no currently loaded classifier. No deduplication/automatic retries
or idempotency key exists; repeating POST appends another classification run.
An ambiguous MongoDB write failure can return 503 after the write reached the
server, as with extraction persistence.

Error details use existing FastAPI conventions:

- 422: malformed project ID or extraction UUID.
- 404: `Project not found.`, `Extraction run not found for this project.`, or
  `No classification found for this extraction run.`
- 503 classifier: `FR/NFR classifier unavailable. Configure a trusted locally trained research model and matching baseline dependencies.`
- 503 persistence: existing sanitized project-persistence detail, including
  project/extraction reads and classification write/index/latest failures.

The explicit run/project filter prevents classifying a run belonging to another
project. No provider calls occur in this API. Project/extraction endpoints keep
their existing contracts; classification has no frontend interface in this task.

## Verification and remaining BERT work

```sh
python -m pytest
# Optional real MongoDB tests, in generated disposable databases only:
TEST_MONGODB_URI=mongodb://127.0.0.1:27017 python -m pytest
```

Tests cover invalid/missing annotations, duplicate/conflicting labels, class and
source counts, reproducible/group-separated splits, missing evaluation classes,
prepared-data tampering, train-only vocabulary, temporary test-purpose pipeline
save/load equivalence, corrupt/untrusted artifacts, fixture rejection, mocked
validation/test control flow, exact requirement mapping, empty results,
missing project/extraction/model, database failures, latest ordering and
append-only runs. Real-MongoDB restart persistence tests use mocked classifiers
and skip without `TEST_MONGODB_URI`. Fixed-prediction metric arithmetic checks
are tests of reporting code, not scientific model evaluation. Existing project,
extraction, health and CORS tests still run. No real trained classifier or live
classification verification is possible until real annotated data is available.

TF-IDF/logistic regression lacks contextual representations and may misread
negation, ambiguity, domain shifts and mixed requirements. Binary labels depend
on the annotation policy; class imbalance and source leakage can distort metrics.
Do not infer calibrated confidence or research accuracy from an individual label.

The proposed BERT comparison remains separate future work: obtain/adjudicate
real labels, freeze a shared source-group split, tune each model on training and
validation only, then compare per-class metrics, macro-F1 and confusion matrices
on the same untouched final test under a predeclared protocol. Document tokenizer,
architecture/checkpoint, training settings, seeds, resources and model versions.
No BERT model or comparison findings are implemented or claimed here.

**Exact next action:** acquire an authorized real requirement corpus, supply
reviewed FR/NFR annotations with genuine canonical source groups/references and
provenance, then run the preparation command above. If all splits pass class and
leakage checks, proceed with validation-only baseline training and model selection.
