"""Bounded offline experiments using existing source labels, never pseudo-labels.

Run from backend with its existing .venv. All outputs require a fresh directory.
Application settings and existing datasets/artifacts are never written.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

from intelise_c1.baseline.data import load_prepared, normalized_text, write_json
from intelise_c1.baseline.model import BaselineConfig, evaluate, freeze, load_artifact, train
from intelise_c1.baseline.pure import sha256

LOGIN = "Users must be able to log in using a username and password."
AUTH = re.compile(r"\b(log[ -]?in|sign[ -]?in|authenticat\w*|password\w*|username\w*)\b", re.I)
# Declared before any new trial runs. No label edits, seed search or test selection.
TRIALS = [(3, 20000), (30, 20000), (100, 20000), (10, 50000), (30, 50000)]


def explain(pipeline, text):
    vectorizer = pipeline.named_steps["tfidf"]
    classifier = pipeline.named_steps["classifier"]
    assert list(classifier.classes_) == ["FR", "NFR"]
    row = vectorizer.transform([text])
    names = vectorizer.get_feature_names_out()
    features = [{"feature": str(names[index]), "nfr_logit_contribution": float(value * classifier.coef_[0, index])}
                for index, value in zip(row.indices, row.data, strict=True)]
    return {"text": text, "prediction": str(pipeline.predict([text])[0]),
            "intercept_nfr_logit": float(classifier.intercept_[0]),
            "decision_nfr_logit": float(pipeline.decision_function([text])[0]),
            "features": sorted(features, key=lambda item: -abs(item["nfr_logit_contribution"])),
            "interpretation": "Positive contributions favor NFR; negative favor FR. Association is not semantic verification."}


def review_batch(training, pipeline, pure, output):
    """Prioritize training label audit and document-diverse unlabelled review.

    Neither existing source labels nor suggestions fill reviewed_label.
    Validation/test examples are not offered as editable training annotations.
    """
    auth = [item for item in training if AUTH.search(item.text)]
    predicted = pipeline.predict([item.text for item in auth]) if auth else []
    ranked = sorted(zip(auth, predicted), key=lambda pair: (pair[0].label == pair[1], pair[0].example_id))
    rows = [{"example_id": item.example_id, "text": item.text, "source_reference": item.source_reference,
             "review_purpose": "audit_existing_training_label", "existing_source_label": item.label,
             "model_suggestion_unreviewed": str(label)} for item, label in ranked[:25]]
    with pure.open(encoding="utf-8", newline="") as stream:
        by_document = defaultdict(list)
        for item in csv.DictReader(stream):
            by_document[item["source_document"]].append(item)
    # Round robin is annotation workload sampling, NOT an evaluation split.
    new = []
    while len(new) < 25 and any(by_document.values()):
        for document in sorted(by_document):
            if by_document[document] and len(new) < 25:
                new.append(by_document[document].pop(0))
    labels = pipeline.predict([item["text"] for item in new]) if new else []
    rows.extend({"example_id": item["candidate_id"], "text": item["text"],
                 "source_reference": f"{item['source_document']}; req_index={item['source_req_index']}",
                 "review_purpose": "new_pure_label_and_relevance_review", "existing_source_label": "",
                 "model_suggestion_unreviewed": str(label)} for item, label in zip(new, labels, strict=True))
    fields = ["example_id", "text", "source_reference", "review_purpose", "existing_source_label",
              "model_suggestion_unreviewed", "reviewed_label", "reviewer_id", "reviewed_at", "notes"]
    # Blind sheet first; suggestions available separately to reduce anchoring.
    for name, suggestions in (("review_batch.csv", False), ("review_batch_with_suggestions.csv", True)):
        with (output / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for item in rows:
                writer.writerow({**item, "model_suggestion_unreviewed": item["model_suggestion_unreviewed"] if suggestions else ""})
    return len(rows)


def run(prepared, baseline, pure_review, output):
    if output.exists():
        raise ValueError("Output exists; use a fresh output directory")
    examples, manifest, _ = load_prepared(prepared)
    snapshots = {path: sha256(path) for directory in (prepared, baseline) for path in directory.iterdir() if path.is_file()}
    pipeline, metadata = load_artifact(baseline)
    by_id = {item.example_id: item for item in examples}
    training = [by_id[key] for key in manifest["splits"]["train"]]
    output.mkdir(parents=True)
    protocol = {"created_at": datetime.now(timezone.utc).isoformat(), "trial_grid": TRIALS,
                "seed": manifest["seed"], "dataset_version": manifest["dataset_version"], "split_id": manifest["split_id"],
                "fit_data": "existing training source labels only; no new labels or label changes",
                "selection": "validation macro-F1; tie: smaller max_features then smaller C; baseline wins equal score",
                "test_policy": "Only selected new candidate evaluated once after freezing. Existing test is reused: supplementary, not fresh independent evidence.",
                "deployment": "No application configuration changes; candidate remains offline",
                "pure_policy": "No human-reviewed labels available. PURE excluded from training/evaluation."}
    write_json(output / "protocol.json", protocol)
    auth = [item for item in training if AUTH.search(item.text)]
    auth_predictions = pipeline.predict([item.text for item in auth]) if auth else []
    audit = {"training_class_counts": dict(Counter(item.label for item in training)),
             "authentication_training_class_counts": dict(Counter(item.label for item in auth)),
             "authentication_training_errors_against_source_labels": sum(item.label != pred for item, pred in zip(auth, auth_predictions)),
             "login_exact_match_in_training": [item.example_id for item in training if normalized_text(item.text) == normalized_text(LOGIN)],
             "login_explanation": explain(pipeline, LOGIN),
             "annotation_batch_rows": review_batch(training, pipeline, pure_review, output),
             "notes": "Source-label disagreements need review; no labels automatically corrected. Counts do not establish annotation accuracy."}
    write_json(output / "audit.json", audit)
    previous = json.loads((baseline / "validation_metrics.json").read_text())
    trials = [{"path": "baseline", "c": metadata.configuration.c, "max_features": metadata.configuration.max_features,
               "validation_macro_f1": previous["macro_f1"], "model_version": metadata.model_version, "seconds": None}]
    for c, max_features in TRIALS:
        directory = output / f"lr-c{c}-features{max_features}"
        started = time.monotonic()
        saved = train(prepared, directory, BaselineConfig(c=c, max_features=max_features, seed=manifest["seed"]))
        validation = json.loads((directory / "validation_metrics.json").read_text())
        trials.append({"path": directory.name, "c": c, "max_features": max_features,
                       "validation_macro_f1": validation["macro_f1"], "model_version": saved.model_version,
                       "seconds": time.monotonic() - started})
        write_json(output / "trial_results.json", trials)
        print(json.dumps(trials[-1]), flush=True)
    winner = min(trials, key=lambda item: (-item["validation_macro_f1"], item["path"] != "baseline", item["max_features"], item["c"]))
    selected = baseline if winner["path"] == "baseline" else output / winner["path"]
    # Selection is now fixed; diagnostic examples never select the winner.
    write_json(output / "selection.json", {"selected": winner, "trials": trials, "protocol": protocol})
    if selected != baseline:
        freeze(selected)
        test = evaluate(prepared, selected)
    else:
        test = json.loads((baseline / "test_metrics.json").read_text())
    candidate, saved = load_artifact(selected)
    probes = [
        (LOGIN, "FR"),
        ("Users must be able to view their current account balance.", "FR"),
        ("Users must be able to transfer funds between accounts and receive a confirmation notification.", "FR"),
        ("Search results must appear within two seconds.", "NFR"),
        ("The system must support 5,000 concurrent users.", "NFR"),
        ("Only administrators can delete accounts.", "FR"),
    ]
    old_predictions = pipeline.predict([text for text, _ in probes])
    new_predictions = candidate.predict([text for text, _ in probes])
    smoke = [{"text": text, "expected_review_draft": expected, "baseline_prediction": str(old), "candidate_prediction": str(new)}
             for (text, expected), old, new in zip(probes, old_predictions, new_predictions, strict=True)]
    assert all(sha256(path) == checksum for path, checksum in snapshots.items()), "Existing dataset/model changed"
    report = {"selected": winner, "candidate_model_directory": str(selected), "reload_verified": True,
              "test_metrics": {key: test[key] for key in ("macro_f1", "per_class", "confusion_matrix")},
              "diagnostics_not_independent_evaluation": smoke, "login_explanation": explain(candidate, LOGIN),
              "unchanged_existing_files_verified": len(snapshots), "pure_training_examples_used": 0,
              "application_model_changed": False,
              "limitations": ["Original source labels unreviewed independently; project IDs unavailable.",
                              "Same original normalized-text test holdout reused for supplementary comparison; not a fresh test set.",
                              "Six illustrative diagnostic examples are not a representative benchmark and were not added to training.",
                              "New PURE reference labels still need human review; no new-corpus generalization claim."]}
    write_json(output / "report.json", report)
    print(json.dumps({"selected": winner, "diagnostic_login_prediction": smoke[0]["candidate_prediction"], "application_model_changed": False}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, default=Path("research/prepared/dcai-v1"))
    parser.add_argument("--baseline", type=Path, default=Path("research/models/dcai-v1/lr-c10"))
    parser.add_argument("--pure-review", type=Path, default=Path("research/prepared/pure-v1/new_only_review.csv"))
    parser.add_argument("--output", type=Path, required=True)
    run(**vars(parser.parse_args()))
