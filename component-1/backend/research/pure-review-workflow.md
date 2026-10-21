# PURE review preparation and baseline charts

This is an offline research preparation step. It does not train or replace the
application model, change its configuration, or modify the frontend. Sources,
snapshots, review sheets, predictions and charts stay local under ignored
`research/raw/` and `research/prepared/`. Redistribution rights have not been
established. Do not commit the datasets or model binaries.

## What was found

The supplied download has 79 original documents and 18 XML files. Six XML files
contain 1,004 explicit `<req>` blocks. The other twelve contain no such blocks;
the importer does not manufacture requirements from their paragraphs. This is
**not extraction of all 34,268 sentences in the full corpus**.

Case/whitespace normalization (the existing baseline's NFKC/casefold/whitespace
normalization) gives 998 unique texts, six redundant occurrences, and 15 exact
matches against the existing DCAI corpus. Twelve matches belong to its training
split, two to validation and one to test. The new-only review sheet contains
983 texts. Paraphrases may produce further overlap; exact matching is not a
complete leakage audit.

No FR/NFR labels were found. `req` is a source annotation, not proof that a block
is atomic, relevant, or correctly classified. Document references are retained;
`source_project_id` is null. Related documents (including the EIRENE family)
need manual grouping review. Do not claim project-separated evaluation using
these filenames or `Dataset_Name` values as genuine project IDs.

## Local outputs

- `raw/pure-v1/`: byte-preserving snapshots of all 97 files and SHA-256 inventory.
- `prepared/pure-v1/source_occurrences.jsonl`: source wording and all occurrences.
- `prepared/pure-v1/unlabelled_candidates.jsonl`: deduplicated source wording.
- `prepared/pure-v1/annotation_review.csv`: all 998 unique candidates.
- `prepared/pure-v1/new_only_review.csv`: 983 candidates without exact DCAI overlap.
- `prepared/pure-v1/model_suggestions.jsonl`: existing-model predictions, explicitly
  unreviewed and separate from the blank reference-label column.
- `duplicates.json`, `dcai_overlap.json`, `exclusions.json`, `summary.json` in that
  preparation directory: retained source references and counts/limitations.
- `charts/`: six PNG/SVG charts, HTML gallery, chart manifest and a seven-page PDF.

XML character data is decoded using XML rules (including entities and line
endings) and joined in element order. No wording is rewritten or whitespace
normalization applied to the stored text. Raw XML is preserved separately.
DTD/entity declarations are rejected. IDs refer to a source hash and req index.
Snapshots verify source/copy hashes and refuse existing output directories.

The selected existing model suggested 225 FR and 773 NFR labels. Those numbers
are predictions, **not verified class counts or metrics**. There are zero
human-reviewed labels, no new trained model, and no measured PURE accuracy/F1.

## Chart interpretation

Accuracy/F1 charts read the **previously saved DCAI evaluation**, without another
fit, test evaluation or model selection. The fixed model is TF-IDF plus logistic
regression, C=10, seed 42; not BERT. Test results on 516 examples:

| Measure | FR | NFR |
| --- | ---: | ---: |
| Precision | 88.24% | 93.06% |
| Recall | 86.21% | 94.15% |
| F1 | 87.21% | 93.60% |

Macro-F1 is 90.41%. Accuracy, computed from the saved confusion matrix, is
472/516 = 91.47%. Matrix rows actual FR/NFR, columns predicted FR/NFR:
`[[150, 24], [20, 322]]`. The saved validation comparison selected C=10; test
results were not used to choose settings. This is a within-corpus normalized-text
holdout, not evidence of generalization to unseen projects or PURE. Aggregate
scores are not confidence scores for individual predictions. No training-history
or learning-curve measurements exist, so such curves were not fabricated.

## Reproduce

Use the existing backend worktree and invoke its interpreter directly; the
backend venv activation script may still contain its old absolute location.
Run these from `component-1/backend` in the backend worktree. Choose fresh
output names to repeat; existing results are deliberately never overwritten.

```sh
.venv/bin/python scripts/prepare_pure.py \
  --documents "$HOME/Downloads/req" \
  --xml "$HOME/Downloads/XMLZIPFile" \
  --raw-output research/raw/pure-v2 \
  --output research/prepared/pure-v2 \
  --dcai-csv 'research/raw/dcai-v1/dcai24_src_dataset.xlsx - Sheet1.csv' \
  --dcai-prepared research/prepared/dcai-v1 \
  --model-dir research/models/dcai-v1/lr-c10

.venv/bin/python -m pytest -q tests/test_pure_preparation.py tests/test_baseline_data.py tests/test_baseline_model.py
.venv/bin/python -m pytest -q tests/test_classifications.py
.venv/bin/python -m pip check
```

Plotting uses a separate environment, leaving the classifier/Whisper locks and
installed packages untouched. From the main repository root:

```sh
# Already installed locally; environment recreation only:
python3 -m venv .worktrees/_local-reports/plotting-env
.worktrees/_local-reports/plotting-env/bin/python -m pip install matplotlib==3.11.2 numpy==2.5.4

MPLCONFIGDIR=/private/tmp/intellise-c1-matplotlib \
.worktrees/_local-reports/plotting-env/bin/python \
  .worktrees/component-1-backend/component-1/backend/scripts/plot_pure_review.py \
  --prepared .worktrees/component-1-backend/component-1/backend/research/prepared/pure-v2 \
  --models .worktrees/component-1-backend/component-1/backend/research/models/dcai-v1
```

The chart manifest records plotting versions; the existing model metadata records
classifier dependency versions, seed, model/dataset/split identity. Raw inventories
and preparation summary identify the imported files and existing corpus hashes.

## Next action before training

Open `new_only_review.csv`. For each candidate, read its source context, fill
`reviewed_label` with FR or NFR, and record reviewer identity/date. FR describes
system behavior; NFR describes a quality or constraint. Record uncertain, mixed
or non-requirement cases in notes for adjudication; do not force labels. Keep
model suggestions out of the reference-label column. Preserve original wording;
any necessary splitting needs separately recorded evidence and review.

After genuine labels and related-document/project grouping are reviewed, adapt
them into the existing `Example`/`Provenance` schema and reuse the existing
`baseline prepare/train/freeze/evaluate` commands. Keep exact duplicate groups
together and quarantine conflicting labels; do not move old held-out examples
into training. Reserve validation for selection and a fresh locked test set for
final evaluation. Do not report improved performance until that evaluation runs.

## Verification performed

Preparation/baseline tests: 32 passed; classification API regression tests:
17 passed (one existing Starlette/httpx deprecation warning). These API tests
are automated regressions, not a new live-MongoDB or browser check. No API
implementation changed. Both backend and isolated plotting `pip check` passed.
All 97 source/snapshot hashes and 1,004 XML-text round trips passed; 998 review
rows have blank reference labels. The selected model hash was unchanged.
Verified six PNG/SVG chart pairs and seven PDF pages; visually inspected the
accuracy/F1 and preparation charts. See local `prepared/pure-v1/verification.json`
for artifact hashes. Existing staged frontend/backend work was preserved;
nothing was staged, committed or pushed by this task.
