"""Plot the experimental annotation revision honestly against unchanged labels."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True, type=Path)
    parser.add_argument("--original-model", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Fresh chart directory; default is REVISION/charts")
    args = parser.parse_args()
    report = json.loads((args.revision / "report.json").read_text())
    original = json.loads((args.original_model / "test_metrics.json").read_text())
    revised = report["test"]
    output = args.output or args.revision / "charts"
    output.mkdir(exist_ok=False)
    names = []
    with PdfPages(output / "experimental-label-revision.pdf") as pdf:
        def save(fig, name, note):
            fig.text(.5, .015, note, ha="center", fontsize=9)
            fig.tight_layout(rect=(0, .06, 1, 1))
            fig.savefig(output / (name + ".png"), dpi=200)
            fig.savefig(output / (name + ".svg"))
            pdf.savefig(fig); plt.close(fig); names.append(name)

        fig, ax = plt.subplots(figsize=(10, 6))
        for index, (metrics, label, color) in enumerate(((original, "Original", "#a4b5bf"), (revised, "AI-assisted revision (experimental)", "#267f9e"))):
            matrix = np.array(metrics["confusion_matrix"]["values"])
            scores = [np.trace(matrix)/matrix.sum(), metrics["macro_f1"], metrics["per_class"]["FR"]["f1-score"], metrics["per_class"]["NFR"]["f1-score"]]
            bars = ax.bar(np.arange(4)+(index-.5)*.36, scores, width=.36, label=label, color=color)
            ax.bar_label(bars, labels=[f"{value:.2%}" for value in scores], padding=4, fontsize=9)
        ax.set(xticks=range(4), xticklabels=["Accuracy", "Macro-F1", "FR F1", "NFR F1"], ylim=(0, 1.14), title="Reused DCAI test · original labels unchanged")
        ax.legend(loc="upper left")
        save(fig, "unchanged-test-label-comparison", "AI-reviewed training policy differs from original test labels · not fresh independent evaluation or PURE results")

        fig, ax = plt.subplots(figsize=(7, 6))
        matrix = np.array(revised["confusion_matrix"]["values"])
        ax.imshow(matrix, cmap="Blues")
        for row in range(2):
            for col in range(2):
                ax.text(col,row,str(matrix[row,col]),ha="center",va="center",fontsize=24,
                        color="white" if matrix[row,col] > matrix.max()/2 else "black")
        ax.set(xticks=range(2),yticks=range(2),xticklabels=["FR","NFR"],yticklabels=["FR","NFR"],
               xlabel="Predicted",ylabel="Original source label",title="Experimental revision · reused DCAI test")
        save(fig, "experimental-confusion-matrix", "Rows = unchanged original labels · columns = predictions · label-policy disagreement is not adjudicated")

        fig, ax = plt.subplots(figsize=(9, 5))
        values = [report["changed_labels"], report["quarantined"], report["retained_original_labels"]]
        bars = ax.bar(["NFR → FR", "Quarantined", "Retained NFR"], values, color=["#267f9e", "#d08435", "#7664b0"])
        ax.bar_label(bars,padding=5); ax.set(ylabel="Training examples",title=f"Explicit AI-assisted review · {report['reviews']} NFR training examples")
        save(fig, "training-label-review", "Not independently human-verified · original text/labels retained in review ledger · no holdout rows changed")
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><h1>Experimental AI-assisted label revision</h1><p>Login now FR; overall quality remains unverified. Application model unchanged.</p>' + ''.join(f'<h2>{name}</h2><img style="max-width:100%" src="{name}.png" alt="{name}">' for name in names))
    print(f"Saved {len(names)} PNG/SVG charts and PDF: {output}")


if __name__ == "__main__":
    main()
