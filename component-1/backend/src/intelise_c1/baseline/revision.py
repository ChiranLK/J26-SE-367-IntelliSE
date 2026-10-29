"""Explicit experimental training-label revisions with inherited holdouts.

This is separate from the standard freshly stratified corpus preparation:
re-stratifying after label edits could move former test rows into training.
AI-assisted annotations must never be represented as human-verified labels.
"""
from copy import deepcopy
from hashlib import sha256

from intelise_c1.baseline.data import DatasetError, validate_splits


def text_hash(text):
    return sha256(text.encode("utf-8")).hexdigest()


def apply_reviews(examples, manifest, reviews):
    by_id = {item.example_id: item for item in examples}
    training = set(manifest["splits"]["train"])
    decisions = {}
    for review in reviews:
        identifier = review["example_id"]
        if identifier in decisions or identifier not in training:
            raise DatasetError("Review must refer once to an existing training example; holdout edits forbidden.")
        original = by_id[identifier]
        if review["original_label"] != original.label or review["text_sha256"] != text_hash(original.text):
            raise DatasetError("Review source text/label does not match the original example.")
        if review["decision"] not in {"FR", "NFR", "QUARANTINE"}:
            raise DatasetError("Invalid review decision.")
        if not review.get("rationale", "").strip() or not review.get("reviewer", "").strip() or not review.get("reviewed_at", "").strip():
            raise DatasetError("Review requires rationale, reviewer and timestamp.")
        if review.get("review_type") != "ai_assisted" or review.get("human_verified") is not False:
            raise DatasetError("This experimental revision must explicitly identify AI review without human verification.")
        decisions[identifier] = review["decision"]
    revised = [item.model_copy(update={"label": decisions.get(item.example_id, item.label)})
               for item in examples if decisions.get(item.example_id) != "QUARANTINE"]
    excluded = {identifier for identifier, decision in decisions.items() if decision == "QUARANTINE"}
    splits = deepcopy(manifest["splits"])
    splits["train"] = [identifier for identifier in splits["train"] if identifier not in excluded]
    validate_splits(revised, splits, manifest["group_key"])
    for split in ("validation", "test"):
        assert splits[split] == manifest["splits"][split]
        assert all(by_id[item.example_id].model_dump() == item.model_dump()
                   for item in revised if item.example_id in set(splits[split]))
    return revised, splits
