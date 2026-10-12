"""Offline commands. No model training is performed by the API process."""
import argparse
from pathlib import Path

from pydantic import ValidationError

from intelise_c1.baseline.data import DatasetError, DEFAULT_SEED, prepare


def main(argv=None):
    parser = argparse.ArgumentParser(description="IntelliSE TF-IDF/logistic FR/NFR baseline (not BERT)")
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--input", required=True, type=Path)
    preparation.add_argument("--provenance", required=True, type=Path)
    preparation.add_argument("--output", required=True, type=Path)
    preparation.add_argument("--seed", type=int, default=DEFAULT_SEED)
    preparation.add_argument("--validation-fraction", type=float, default=.2)
    preparation.add_argument("--test-fraction", type=float, default=.2)
    training = commands.add_parser("train")
    training.add_argument("--prepared", required=True, type=Path)
    training.add_argument("--output", required=True, type=Path)
    training.add_argument("--c", type=float, default=1.0)
    training.add_argument("--seed", type=int, default=DEFAULT_SEED)
    for name in ("freeze", "evaluate"):
        command = commands.add_parser(name)
        command.add_argument("--model-dir", required=True, type=Path)
        if name == "evaluate":
            command.add_argument("--prepared", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            manifest = prepare(args.input, args.provenance, args.output, args.seed, args.validation_fraction, args.test_fraction)
            print(f"Prepared {manifest['purpose']} data; dataset_version={manifest['dataset_version']}; split_id={manifest['split_id']}")
        else:
            from intelise_c1.baseline.model import BaselineConfig, evaluate, freeze, train
            if args.command == "train":
                metadata = train(args.prepared, args.output, BaselineConfig(c=args.c, seed=args.seed))
                print(f"Saved TF-IDF/logistic pipeline {metadata.model_version}; validation metrics only. Final test remains unevaluated.")
            elif args.command == "freeze":
                freeze(args.model_dir)
                print("Model settings frozen. Do not use final test results to select settings.")
            else:
                evaluate(args.prepared, args.model_dir)
                print("Measured held-out test results saved in test_metrics.json.")
    except (DatasetError, OSError, ValidationError, ImportError) as error:
        if isinstance(error, DatasetError):
            message = str(error)
        elif isinstance(error, ImportError):
            message = "Install requirements-baseline.lock to enable training/model persistence."
        else:
            message = "Invalid settings or unavailable/existing output files. Outputs are never overwritten."
        parser.exit(2, message + "\n")


if __name__ == "__main__":
    main()
