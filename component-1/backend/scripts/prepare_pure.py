"""Run from backend with .venv/bin/python scripts/prepare_pure.py --help."""
import argparse
import json
from pathlib import Path

from intelise_c1.baseline.pure import prepare_pure

parser = argparse.ArgumentParser(description="Prepare unlabelled PURE review data; never trains/replaces a model")
for name in ("documents", "xml", "raw-output", "output", "dcai-csv", "dcai-prepared", "model-dir"):
    parser.add_argument("--" + name, required=True, type=Path)
if __name__ == "__main__":
    summary = prepare_pure(**vars(parser.parse_args()))
    print(json.dumps({key: summary[key] for key in ("unique_candidates", "new_unique_candidates", "dcai_overlap_unique", "reviewed_labels", "new_model_trained")}, indent=2))
