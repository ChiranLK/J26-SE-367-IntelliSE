"""Offline, unlabelled PURE XML review preparation. Never creates training labels."""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from intelise_c1.baseline.data import normalized_text


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path, values):
    with Path(path).open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def requirements(path):
    """Preserve XML character data exactly, including inter-element whitespace.

    XML entity/newline decoding follows XML rules. Raw bytes remain in snapshot.
    A req tag is a source annotation, not proof of relevance or atomicity.
    """
    raw = Path(path).read_bytes()
    if len(raw) > 20_000_000:
        raise ValueError("XML exceeds the offline importer size limit")
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD/entity declarations are not accepted")
    root = ET.fromstring(raw)
    return [(element.get("id"), "".join(element.itertext())) for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] == "req"]


def prepare_pure(*, documents, xml, raw_output, output, dcai_csv, dcai_prepared, model_dir):
    """Snapshot originals, prepare an unlabelled sheet, run the existing model.

    Fresh output directories are required. On failure leave partial outputs for
    inspection; no existing source, model, API configuration or output is changed.
    """
    from intelise_c1.baseline.model import load_artifact

    if raw_output.exists() or output.exists():
        raise ValueError("Output already exists; choose fresh directories (no overwrite)")
    sources = {"documents": Path(documents), "xml": Path(xml)}
    for directory in sources.values():
        if not directory.is_dir():
            raise ValueError("Both source directories must exist")
    model_hash = sha256(model_dir / "pipeline.skops")
    pipeline, metadata = load_artifact(model_dir)
    raw_output.mkdir(parents=True)
    output.mkdir(parents=True)
    inventory = []
    for category, directory in sources.items():
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or any(part.startswith(".") for part in path.relative_to(directory).parts):
                continue
            if path.is_symlink():
                raise ValueError("Source symlinks are not accepted")
            relative = Path(category) / path.relative_to(directory)
            target = raw_output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            before = sha256(path)
            shutil.copy2(path, target)
            if before != sha256(target) or before != sha256(path):
                raise ValueError("Source changed during snapshot; inspect partial outputs")
            inventory.append({"path": relative.as_posix(), "sha256": before, "bytes": target.stat().st_size})
    write_json(raw_output / "inventory.json", inventory)

    old_rows = defaultdict(list)
    with dcai_csv.open(encoding="utf-8-sig", newline="") as stream:
        for index, row in enumerate(csv.DictReader(stream), 2):
            old_rows[normalized_text(row["Requirement"])].append({
                "csv_record": index, "label": row["Type"].strip(), "dataset_name": row.get("Dataset_Name"),
            })
    manifest = json.loads((dcai_prepared / "manifest.json").read_text())
    split_by_id = {item: split for split, ids in manifest["splits"].items() for item in ids}
    old_splits = {}
    for line in (dcai_prepared / "examples.jsonl").read_text().splitlines():
        item = json.loads(line)
        old_splits[normalized_text(item["text"])] = split_by_id[item["example_id"]]

    occurrences, excluded, document_counts = [], [], []
    for source in inventory:
        if not source["path"].startswith("xml/") or not source["path"].lower().endswith(".xml"):
            continue
        blocks = requirements(raw_output / source["path"])
        document_counts.append({"document": source["path"], "requirement_blocks": len(blocks)})
        for index, (source_id, text) in enumerate(blocks, 1):
            item = {"candidate_id": f"pure:{source['sha256'][:16]}:req:{index}", "text": text,
                    "source_document": source["path"], "source_sha256": source["sha256"],
                    "source_req_index": index, "source_req_id": source_id, "source_project_id": None}
            if not text.strip() or len(text) > 10000:
                excluded.append({**item, "reason": "empty_or_exceeds_existing_model_text_limit"})
            else:
                occurrences.append(item)
    grouped = defaultdict(list)
    for item in occurrences:
        grouped[normalized_text(item["text"])].append(item)
    candidates, duplicates, overlaps = [], [], []
    for key, items in grouped.items():
        candidate = {**items[0], "occurrence_ids": [item["candidate_id"] for item in items]}
        candidates.append(candidate)
        if len(items) > 1:
            duplicates.append({"representative_id": candidate["candidate_id"], "occurrence_ids": candidate["occurrence_ids"]})
        if key in old_rows:
            labels = sorted({row["label"] for row in old_rows[key] if row["label"] in {"FR", "NFR"}})
            overlaps.append({"candidate_id": candidate["candidate_id"], "dcai_records": old_rows[key],
                             "existing_labels": labels, "conflicting_labels": len(labels) > 1,
                             "existing_split": old_splits.get(key), "eligible_as_new_independent_data": False})
    # Suggestions are intentionally in a separate file, never the reviewed_label column.
    predictions = pipeline.predict([item["text"] for item in candidates]) if candidates else []
    suggestions = [{"candidate_id": item["candidate_id"], "suggested_label": str(label),
                    "model_version": metadata.model_version, "human_reviewed": False}
                   for item, label in zip(candidates, predictions, strict=True)]
    overlap_by_id = {item["candidate_id"]: item for item in overlaps}
    fields = ["candidate_id", "text", "source_document", "source_req_index", "source_req_id",
              "source_project_id", "existing_dcai_labels", "existing_dcai_split", "reviewed_label", "reviewer_id", "reviewed_at", "notes"]
    for filename, new_only in (("annotation_review.csv", False), ("new_only_review.csv", True)):
        with (output / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for item in candidates:
                match = overlap_by_id.get(item["candidate_id"])
                if new_only and match:
                    continue
                writer.writerow({**{key: item.get(key, "") for key in fields if key in item},
                                 "existing_dcai_labels": "|".join(match["existing_labels"]) if match else "",
                                 "existing_dcai_split": match["existing_split"] if match else ""})
    write_jsonl(output / "source_occurrences.jsonl", occurrences)
    write_jsonl(output / "unlabelled_candidates.jsonl", candidates)
    write_jsonl(output / "model_suggestions.jsonl", suggestions)
    write_json(output / "duplicates.json", duplicates)
    write_json(output / "dcai_overlap.json", overlaps)
    write_json(output / "exclusions.json", excluded)
    if sha256(model_dir / "pipeline.skops") != model_hash:
        raise ValueError("Existing model hash changed during preparation")
    summary = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "source_inventory_sha256": sha256(raw_output / "inventory.json"), "source_files": len(inventory),
        "xml_documents": len(document_counts), "documents": document_counts,
        "source_requirement_blocks": len(occurrences) + len(excluded), "excluded_blocks": len(excluded),
        "unique_candidates": len(candidates), "redundant_duplicate_occurrences": len(occurrences) - len(candidates),
        "dcai_overlap_unique": len(overlaps), "new_unique_candidates": len(candidates) - len(overlaps),
        "overlap_split_counts": dict(Counter(item["existing_split"] or "not_in_prepared" for item in overlaps)),
        "reviewed_labels": 0, "new_model_trained": False, "pure_accuracy": None, "pure_macro_f1": None,
        "model_version": metadata.model_version, "model_sha256_unchanged": model_hash,
        "suggested_class_counts_not_ground_truth": dict(Counter(str(item) for item in predictions)),
        "dcai_csv_sha256": sha256(dcai_csv), "existing_split_id": manifest["split_id"],
        "limitations": ["XML subset only; the 79 source documents have not been sentence-extracted.",
                        "No FR/NFR labels found; source req tags do not establish relevance or atomicity.",
                        "Document names are references, not verified individual project IDs. Related documents need grouping review.",
                        "Exact normalized matches only: paraphrases and related documents may also overlap DCAI.",
                        "Suggestions are not reference labels; no accuracy/F1 can be measured for PURE yet.",
                        "Source redistribution rights unverified; keep datasets local."],
    }
    write_json(output / "summary.json", summary)
    return summary
