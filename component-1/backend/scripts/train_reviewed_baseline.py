"""Train one explicitly experimental, AI-reviewed candidate; never deploy it."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from intelise_c1.baseline.data import digest, inspect_rows, load_prepared, split_summary, write_json
from intelise_c1.baseline.model import BaselineConfig, fit_pipeline, freeze, load_artifact, metrics, save_artifact
from intelise_c1.baseline.pure import sha256, write_jsonl
from intelise_c1.baseline.revision import apply_reviews


def run(parent, reviews_path, output, model_output, revision_name="dcai-auth-ai-v1", review_scope="authentication"):
    if output.exists() or model_output.exists():
        raise ValueError("Outputs already exist; choose fresh directories")
    examples, old, provenance = load_prepared(parent)
    hashes = {path: sha256(path) for path in parent.iterdir() if path.is_file()}
    reviews = json.loads(reviews_path.read_text())
    revised, splits = apply_reviews(examples, old, reviews)
    _, validation = inspect_rows([item.model_dump() for item in revised], allow_missing_projects=True)
    if not validation["valid"]:
        raise ValueError("Revised data failed duplicate/schema validation")
    output.mkdir(parents=True)
    rows = [item.model_dump() for item in sorted(revised, key=lambda item: item.example_id)]
    revision_provenance = {**provenance.model_dump(), "dataset_name": f"DCAI training-only AI-assisted {review_scope} policy revision",
                           "dataset_version": revision_name, "annotators": ["Codex AI assistant (training subset only); original dataset annotators unknown"],
                           "annotation_protocol": f"Explicit per-record AI review of {review_scope} training examples; behaviour/permissions FR, qualities/technology NFR; quarantine ambiguous/mixed statements. No predictions supply labels.",
                           "label_review": "AI-assisted experimental annotations at user's request; NOT independently human-reviewed. Validation/test retain unchanged original source labels."}
    manifest = {**old, "dataset_version": digest({"examples": rows, "provenance": revision_provenance}),
                "split_id": digest(splits), "splits": splits, "sizes": split_summary(revised, splits, old["group_key"]),
                "created_at": datetime.now(timezone.utc).isoformat(), "annotation_status": "AI-assisted experimental; no human verification",
                "split_assignment_method": "inherited_parent_holdouts; training quarantines removed; NOT newly stratified",
                "parent_dataset_version": old["dataset_version"], "parent_split_id": old["split_id"],
                "reviews_sha256": sha256(reviews_path)}
    # Deliberately not standard manifest.json: ordinary prepare/load cannot
    # misidentify an inherited assignment as newly seeded stratification.
    write_jsonl(output / "examples.jsonl", rows)
    write_json(output / "provenance.json", revision_provenance)
    write_json(output / "revision_manifest.json", manifest)
    write_json(output / "reviews.json", reviews)
    write_json(output / "validation_report.json", validation)
    original_by_id = {item.example_id: item for item in examples}
    write_jsonl(output / "quarantine.jsonl", [original_by_id[row["example_id"]].model_dump() for row in reviews if row["decision"] == "QUARANTINE"])
    protocol = {"configuration": {"c": 30, "max_features": 20000, "seed": old["seed"]},
                "selection": "One fixed configuration inherited from previous validation-only selection; no further tuning after diagnostics.",
                "fit": "revised training examples only; no PURE, synthetic examples or diagnostic sentences",
                "evaluation": "unchanged old validation/test labels; reused test, mismatched label policy, supplementary only",
                "deployment": "Offline only; no application settings modified"}
    write_json(output / "protocol.json", protocol)
    by_id = {item.example_id: item for item in revised}
    started = time.monotonic()
    model = fit_pipeline([by_id[key] for key in splits["train"]], BaselineConfig(**protocol["configuration"]))
    val = metrics(model, [by_id[key] for key in splits["validation"]])
    metadata = save_artifact(model, model_output, manifest, BaselineConfig(**protocol["configuration"]))
    write_json(model_output / "validation_metrics.json", val)
    freeze(model_output)
    reloaded, _ = load_artifact(model_output)
    test = metrics(reloaded, [by_id[key] for key in splits["test"]])
    write_json(model_output / "test_metrics.json", {**test, "model_version": metadata.model_version,
                                                  "evaluation_note": protocol["evaluation"]})
    probes = [("Users must be able to log in using a username and password.", "FR"),
              ("Users must be able to view their current account balance.", "FR"),
              ("Users must be able to transfer funds between accounts and receive a confirmation notification.", "FR"),
              ("Only administrators can delete accounts.", "FR"),
              ("Search results must appear within two seconds.", "NFR"),
              ("The system must support 5,000 concurrent users.", "NFR"),
              ("All financial data and transactions must be encrypted using industry-standard protocols.", "NFR")]
    assert list(model.predict([item[0] for item in probes])) == list(reloaded.predict([item[0] for item in probes]))
    diagnostics = [{"text": text, "expected": expected, "actual": str(reloaded.predict([text])[0])} for text, expected in probes]
    assert all(sha256(path) == checksum for path, checksum in hashes.items())
    report = {"annotation_status": manifest["annotation_status"], "reviews": len(reviews),
              "changed_labels": sum(row["decision"] not in {row["original_label"], "QUARANTINE"} for row in reviews),
              "quarantined": sum(row["decision"] == "QUARANTINE" for row in reviews),
              "retained_original_labels": sum(row["decision"] == row["original_label"] for row in reviews),
              "split_sizes": manifest["sizes"], "model_version": metadata.model_version,
              "model_directory": str(model_output), "elapsed_seconds": time.monotonic()-started,
              "validation": val, "test": test, "diagnostics_not_independent_evaluation": diagnostics,
              "holdouts_unchanged": True, "source_dataset_unchanged": True,
              "reload_predictions_verified": True, "application_model_changed": False,
              "evaluation_limitations": protocol["evaluation"]}
    write_json(output / "report.json", report)
    print(json.dumps({key: report[key] for key in ("changed_labels", "quarantined", "retained_original_labels", "model_version", "elapsed_seconds")}, indent=2))
    print(json.dumps(diagnostics, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, default=Path("research/prepared/dcai-v1"))
    parser.add_argument("--reviews-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--revision-name", default="dcai-auth-ai-v1")
    parser.add_argument("--review-scope", default="authentication")
    run(**vars(parser.parse_args()))
