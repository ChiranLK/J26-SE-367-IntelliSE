"""Run four semantic retrieval checks with the configured real embedding model."""

from __future__ import annotations

import os
from pathlib import Path

from intelise_c3.rag import create_store

COMPONENT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("RAG_BACKEND", "chroma")


def main() -> int:
    store = create_store(os.environ["RAG_BACKEND"], COMPONENT_ROOT / "rules")
    queries = (
        ("make the endpoint read data straight from the database table", "spring", "controller"),
        ("wire collaborators so tests can replace them with fakes", "node", "service"),
        ("user supplied id goes into the SQL statement", "node", "api"),
        ("component downloads data from the server itself", "react", "ui"),
    )
    for task, stack, layer in queries:
        print("=" * 70)
        print(f"TASK: {task}  [{stack}/{layer}]")
        for rule in store.get_rules(task, stack, layer, k=3):
            print(f"  - {rule.id}: {rule.rule}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
