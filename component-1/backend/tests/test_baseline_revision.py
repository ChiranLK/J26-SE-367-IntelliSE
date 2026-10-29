from copy import deepcopy

import pytest

from intelise_c1.baseline.data import DatasetError, Example
from intelise_c1.baseline.revision import apply_reviews, text_hash


def fixture():
    examples = [Example(example_id=f"{split}-{label}-{index}", text=f"Distinct {split} {label} text {index}",
                        label=label, source_project_id=None, source_reference=f"source {split} {index}")
                for split in ("train", "validation", "test") for label in ("FR", "NFR")
                for index in range(2 if split == "train" else 1)]
    manifest = {"group_key": "normalized_text", "splits": {split: [item.example_id for item in examples if item.example_id.startswith(split)]
                                                          for split in ("train", "validation", "test")}}
    return examples, manifest


def review(item, decision="NFR"):
    return {"example_id": item.example_id, "original_label": item.label, "text_sha256": text_hash(item.text),
            "decision": decision, "rationale": "Explicit requirement policy review", "reviewer": "AI test reviewer",
            "review_type": "ai_assisted", "human_verified": False, "reviewed_at": "2026-10-16"}


def test_revisions_preserve_source_text_ids_metadata_and_both_holdouts():
    examples, manifest = fixture()
    originals = [item.model_dump() for item in examples]
    original_manifest = deepcopy(manifest)
    revised, splits = apply_reviews(examples, manifest, [review(examples[0])])
    assert revised[0].label == "NFR"
    assert revised[0].model_dump(exclude={"label"}) == examples[0].model_dump(exclude={"label"})
    assert [item.model_dump() for item in revised[1:]] == originals[1:]
    assert [item.model_dump() for item in examples] == originals
    assert splits == manifest["splits"] and manifest == original_manifest


def test_quarantine_removes_only_requested_training_example():
    examples, manifest = fixture()
    revised, splits = apply_reviews(examples, manifest, [review(examples[0], "QUARANTINE")])
    assert examples[0].example_id not in {item.example_id for item in revised}
    assert len(splits["train"]) == len(manifest["splits"]["train"]) - 1
    assert splits["test"] == manifest["splits"]["test"]
    assert splits["validation"] == manifest["splits"]["validation"]


@pytest.mark.parametrize("split", ["validation", "test"])
def test_holdout_edits_forbidden(split):
    examples, manifest = fixture()
    item = next(item for item in examples if item.example_id.startswith(split))
    with pytest.raises(DatasetError, match="holdout edits forbidden"):
        apply_reviews(examples, manifest, [review(item)])


@pytest.mark.parametrize("change", [{"text_sha256": "wrong"}, {"original_label": "NFR"},
                                   {"decision": "guessed"}, {"human_verified": True},
                                   {"review_type": "human"}, {"rationale": " "}, {"reviewed_at": ""}])
def test_mismatches_invalid_decisions_and_false_human_review_rejected(change):
    examples, manifest = fixture()
    with pytest.raises(DatasetError):
        apply_reviews(examples, manifest, [{**review(examples[0]), **change}])


def test_duplicate_reviews_and_loss_of_class_coverage_rejected():
    examples, manifest = fixture()
    with pytest.raises(DatasetError):
        apply_reviews(examples, manifest, [review(examples[0])] * 2)
    with pytest.raises(DatasetError, match="both FR and NFR"):
        apply_reviews(examples, manifest, [review(item, "QUARANTINE") for item in examples if item.example_id.startswith("train-FR")])
