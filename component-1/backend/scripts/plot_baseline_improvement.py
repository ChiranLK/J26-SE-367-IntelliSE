"""Visualize a completed offline improvement run; uses isolated Matplotlib env."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np


def render(run, baseline):
    report = json.loads((run / "report.json").read_text())
    selection = json.loads((run / "selection.json").read_text())
    audit = json.loads((run / "audit.json").read_text())
    old = json.loads((baseline / "test_metrics.json").read_text())
    new = report["test_metrics"]
    output = run / "charts"
    output.mkdir(exist_ok=False)
    names = []
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    with PdfPages(output / "baseline-improvement-report.pdf") as pdf:
        def save(fig, name, note):
            fig.text(.5, .015, note, ha="center", fontsize=9)
            fig.tight_layout(rect=(0, .05, 1, 1))
            fig.savefig(output / f"{name}.png", dpi=220)
            fig.savefig(output / f"{name}.svg")
            pdf.savefig(fig); plt.close(fig); names.append(name)

        fig, ax = plt.subplots(figsize=(11, 6))
        trials = selection["trials"]
        labels = ["Original\nC=10 / 20k" if item["path"] == "baseline" else f"C={item['c']}\n{item['max_features']//1000}k features" for item in trials]
        bars = ax.bar(labels, [item["validation_macro_f1"] for item in trials], color=["#267f9e" if item["path"] == selection["selected"]["path"] else "#a4b5bf" for item in trials])
        ax.bar_label(bars, labels=[f"{item['validation_macro_f1']:.2%}" for item in trials], padding=4)
        ax.set(ylim=(0, 1.05), ylabel="Validation macro-F1", title="Model selection · existing DCAI validation split only")
        save(fig, "validation-comparison", "Vocabulary/IDF fitted on training only · selected bar in blue · no PURE labels used")

        fig, ax = plt.subplots(figsize=(9, 6))
        def accuracy(result):
            matrix = np.array(result["confusion_matrix"]["values"])
            return np.trace(matrix) / matrix.sum()
        for index, (result, label, color) in enumerate(((old, "Original", "#a4b5bf"), (new, "Selected candidate", "#267f9e"))):
            values = [accuracy(result), result["macro_f1"], result["per_class"]["FR"]["f1-score"], result["per_class"]["NFR"]["f1-score"]]
            bars = ax.bar(np.arange(4) + (index-.5)*.36, values, .36, label=label, color=color)
            ax.bar_label(bars, labels=[f"{value:.1%}" for value in values], fontsize=9, padding=4)
        ax.set(xticks=range(4), xticklabels=["Accuracy", "Macro-F1", "FR F1", "NFR F1"], ylim=(0, 1.12), title="Supplementary comparison · reused DCAI test set")
        ax.legend(loc="upper left", ncols=2)
        save(fig, "supplementary-test-comparison", "516 existing test examples · NOT fresh independent evaluation or PURE performance")

        fig, ax = plt.subplots(figsize=(7, 6))
        matrix = np.array(new["confusion_matrix"]["values"])
        ax.imshow(matrix, cmap="Blues")
        for row in range(2):
            for col in range(2):
                ax.text(col, row, str(matrix[row, col]), ha="center", va="center", fontsize=25,
                        color="white" if matrix[row, col] > matrix.max()/2 else "black")
        ax.set(xticks=range(2), yticks=range(2), xticklabels=["FR", "NFR"], yticklabels=["FR", "NFR"],
               xlabel="Predicted", ylabel="Actual", title="Selected candidate · reused DCAI test")
        save(fig, "candidate-confusion-matrix", "Rows = actual · columns = predicted · source labels independently unreviewed")

        fig, ax = plt.subplots(figsize=(9, 5))
        counts = audit["authentication_training_class_counts"]
        bars = ax.bar(["FR", "NFR"], [counts.get(label, 0) for label in ["FR", "NFR"]], color=["#267f9e", "#7664b0"])
        ax.bar_label(bars, padding=5)
        ax.set(ylabel="Source-labelled training examples", title="Authentication keyword subset · existing training labels")
        save(fig, "authentication-label-audit", "Keyword subset only · counts do not establish correct labels · source-policy review needed")

        fig, ax = plt.subplots(figsize=(10, 6))
        features = audit["login_explanation"]["features"][:12]
        values = [item["nfr_logit_contribution"] for item in features]
        ax.barh([item["feature"] for item in features], values, color=["#d08435" if value > 0 else "#267f9e" for value in values])
        ax.axvline(0, color="black", linewidth=.6); ax.invert_yaxis()
        ax.set(xlabel="Contribution: negative favors FR; positive favors NFR", title="Original model · features behind the login error")
        save(fig, "login-feature-contributions", "Local linear-model explanation · learned associations, not semantic correctness or confidence")
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><h1>Baseline improvement experiment</h1><p>Original labels; reused DCAI test, no PURE evaluation. Application model unchanged.</p><a href="baseline-improvement-report.pdf">PDF report</a>' + ''.join(f'<h2>{name}</h2><img style="max-width:100%" src="{name}.png" alt="{name}">' for name in names))
    print(f"Saved {len(names)} PNG/SVG charts and PDF: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    render(**vars(parser.parse_args()))
