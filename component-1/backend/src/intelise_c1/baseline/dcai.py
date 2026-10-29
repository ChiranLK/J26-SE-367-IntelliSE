"""Lossless CSV import with explicit quarantine and missing-project provenance.

This prepares inputs for the existing split/train/freeze/evaluate tooling.
It never treats Dataset_Name as a project ID or invents annotation labels.
"""
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path

from intelise_c1.baseline.data import DatasetError, LABELS, normalized_text, write_json

REQUIRED_COLUMNS = {"Requirement", "Type", "Specific_Type", "Security_Category", "Dataset_Name"}


def import_dcai(source: Path, output: Path):
    raw = source.read_bytes()
    if len(raw) > 50 * 1024 * 1024:
        raise DatasetError("DCAI input exceeds 50 MiB.")
    raw_hash = sha256(raw).hexdigest()
    with source.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        headers = reader.fieldnames
        if not headers or not REQUIRED_COLUMNS <= set(headers) or len(headers) != len(set(headers)):
            raise DatasetError("DCAI CSV requires unique Requirement, Type and original metadata columns.")
        rows = list(reader)
    if not rows or len(rows) > 50000 or any(None in row or None in row.values() for row in rows):
        raise DatasetError("DCAI CSV is empty, oversized or has malformed rows.")
    # A future export with project IDs must use reviewed project-aware import, not lose them.
    if any("project" in column.casefold() for column in headers):
        raise DatasetError("Project metadata detected; use a reviewed project mapping before importing.")
    groups = defaultdict(list)
    for index, row in enumerate(rows, 2):
        groups[normalized_text(row["Requirement"])].append(index)
    assignments, quarantined, examples, metadata, conflicts, duplicates = [], [], [], [], [], []
    disposition = {}
    for normalized, indices in groups.items():
        valid = [index for index in indices if rows[index - 2]["Type"] in LABELS
                 and rows[index - 2]["Requirement"].strip()
                 and len(rows[index - 2]["Requirement"]) <= 10000]
        labels = sorted({rows[index - 2]["Type"] for index in valid})
        text_hash = sha256(normalized.encode("utf-8")).hexdigest()
        if len(indices) > 1:
            duplicates.append({"normalized_text_hash": text_hash, "csv_records": indices,
                               "labels": sorted({rows[index - 2]["Type"] for index in indices})})
        if len(labels) > 1:
            conflicts.append({"normalized_text_hash": text_hash, "csv_records": valid, "labels": labels})
            for index in valid:
                disposition[index] = ("conflicting_labels", None)
        elif valid:
            representative = valid[0]  # Stable first source occurrence, original text retained.
            example_id = f"dcai:{raw_hash[:16]}:record:{representative}"
            row = rows[representative - 2]
            examples.append({"example_id": example_id, "text": row["Requirement"], "label": row["Type"],
                             "source_project_id": None,
                             "source_reference": f"{source.name}; sha256={raw_hash}; csv_record={representative}"})
            metadata.append({"example_id": example_id, "representative_csv_record": representative,
                             "source_records": [{"csv_record": index, "original_fields": rows[index - 2]} for index in valid]})
            for index in valid:
                disposition[index] = ("included" if index == representative else "same_label_duplicate", example_id)
        for index in indices:
            if index not in disposition:
                row = rows[index - 2]
                reason = "invalid_label" if row["Type"] not in LABELS else "invalid_text"
                disposition[index] = (reason, None)
    for index, row in enumerate(rows, 2):
        reason, representative = disposition[index]
        assignments.append({"csv_record": index, "disposition": reason, "representative_example_id": representative})
        if reason != "included":
            quarantined.append({"csv_record": index, "reason": reason, "representative_example_id": representative,
                                "original_fields": row})
    if any(len(item["text"]) > 10000 for item in examples):
        raise DatasetError("Requirement exceeds existing text bounds.")
    report = {"raw_source": str(source.resolve()), "raw_filename": source.name, "raw_sha256": raw_hash,
              "headers": headers, "raw_rows": len(rows), "raw_class_counts": dict(Counter(row["Type"] for row in rows)),
              "disposition_counts": dict(Counter(item["disposition"] for item in assignments)),
              "usable_rows": len(examples), "final_class_counts": dict(Counter(item["label"] for item in examples)),
              "normalization": "NFKC Unicode, casefold, whitespace collapse; detection only; original text unchanged",
              "duplicate_groups": duplicates, "conflicting_label_groups": conflicts,
              "source_collection_counts": dict(Counter(row["Dataset_Name"] for row in rows)),
              "genuine_project_ids_recovered": 0,
              "grouping_limitation": "No project IDs in supplied export. Dataset_Name denotes collections, not individual projects. Normalized-text holdout is within-corpus; it does not measure unseen-project generalization.",
              "csv_record_numbering": "Header is record 1; records are CSV logical records, not physical lines."}
    provenance = {"purpose": "research", "dataset_name": "User-supplied DCAI24 software requirements CSV",
                  "dataset_version": raw_hash,
                  "source_description": f"User-supplied {source.name}; exact raw SHA-256 {raw_hash}. Original metadata retained in source_metadata.jsonl. No project IDs are provided.",
                  "license_or_permission": "User explicitly authorized local preparation/training in this session. Original corpus license and redistribution permission were not supplied or independently verified; raw data/artifacts remain ignored by Git.",
                  "annotation_protocol": "Type is used verbatim as the binary target. Source annotation protocol is unavailable in the supplied export; no new labels, inferred labels or category remapping were performed.",
                  "annotators": ["Source annotator identities unavailable in the supplied export; no identity is asserted."],
                  "label_review": "No independent human reannotation or agreement measurement. #N/A/unsupported labels and invalid texts quarantined; all FR/NFR conflicts quarantined; same-label duplicates retain the first original row with all source metadata."}
    output.mkdir(parents=True, exist_ok=False)
    (output / source.name).write_bytes(raw)
    for name, values in [("examples.jsonl", examples), ("source_metadata.jsonl", metadata),
                         ("quarantine.jsonl", quarantined)]:
        (output / name).write_text("".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values), encoding="utf-8")
    write_json(output / "exclusion_report.json", report)
    write_json(output / "row_assignments.json", assignments)
    write_json(output / "provenance.json", provenance)
    if sha256(source.read_bytes()).hexdigest() != raw_hash or sha256((output / source.name).read_bytes()).hexdigest() != raw_hash:
        raise DatasetError("Raw file changed during import; do not use the prepared output.")
    return report
