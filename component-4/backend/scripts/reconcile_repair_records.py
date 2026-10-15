#!/usr/bin/env python3
"""
INTELISE Historical Repair Record Reconciliation Script

Purpose:
  Safely and idempotently reconciles historical repair attempts that were incorrectly
  marked REVERIFIED even though no genuine re-verification run executed (corrected_run_id is null/none
  and defect resolution verdict is INCONCLUSIVE).

Usage:
  # Dry-run inspection (default, non-destructive):
  python scripts/reconcile_repair_records.py --dry-run

  # Target a specific repair attempt in dry-run mode:
  python scripts/reconcile_repair_records.py --repair-id rep-5f900fb0183d --dry-run

  # Apply changes to MongoDB Atlas after review:
  python scripts/reconcile_repair_records.py --repair-id rep-5f900fb0183d --apply
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo import MongoClient

# Ensure backend root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings


def is_inconsistent_repair_doc(doc: Dict[str, Any]) -> bool:
    """
    Evaluates whether a database document exhibits the inconsistent REVERIFIED lifecycle anomaly:
    - Status is REVERIFIED or VERIFIED
    - corrected_run_id is null, missing, or 'none'/'null'
    - comparison.verdict is INCONCLUSIVE
    """
    status = str(doc.get("status", "")).upper()
    if status not in ("REVERIFIED", "VERIFIED"):
        return False

    corr_run_id = doc.get("corrected_run_id")
    no_run = not corr_run_id or str(corr_run_id).strip().lower() in ("none", "null", "")

    comp = doc.get("comparison") or {}
    verdict = comp.get("verdict", "")
    is_inconclusive = str(verdict).upper() == "INCONCLUSIVE"

    return no_run and is_inconclusive


def find_inconsistent_records(
    col: Any,
    repair_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Queries and returns all matching inconsistent repair records."""
    query: Dict[str, Any] = {}
    if repair_id:
        query["$or"] = [{"repair_id": repair_id}, {"id": repair_id}, {"_id": repair_id}]
    elif run_id:
        query["original_run_id"] = run_id

    candidates = list(col.find(query))
    return [d for d in candidates if is_inconsistent_repair_doc(d)]


def reconcile_doc(
    col: Any,
    doc: Dict[str, Any],
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Applies the narrowly-scoped reconciliation update to a single repair record.
    Preserves all submission, test, and note details.
    """
    doc_id = doc.get("_id") or doc.get("repair_id") or doc.get("id")
    now_iso = datetime.now(timezone.utc).isoformat()

    updates: Dict[str, Any] = {
        "status": "BLOCKED",
        "corrected_run_id": None,
        "updated_at": datetime.now(timezone.utc),
    }

    comp = doc.get("comparison")
    if comp:
        comp_updates = dict(comp)
        comp_updates["corrected_run_id"] = None
        comp_updates["corrected_status"] = "BLOCKED"
        comp_updates["remaining_defects_count"] = 0
        if not comp_updates.get("notes"):
            comp_updates["notes"] = "Re-verification blocked: original trusted test suite is unavailable."
        updates["comparison"] = comp_updates

    if dry_run:
        print(f"  [DRY RUN] Would update document _id='{doc_id}':")
        print(f"    - status: {doc.get('status')} -> BLOCKED")
        print(f"    - corrected_run_id: {doc.get('corrected_run_id')} -> None")
        print(f"    - comparison.corrected_status: -> BLOCKED")
        print(f"    - comparison.remaining_defects_count: -> 0")
        return {"id": doc_id, "status": "DRY_RUN"}

    res = col.update_one(
        {"_id": doc["_id"]},
        {"$set": updates},
    )
    print(f"  [APPLIED] Successfully updated document _id='{doc_id}' (matched={res.matched_count}, modified={res.modified_count})")
    return {"id": doc_id, "status": "RECONCILED", "modified_count": res.modified_count}


def main():
    parser = argparse.ArgumentParser(
        description="INTELISE Historical Repair Record Reconciliation Utility"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply reconciliation changes to the database. If omitted, operates in dry-run mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Perform inspection and report actions without making database modifications (default).",
    )
    parser.add_argument(
        "--repair-id",
        type=str,
        default=None,
        help="Target a specific repair attempt identifier (e.g. rep-5f900fb0183d).",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Target all repair attempts associated with a specific verification run ID.",
    )
    args = parser.parse_args()

    # Determine execution mode: --apply overrides default dry-run
    is_dry_run = not args.apply

    print("=" * 70)
    print("INTELISE — Historical Repair Record Reconciliation Utility")
    print(f"Execution Mode: {'DRY RUN (No changes will be saved)' if is_dry_run else 'APPLY (Changes will be written to database)'}")
    print("=" * 70)

    if not settings.MONGODB_URI:
        print("ERROR: MONGODB_URI is not configured in settings or .env file.")
        sys.exit(1)

    # Obfuscate URI credentials for logging
    safe_uri = settings.MONGODB_URI.split("@")[-1] if "@" in settings.MONGODB_URI else "mongodb-connection"
    print(f"Connecting to MongoDB Atlas target: ...@{safe_uri}")
    print(f"Database: {settings.MONGODB_DB_NAME}")

    try:
        timeout_ms = max(settings.MONGODB_CONNECT_TIMEOUT_MS, 30000)
        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=timeout_ms)
        client.admin.command("ping")
        db = client[settings.MONGODB_DB_NAME]
        repair_col = db["repair_attempts"]
    except Exception as exc:
        print(f"ERROR: Could not connect to MongoDB Atlas: {exc}")
        sys.exit(1)

    print(f"Total documents in 'repair_attempts': {repair_col.count_documents({})}")
    print("Scanning for inconsistent repair records...")

    inconsistent_records = find_inconsistent_records(
        repair_col,
        repair_id=args.repair_id,
        run_id=args.run_id,
    )

    print(f"Found {len(inconsistent_records)} inconsistent record(s) matching criteria:")
    for doc in inconsistent_records:
        doc_id = doc.get("repair_id") or doc.get("id") or doc.get("_id")
        comp = doc.get("comparison") or {}
        print(f"\n- Repair ID: {doc_id}")
        print(f"  Original Run ID: {doc.get('original_run_id')}")
        print(f"  Current Status: {doc.get('status')}")
        print(f"  Corrected Run ID: {doc.get('corrected_run_id')}")
        print(f"  Comparison Verdict: {comp.get('verdict')}")
        print(f"  Notes: {doc.get('notes')}")

    if not inconsistent_records:
        print("\n✓ No inconsistent repair records found. All repair records have consistent lifecycles.")
        return

    print("\n" + ("-" * 70))
    if is_dry_run:
        print("DRY-RUN SUMMARY: The following operations would be executed if --apply is passed:")
    else:
        print("APPLYING RECONCILIATION UPDATES:")

    for doc in inconsistent_records:
        reconcile_doc(repair_col, doc, dry_run=is_dry_run)

    print("-" * 70)
    if is_dry_run:
        print("\nDry-run completed successfully. To commit these changes, re-run with:")
        target_flag = f" --repair-id {args.repair_id}" if args.repair_id else ""
        print(f"  python scripts/reconcile_repair_records.py{target_flag} --apply")
    else:
        print("\n✓ Reconciliation applied successfully. All targeted records now have status 'BLOCKED'.")


if __name__ == "__main__":
    main()
