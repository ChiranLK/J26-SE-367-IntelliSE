# Local DCAI baseline artifacts

Raw/prepared datasets, source-row metadata, per-example reports and all three
learned model binaries stay local. Dataset redistribution permission and a model
distribution/storage policy have not been established. User authorization for
local training does not establish those permissions. Existing backend ignore
rules cover `research/raw/`, `research/prepared/` and `research/models/`.
Do not add these directories wholesale or force ignored artifacts into Git.

The repository retains [aggregate results and identity hashes](dcai-v1-summary.json)
and the existing [preparation/evaluation report](dcai-baseline-report.md).
The aggregate JSON was derived from saved reports, not a new training/evaluation
run. It contains no requirement text, individual row/split assignments, personal
paths, credentials or model coefficients. Full provenance, exclusion reports,
split manifests, trials, freeze records and detailed metrics remain beside the
local data/models and in the recoverable local organization backup.

## Selected model and local application

From this backend checkout, the selected trusted local artifact directory is:

```text
research/models/dcai-v1/lr-c10
```

It contains pipeline.skops, metadata.json, split_manifest.json,
validation_metrics.json, frozen.json and test_metrics.json. C=10 was selected by
validation macro-F1 over C={0.1,1,10}; the frozen model's held-out macro-F1 was
0.9040697674418605. Hash identity and full per-class metrics are in the aggregate
summary. This is TF-IDF/logistic regression, not BERT. Evaluation is within-corpus
normalized-text holdout with seed 42; no genuine project IDs were recovered.
Dataset_Name is not a project identifier. Scores do not establish project-held-out
generalization or confidence for an individual prediction.

The local organization copied artifacts without overwriting destination files;
original copies were retained so existing absolute-path application configuration
continues to work. Each copied file and the selected binary hash were verified.
To use this checkout's own local copy, explicitly configure the ignored .env:

```dotenv
C1_CLASSIFIER_MODEL_DIR=research/models/dcai-v1/lr-c10
```

Restart from this backend checkout after changing configuration. No model is
downloaded or trained during normal API startup. Use matching baseline dependencies:

```sh
.venv/bin/python -m pip install -r requirements-baseline.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e '.[dev,baseline]'
.venv/bin/python -m pip check
.venv/bin/python - <<'PY'
from pathlib import Path
from intelise_c1.baseline.model import load_artifact
path = Path('research/models/dcai-v1/lr-c10')
pipeline, metadata = load_artifact(path)
print(metadata.model_identifier, metadata.model_version, metadata.evaluation_method)
PY
```

Only load an operator-trusted locally produced artifact whose hash/metadata match
the recorded model identity. Ignored does not mean deleted or unavailable.

## Obtain or reproduce

The binary is not distributed by this change. Use the preserved local original or
organization backup, or obtain the permission-backed source export from its owner.
The required file is `dcai24_src_dataset.xlsx - Sheet1.csv`, raw SHA-256
`b39a229a62c3c28186d5deb945b175da41f3f4ac7dbfddb787e8fd3e4abea49b`.
Do not substitute a different export and report its results as this run.

Reuse the existing CLI and [research procedure](README.md#dcai-csv-import). Use
fresh versioned output directories; the importer/trainer refuse to overwrite:

```sh
python -m intelise_c1.baseline import-dcai \
  --input '/path/to/authorized/dcai24_src_dataset.xlsx - Sheet1.csv' \
  --output research/raw/dcai-repro
python -m intelise_c1.baseline prepare \
  --input research/raw/dcai-repro/examples.jsonl \
  --provenance research/raw/dcai-repro/provenance.json \
  --output research/prepared/dcai-repro --grouping normalized_text \
  --seed 42 --validation-fraction 0.2 --test-fraction 0.2
python -m intelise_c1.baseline train --prepared research/prepared/dcai-repro \
  --output research/models/dcai-repro/lr-c01 --c 0.1 --seed 42
python -m intelise_c1.baseline train --prepared research/prepared/dcai-repro \
  --output research/models/dcai-repro/lr-c1 --c 1 --seed 42
python -m intelise_c1.baseline train --prepared research/prepared/dcai-repro \
  --output research/models/dcai-repro/lr-c10 --c 10 --seed 42
```

Compare validation macro-F1 only, with smaller C as tie-break; freeze the selected
candidate, then run the existing evaluate command on the held-out test. The
original selected C=10 run is already frozen/evaluated; do not retune it against
its test score. Preserve source license/annotation/grouping limitations and record
dependency versions, seed, dataset/split identities and artifacts for every new run.

For MongoDB availability checks see [the sanitized diagnosis](mongodb-diagnosis.md).
