"""STEP 1 - Select usable GenMyModel models from ModelSet.

Input : ModelSet clone (for genmymodel.db) + extracted raw XMI files
Output: data/manifest.csv  (id, xmi_path, diagram_type, domain, family)

Only the *labelled* part of ModelSet GenMyModel is used, because its metadata
tells us the diagram type (domainmodel = class diagram, usecase = use case
diagram), the domain, and a 'family' id that groups near-duplicate models.
'dummy' / 'unknown' domains are removed (test or junk models).

Usage (run from the codebert-uml-syntax folder):
  python step1_select_models.py ^
      --db  ..\\modelset-dataset\\datasets\\dataset.genmymodel\\data\\genmymodel.db ^
      --raw ..\\modelset-dataset\\raw-data
"""
import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

TYPE_MAP = {"domainmodel": "CLASS", "usecase": "USE_CASE"}
BAD_DOMAINS = {"dummy", "unknown"}


def first(value, default=""):
    """ModelSet labels are usually lists (["library"]) but can be plain strings."""
    if isinstance(value, list):
        return str(value[0]).strip().lower() if value else default
    return str(value).strip().lower() if value else default


def metadata_rows(con):
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    if "metadata" not in tables:
        raise SystemExit(f"No 'metadata' table in DB. Tables found: {tables}")
    cols = [r[1] for r in con.execute("PRAGMA table_info(metadata)")]
    json_col = next((c for c in ("json", "metadata") if c in cols), None)
    if json_col is None or "id" not in cols:
        raise SystemExit(f"Unexpected metadata columns: {cols} (run check_db.py)")
    return con.execute(f"SELECT id, {json_col} FROM metadata")


def resolve(raw: Path, mid: str):
    """id normally looks like repo-genmymodel-uml/data/<uuid>.xmi"""
    for p in (raw / mid, raw / "repo-genmymodel-uml" / "data" / Path(mid).name):
        if p.exists():
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--raw", required=True, help="folder that contains repo-genmymodel-uml/")
    ap.add_argument("--out", default="data/manifest.csv")
    a = ap.parse_args()

    db, raw = Path(a.db), Path(a.raw)
    if not db.is_file():
        raise SystemExit(f"DB not found: {db.resolve()}")
    if not (raw / "repo-genmymodel-uml").is_dir():
        raise SystemExit(f"'repo-genmymodel-uml' not found inside {raw.resolve()}")

    con = sqlite3.connect(db)
    rows, missing_examples, stats = [], [], Counter()
    for mid, js in metadata_rows(con):
        try:
            meta = json.loads(js)
        except (TypeError, json.JSONDecodeError):
            stats["bad_json"] += 1
            continue
        mtype = first(meta.get("type"))
        domain = first(meta.get("domain"), "unknown")
        if mtype not in TYPE_MAP or domain in BAD_DOMAINS:
            stats["skipped_type_or_domain"] += 1
            continue
        path = resolve(raw, mid)
        if path is None:
            stats["missing_file"] += 1
            if len(missing_examples) < 3:
                missing_examples.append(mid)
            continue
        family = first(meta.get("family"))
        if not family:
            stats["no_family"] += 1   # left empty: step 3 then groups by an element-name fingerprint
        rows.append({"id": mid, "xmi_path": str(path), "diagram_type": TYPE_MAP[mtype],
                     "domain": domain, "family": family})
        stats[TYPE_MAP[mtype]] += 1

    if not rows:
        raise SystemExit(f"0 models selected. stats={dict(stats)} missing examples={missing_examples}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"selected {len(rows)} models -> {a.out}")
    print("stats:", dict(stats))
    print("domains (top 10):", Counter(r["domain"] for r in rows).most_common(10))
    print("distinct families:", len({r['family'] for r in rows if r['family']}),
          "| models without family:", sum(1 for r in rows if not r['family']))
    if missing_examples:
        print("example missing ids:", missing_examples)


if __name__ == "__main__":
    main()