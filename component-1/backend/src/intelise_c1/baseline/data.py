"""Strict labeled JSONL validation and reproducible source-group holdouts."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import random
from typing import Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

LABELS = ("FR", "NFR")
SPLITS = ("train", "validation", "test")
DEFAULT_SEED = 42


class DatasetError(ValueError):
    """Sanitized dataset/preparation error; never prints requirement texts."""


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    example_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=10000)
    label: Literal["FR", "NFR"]
    source_project_id: str = Field(min_length=1, max_length=200)
    source_reference: str = Field(min_length=1, max_length=2000)

    @field_validator("example_id", "text", "source_project_id", "source_reference")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Must not be blank")
        return value  # Preserve all text; do not infer IDs or labels.

    @field_validator("example_id", "source_project_id")
    @classmethod
    def canonical_identifier(cls, value):
        if value != value.strip():
            raise ValueError("IDs must not contain leading/trailing whitespace")
        return value


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    purpose: Literal["research", "test"]
    dataset_name: str
    dataset_version: str
    source_description: str
    license_or_permission: str
    annotation_protocol: str
    annotators: list[str] = Field(min_length=1)
    label_review: str

    @field_validator("dataset_name", "dataset_version", "source_description", "license_or_permission", "annotation_protocol", "label_review")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Provenance fields must not be blank")
        return value

    @field_validator("annotators")
    @classmethod
    def named_annotators(cls, value):
        if any(not item.strip() for item in value):
            raise ValueError("Annotator IDs must not be blank")
        return value


def digest(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def inspect_rows(rows: list[dict]) -> tuple[list[Example], dict]:
    examples, issues = [], []
    for line, row in enumerate(rows, 1):
        try:
            examples.append(Example.model_validate(row))
        except ValidationError as error:
            issues.append({"line": line, "code": "invalid_example", "fields": [".".join(map(str, item["loc"])) for item in error.errors()]})
    if not rows:
        issues.append({"code": "empty_dataset"})
    ids, texts = defaultdict(list), defaultdict(list)
    for example in examples:
        ids[example.example_id].append(example)
        normalized = " ".join(unicodedata.normalize("NFKC", example.text).casefold().split())
        texts[normalized].append(example)
    duplicate_ids = sorted(key for key, values in ids.items() if len(values) > 1)
    if duplicate_ids:
        issues.append({"code": "duplicate_example_ids", "example_ids": duplicate_ids})
    duplicates = []
    for values in texts.values():
        if len(values) > 1:
            labels = sorted({item.label for item in values})
            duplicates.append({"example_ids": sorted(item.example_id for item in values),
                               "source_project_ids": sorted({item.source_project_id for item in values}),
                               "labels": labels, "conflicting_labels": len(labels) > 1})
    duplicates.sort(key=lambda value: value["example_ids"])
    for duplicate in duplicates:
        issues.append({"code": "conflicting_labels" if duplicate["conflicting_labels"] else "duplicate_text", **duplicate})
    report = {"total_rows": len(rows), "valid_rows": len(examples),
              "class_counts": {label: sum(item.label == label for item in examples) for label in LABELS},
              "source_project_count": len({item.source_project_id for item in examples}),
              "source_project_counts": dict(sorted(Counter(item.source_project_id for item in examples).items())),
              "duplicates": duplicates, "issues": issues, "valid": not issues}
    return examples, report


def read_dataset(path: Path):
    try:
        # Bound research input; annotations can be prepared in explicit versions.
        if path.stat().st_size > 50 * 1024 * 1024:
            raise DatasetError("Dataset exceeds the 50 MiB preparation limit.")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as error:
        if isinstance(error, DatasetError):
            raise
        raise DatasetError("Cannot read dataset JSONL. Check its path, encoding and JSON syntax.") from None
    if len(rows) > 50000:
        raise DatasetError("Dataset exceeds 50,000 examples.")
    return inspect_rows(rows)


def read_provenance(path: Path) -> Provenance:
    try:
        return Provenance.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        raise DatasetError("Provenance must include purpose, dataset/version, sources, permission, annotation protocol, annotators and label review.") from None


def split_groups(examples: list[Example], seed: int = DEFAULT_SEED, validation_fraction: float = .2, test_fraction: float = .2):
    if not 0 < validation_fraction < 1 or not 0 < test_fraction < 1 or validation_fraction + test_fraction >= 1:
        raise DatasetError("Validation/test group fractions must be positive and sum to less than one.")
    groups = sorted({item.source_project_id for item in examples})
    n_validation, n_test = ceil(len(groups) * validation_fraction), ceil(len(groups) * test_fraction)
    if len(groups) - n_validation - n_test < 1:
        raise DatasetError("Need enough independent source groups for three nonempty splits.")
    generator = random.Random(seed)
    # First coverage-valid assignment only; never select a split using model scores.
    for attempt in range(1000):
        ordered = generator.sample(groups, len(groups))
        selected = {"test": set(ordered[:n_test]), "validation": set(ordered[n_test:n_test + n_validation]),
                    "train": set(ordered[n_test + n_validation:])}
        splits = {name: sorted(item.example_id for item in examples if item.source_project_id in selected[name]) for name in SPLITS}
        try:
            validate_splits(examples, splits)
        except DatasetError:
            continue
        return splits, attempt
    raise DatasetError("No source-group split with both classes in every split found in 1,000 seeded attempts. Review source coverage; do not move individual examples or fabricate groups.")


def validate_splits(examples: list[Example], splits: dict):
    if set(splits) != set(SPLITS) or any(not isinstance(splits[name], list) for name in SPLITS):
        raise DatasetError("Expected train, validation and test assignments.")
    by_id = {item.example_id: item for item in examples}
    flat = [identifier for name in SPLITS for identifier in splits[name]]
    if len(flat) != len(set(flat)) or set(flat) != set(by_id):
        raise DatasetError("Every example must occur in exactly one split.")
    seen_groups = set()
    for name in SPLITS:
        subset = [by_id[identifier] for identifier in splits[name]]
        groups = {item.source_project_id for item in subset}
        if groups & seen_groups:
            raise DatasetError("Source groups overlap across splits.")
        seen_groups |= groups
        if {item.label for item in subset} != set(LABELS):
            raise DatasetError("Every training/evaluation split must contain both FR and NFR.")


def split_summary(examples, splits):
    by_id = {item.example_id: item for item in examples}
    return {name: {"examples": len(ids), "source_groups": sorted({by_id[identifier].source_project_id for identifier in ids}),
                   "class_counts": {label: sum(by_id[identifier].label == label for identifier in ids) for label in LABELS}}
            for name, ids in splits.items()}


def prepare(dataset: Path, provenance_path: Path, output: Path, seed=DEFAULT_SEED, validation_fraction=.2, test_fraction=.2):
    examples, report = read_dataset(dataset)
    provenance = read_provenance(provenance_path)
    if "fixtures" in dataset.parts and provenance.purpose != "test":
        raise DatasetError("Files in fixture directories must be explicitly marked test-only.")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "validation_report.json", report)
    if not report["valid"]:
        raise DatasetError("Dataset validation failed. Inspect validation_report.json; resolve duplicates/conflicting labels before splitting.")
    splits, attempt = split_groups(examples, seed, validation_fraction, test_fraction)
    rows = [item.model_dump() for item in sorted(examples, key=lambda item: item.example_id)]
    dataset_version = digest({"examples": rows, "provenance": provenance.model_dump()})
    (output / "examples.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    write_json(output / "provenance.json", provenance.model_dump())
    manifest = {"format_version": 1, "dataset_version": dataset_version, "purpose": provenance.purpose,
                "seed": seed, "group_key": "source_project_id", "validation_group_fraction": validation_fraction,
                "test_group_fraction": test_fraction, "coverage_attempt": attempt,
                "split_id": digest(splits), "splits": splits, "sizes": split_summary(examples, splits),
                "created_at": datetime.now(timezone.utc).isoformat()}
    write_json(output / "manifest.json", manifest)
    return manifest


def load_prepared(directory: Path):
    examples, report = read_dataset(directory / "examples.jsonl")
    provenance = read_provenance(directory / "provenance.json")
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        rows = [item.model_dump() for item in sorted(examples, key=lambda item: item.example_id)]
        if not report["valid"] or manifest["format_version"] != 1 or manifest["purpose"] != provenance.purpose:
            raise DatasetError("Invalid prepared dataset metadata or examples.")
        if manifest["dataset_version"] != digest({"examples": rows, "provenance": provenance.model_dump()}):
            raise DatasetError("Prepared dataset version does not match its examples/provenance.")
        validate_splits(examples, manifest["splits"])
        if manifest["split_id"] != digest(manifest["splits"]) or manifest["sizes"] != split_summary(examples, manifest["splits"]):
            raise DatasetError("Prepared split identifiers/counts do not match assignments.")
        if manifest["group_key"] != "source_project_id" or type(manifest["seed"]) is not int:
            raise DatasetError("Invalid grouping key or seed.")
        expected, attempt = split_groups(examples, manifest["seed"], manifest["validation_group_fraction"], manifest["test_group_fraction"])
        if expected != manifest["splits"] or attempt != manifest["coverage_attempt"]:
            raise DatasetError("Saved assignments do not match the recorded seed/fractions.")
        return examples, manifest, provenance
    except (OSError, ValueError, KeyError, TypeError) as error:
        if isinstance(error, DatasetError):
            raise
        raise DatasetError("Invalid prepared dataset manifest.") from None
