"""Interactive terminal tester. Run a file so stdin remains available for input."""
import argparse
import json
from pathlib import Path

from intelise_c1.baseline.model import load_artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True, help="Trusted locally trained artifact directory")
    parser.add_argument("--text", help="One requirement; omit for interactive testing")
    args = parser.parse_args()
    model, metadata = load_artifact(args.model_dir)
    print("Model:", metadata.model_identifier, "\nVersion:", metadata.model_version)
    manifest = json.loads((args.model_dir / "split_manifest.json").read_text())
    if manifest.get("annotation_status"):
        print("Annotation status:", manifest["annotation_status"])

    def predict(text):
        if not text.strip() or len(text) > 10000:
            print("Enter nonblank text up to 10,000 characters.")
            return
        label = str(model.predict([text])[0])
        print(label + ": " + ("Functional requirement" if label == "FR" else "Non-functional requirement"))

    if args.text is not None:
        predict(args.text)
        return
    print("Enter one requirement at a time; type quit to exit.")
    while True:
        try:
            text = input("\nRequirement: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() == "quit":
            break
        predict(text)


if __name__ == "__main__":
    main()
