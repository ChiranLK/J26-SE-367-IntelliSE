"""TF-IDF/logistic baseline and restricted, local skops artifact persistence."""
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
from typing import Literal
import warnings

from pydantic import BaseModel, ConfigDict, Field

from intelise_c1.baseline.data import DatasetError, LABELS, digest, load_prepared, write_json

PRODUCER = "intelise-c1-tfidf-logistic-v1"
LABEL_MAPPING = {"FR": "Functional Requirement", "NFR": "Non-Functional Requirement"}
DEPENDENCIES = ("scikit-learn", "numpy", "scipy", "skops")


class BaselineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    c: float = Field(default=1.0, gt=0, le=1000, allow_inf_nan=False)
    max_features: int = Field(default=20000, ge=100, le=100000)
    max_iter: int = Field(default=1000, ge=100, le=10000)
    seed: int = 42


class ArtifactMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: Literal[1]
    producer: Literal["intelise-c1-tfidf-logistic-v1"]
    purpose: Literal["research", "test"]
    model_identifier: Literal["tfidf-logistic-regression"]
    model_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    dataset_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    split_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_method: Literal["source_project_holdout", "stratified_normalized_text_holdout"] = "source_project_holdout"
    configuration: BaselineConfig
    label_mapping: dict[str, str]
    dependencies: dict[str, str]
    python_version: str
    created_at: str


def dependency_versions():
    return {name: version(name) for name in DEPENDENCIES}


def fit_pipeline(examples, config: BaselineConfig):
    """Low-level fit used by research training and test-only mechanical checks."""
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2), stop_words=None, max_features=config.max_features)),
        ("classifier", LogisticRegression(C=config.c, solver="lbfgs", class_weight="balanced", max_iter=config.max_iter, random_state=config.seed)),
    ])
    if {item.label for item in examples} != set(LABELS):
        raise DatasetError("Training needs both FR and NFR.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            pipeline.fit([item.text for item in examples], [item.label for item in examples])
    except (ValueError, ConvergenceWarning):
        raise DatasetError("Training failed: check usable vocabulary, class coverage and convergence settings.") from None
    return pipeline


def metrics(pipeline, examples):
    from sklearn.metrics import classification_report, confusion_matrix, f1_score

    truth = [item.label for item in examples]
    predictions = pipeline.predict([item.text for item in examples])
    report = classification_report(truth, predictions, labels=list(LABELS), output_dict=True, zero_division=0)
    return {"examples": len(examples), "source_project_count": len({item.source_project_id for item in examples if item.source_project_id is not None}),
            "class_counts": {label: truth.count(label) for label in LABELS},
            "per_class": {label: {key: report[label][key] for key in ("precision", "recall", "f1-score", "support")} for label in LABELS},
            "macro_f1": float(f1_score(truth, predictions, labels=list(LABELS), average="macro", zero_division=0)),
            "confusion_matrix": {"label_order": list(LABELS), "rows": "true", "columns": "predicted",
                                 "values": confusion_matrix(truth, predictions, labels=list(LABELS)).tolist()}}


def save_artifact(pipeline, directory: Path, manifest: dict, config: BaselineConfig):
    import skops.io as sio

    directory.mkdir(parents=True, exist_ok=False)
    blob = sio.dumps(pipeline)
    if sio.get_untrusted_types(data=blob):
        raise DatasetError("Pipeline contains unsupported artifact types; no dynamic trust expansion is allowed.")
    metadata = ArtifactMetadata(
        format_version=1, producer=PRODUCER, purpose=manifest["purpose"], model_identifier="tfidf-logistic-regression",
        model_version=sha256(blob).hexdigest(), dataset_version=manifest["dataset_version"], split_id=manifest["split_id"],
        evaluation_method=manifest.get("evaluation_method", "source_project_holdout"),
        configuration=config, label_mapping=LABEL_MAPPING, dependencies=dependency_versions(),
        python_version=platform.python_version(), created_at=datetime.now(timezone.utc).isoformat(),
    )
    (directory / "pipeline.skops").write_bytes(blob)
    write_json(directory / "metadata.json", metadata.model_dump())
    write_json(directory / "split_manifest.json", manifest)
    return metadata


def load_artifact(directory: Path, *, allow_test=False):
    """Only the operator-configured local directory; never accept request paths.

    Hashes detect corruption, not provenance. The operator must protect and trust
    the directory. Never automatically trust types discovered inside an artifact.
    """
    import skops.io as sio
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.utils.validation import check_is_fitted

    root = directory.resolve(strict=True)
    paths = [root / "metadata.json", root / "pipeline.skops", root / "split_manifest.json"]
    if any(path.is_symlink() or path.resolve(strict=True).parent != root for path in paths):
        raise DatasetError("Artifact files must be regular files inside the trusted directory.")
    if paths[0].stat().st_size > 1048576 or paths[1].stat().st_size > 64 * 1024 * 1024:
        raise DatasetError("Artifact exceeds loading size limits.")
    metadata = ArtifactMetadata.model_validate_json(paths[0].read_bytes())
    if (metadata.purpose != "research" and not allow_test) or metadata.label_mapping != LABEL_MAPPING:
        raise DatasetError("Only research-purpose artifacts with the FR/NFR mapping may serve predictions.")
    if metadata.dependencies != dependency_versions() or metadata.python_version.split('.')[:2] != platform.python_version().split('.')[:2]:
        raise DatasetError("Artifact dependency/Python versions do not match this environment.")
    if paths[2].stat().st_size > 20 * 1024 * 1024:
        raise DatasetError("Artifact split manifest exceeds loading limits.")
    split_manifest = json.loads(paths[2].read_text(encoding="utf-8"))
    if (split_manifest["dataset_version"] != metadata.dataset_version or split_manifest["split_id"] != metadata.split_id
        or split_manifest["purpose"] != metadata.purpose or split_manifest["seed"] != metadata.configuration.seed
        or digest(split_manifest["splits"]) != metadata.split_id):
        raise DatasetError("Artifact split manifest does not match model metadata.")
    if metadata.evaluation_method != split_manifest.get("evaluation_method", "source_project_holdout"):
        raise DatasetError("Artifact evaluation method differs from its split manifest.")
    blob = paths[1].read_bytes()
    if sha256(blob).hexdigest() != metadata.model_version or sio.get_untrusted_types(data=blob):
        raise DatasetError("Artifact hash/type validation failed.")
    pipeline = sio.loads(blob, trusted=[])
    if type(pipeline) is not Pipeline or list(pipeline.named_steps) != ["tfidf", "classifier"]:
        raise DatasetError("Unsupported pipeline.")
    vectorizer, classifier = pipeline.named_steps.values()
    if type(vectorizer) is not TfidfVectorizer or type(classifier) is not LogisticRegression:
        raise DatasetError("Unsupported baseline estimator types.")
    check_is_fitted(pipeline)
    if list(classifier.classes_) != list(LABELS):
        raise DatasetError("Artifact classes do not match FR/NFR.")
    config = metadata.configuration
    if (vectorizer.ngram_range != (1, 2) or vectorizer.stop_words is not None or vectorizer.max_features != config.max_features
        or not vectorizer.lowercase or classifier.C != config.c or classifier.max_iter != config.max_iter
        or classifier.solver != "lbfgs" or classifier.class_weight != "balanced" or classifier.random_state != config.seed):
        raise DatasetError("Artifact configuration differs from the documented baseline.")
    return pipeline, metadata


def train(prepared: Path, output: Path, config: BaselineConfig):
    examples, manifest, _provenance = load_prepared(prepared)
    if manifest["purpose"] != "research":
        raise DatasetError("Test fixtures cannot train a research model or produce research evaluation.")
    if config.seed != manifest["seed"]:
        raise DatasetError("Training seed must match the saved split seed.")
    by_id = {item.example_id: item for item in examples}
    training = [by_id[identifier] for identifier in manifest["splits"]["train"]]
    validation = [by_id[identifier] for identifier in manifest["splits"]["validation"]]
    pipeline = fit_pipeline(training, config)  # TF-IDF vocabulary/IDF fit only here.
    validation_metrics = metrics(pipeline, validation)
    metadata = save_artifact(pipeline, output, manifest, config)
    write_json(output / "validation_metrics.json", {"evaluation_split": "validation", "dataset_version": manifest["dataset_version"],
                                                   "split_id": manifest["split_id"], "dataset_and_split_sizes": manifest["sizes"], **validation_metrics})
    return metadata


def freeze(directory: Path):
    _pipeline, metadata = load_artifact(directory)
    marker = {"model_version": metadata.model_version, "configuration_hash": digest(metadata.configuration.model_dump()),
              "dataset_version": metadata.dataset_version, "split_id": metadata.split_id,
              "frozen_at": datetime.now(timezone.utc).isoformat()}
    with (directory / "frozen.json").open("x", encoding="utf-8") as file:
        json.dump(marker, file, indent=2, sort_keys=True)
        file.write("\n")


def evaluate(prepared: Path, directory: Path):
    pipeline, metadata = load_artifact(directory)
    examples, manifest, _provenance = load_prepared(prepared)
    if manifest["purpose"] != "research" or manifest["dataset_version"] != metadata.dataset_version or manifest["split_id"] != metadata.split_id:
        raise DatasetError("Evaluation data must match the model's research dataset and saved splits.")
    try:
        marker = json.loads((directory / "frozen.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise DatasetError("Freeze settings after validation model selection before final test evaluation.") from None
    if any(marker.get(key) != expected for key, expected in {
        "model_version": metadata.model_version, "configuration_hash": digest(metadata.configuration.model_dump()),
        "dataset_version": metadata.dataset_version, "split_id": metadata.split_id,
    }.items()):
        raise DatasetError("Frozen settings do not match this model/dataset.")
    report_path = directory / "test_metrics.json"
    if report_path.exists():
        raise DatasetError("Final test report already exists; do not use repeated test evaluation for model selection.")
    by_id = {item.example_id: item for item in examples}
    testing = [by_id[identifier] for identifier in manifest["splits"]["test"]]
    report = {"evaluation_split": "test", "model_version": metadata.model_version,
              "dataset_version": metadata.dataset_version, "split_id": metadata.split_id,
              "dataset_and_split_sizes": manifest["sizes"], **metrics(pipeline, testing)}
    with report_path.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2, sort_keys=True)
        file.write("\n")
    return report
