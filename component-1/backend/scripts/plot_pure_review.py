"""Plot saved reports only. Requires Matplotlib in an isolated plotting environment."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np


def render(prepared, models):
    summary = json.loads((prepared / "summary.json").read_text())
    test_path = models / "lr-c10" / "test_metrics.json"
    test = json.loads(test_path.read_text())
    output = prepared / "charts"
    output.mkdir(exist_ok=False)
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    matrix = np.array(test["confusion_matrix"]["values"])
    accuracy = float(np.trace(matrix) / matrix.sum())
    labels = test["confusion_matrix"]["label_order"]
    charts = []
    with PdfPages(output / "component-01-dataset-and-baseline-report.pdf") as pdf:
        fig = plt.figure(figsize=(11.7, 8.3))
        fig.text(.08, .90, "Component 01: PURE preparation and existing baseline", fontsize=20, weight="bold")
        lines = [
            f"Prepared: {summary['created_at']}", "",
            f"PURE: {summary['xml_documents']} XML documents; {summary['source_requirement_blocks']:,} marked requirement blocks.",
            f"Unique texts: {summary['unique_candidates']:,}; redundant duplicate occurrences: {summary['redundant_duplicate_occurrences']}.",
            f"Exact DCAI overlaps: {summary['dcai_overlap_unique']}; remaining unlabelled candidates: {summary['new_unique_candidates']}.",
            f"Overlap with existing splits: {summary['overlap_split_counts']}",
            "Human-reviewed FR/NFR labels: 0. No new model trained. PURE accuracy / F1: unavailable.",
            "The review sheet contains source XML text, not independently verified requirements.", "",
            "EXISTING DCAI TF-IDF + logistic regression test results (not PURE)",
            f"Held-out examples: {int(matrix.sum())}; accuracy: {accuracy:.2%}; macro-F1: {test['macro_f1']:.2%}.",
            "Selection: validation macro-F1; existing frozen C=10 model. No test-based tuning here.",
            "Evaluation: within-corpus normalized-text holdout, NOT unseen-project evaluation.",
            "Exact duplicates were separated; related projects/paraphrases may still overlap.", "",
            "NEXT: label new_only_review.csv as FR/NFR; record reviewer/date and source grouping.",
            "Resolve mixed/uncertain examples and related documents before constructing evaluation splits.",
            "Model suggestions are separate, unreviewed predictions and must not become reference labels.",
            "Original files and selected model preserved. No API/model configuration changed.",
        ]
        fig.text(.08, .82, "\n".join(lines), va="top", linespacing=1.65, fontsize=11)
        pdf.savefig(fig); plt.close(fig)

        def save(fig, name, description):
            fig.text(.5, .015, description, ha="center", fontsize=9)
            fig.tight_layout(rect=(0, .05, 1, 1))
            fig.savefig(output / f"{name}.png", dpi=220)
            fig.savefig(output / f"{name}.svg")
            pdf.savefig(fig)
            charts.append({"name": name, "description": description})
            plt.close(fig)

        fig, ax = plt.subplots(figsize=(9, 5))
        scores = [accuracy, test["macro_f1"]]
        bars = ax.bar(["Accuracy", "Macro-F1"], scores, color=["#267f9e", "#7664b0"], width=.5)
        ax.bar_label(bars, labels=[f"{x:.2%}" for x in scores], padding=5)
        ax.set(ylim=(0, 1.05), ylabel="Score", title="Existing DCAI held-out test · TF-IDF / logistic regression")
        save(fig, "dcai-test-accuracy-macro-f1", "516 examples · within-corpus holdout · these are NOT PURE evaluation scores")

        fig, ax = plt.subplots(figsize=(9, 5))
        for index, (key, name, color) in enumerate((("precision", "Precision", "#267f9e"), ("recall", "Recall", "#d08435"), ("f1-score", "F1", "#7664b0"))):
            values = [test["per_class"][label][key] for label in labels]
            bars = ax.bar(np.arange(len(labels)) + (index - 1) * .24, values, .24, label=name, color=color)
            ax.bar_label(bars, labels=[f"{x:.1%}" for x in values], padding=3, fontsize=9)
        ax.set(xticks=range(len(labels)), xticklabels=labels, ylim=(0, 1.15), ylabel="Score", title="Existing DCAI test · precision, recall and F1 by class")
        ax.legend(loc="upper left", ncols=3)
        save(fig, "dcai-test-per-class", "FR support 174 · NFR support 342 · not individual-prediction confidence")

        fig, ax = plt.subplots(figsize=(7, 6))
        ax.imshow(matrix, cmap="Blues")
        for row in range(2):
            for col in range(2):
                ax.text(col, row, str(matrix[row, col]), ha="center", va="center", fontsize=25,
                        color="white" if matrix[row, col] > matrix.max() / 2 else "black")
        ax.set(xticks=range(2), yticks=range(2), xticklabels=labels, yticklabels=labels,
               xlabel="Predicted", ylabel="Actual", title="Existing DCAI test · confusion matrix")
        save(fig, "dcai-test-confusion-matrix", "Rows = actual · columns = predicted · 44 errors across 516 held-out examples")

        fig, ax = plt.subplots(figsize=(9, 5))
        scores = [json.loads((models / name / "validation_metrics.json").read_text())["macro_f1"]
                  for name in ("lr-c01", "lr-c1", "lr-c10")]
        bars = ax.bar(["C = 0.1", "C = 1", "C = 10 (selected)"], scores, color=["#a4b5bf", "#a4b5bf", "#267f9e"])
        ax.bar_label(bars, labels=[f"{x:.2%}" for x in scores], padding=5)
        ax.set(ylim=(0, 1), ylabel="Validation macro-F1", title="Existing DCAI model selection · validation only")
        save(fig, "dcai-validation-model-selection", "Read saved validation reports; no new fitting or test-based selection")

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        bars = axes[0].bar(["New unlabelled", "Exact DCAI overlap", "Redundant copies"],
                          [summary['new_unique_candidates'], summary['dcai_overlap_unique'], summary['redundant_duplicate_occurrences']], color=["#267f9e", "#d08435", "#a4b5bf"])
        axes[0].bar_label(bars, padding=3); axes[0].set(title="PURE preparation · marked blocks", ylabel="Count")
        counts = summary["suggested_class_counts_not_ground_truth"]
        bars = axes[1].bar(["FR", "NFR"], [counts.get(x, 0) for x in ("FR", "NFR")], color=["#267f9e", "#7664b0"])
        axes[1].bar_label(bars, padding=3); axes[1].set(title="Existing-model suggestions · NOT true labels", ylabel="Unique candidate count")
        save(fig, "pure-preparation-and-suggestions", "No reviewed FR/NFR labels · no PURE accuracy or F1 measurable · req tags still need relevance review")

        fig, ax = plt.subplots(figsize=(11, 6))
        docs = [item for item in summary["documents"] if item["requirement_blocks"]]
        ax.barh([Path(item["document"]).name for item in docs], [item["requirement_blocks"] for item in docs], color="#267f9e")
        ax.invert_yaxis(); ax.set(xlabel="Explicit <req> blocks", title="PURE XML coverage · six files with marked requirements")
        save(fig, "pure-document-coverage", "12 further XML files have zero <req> blocks; not equivalent to the full 34,268-sentence corpus")
    body = "\n".join(f'<h2>{item["name"]}</h2><p>{item["description"]}</p><img style="max-width:100%" src="{item["name"]}.png" alt="{item["name"]}">' for item in charts)
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Component 01 research charts</title><h1>PURE preparation and existing DCAI baseline</h1><p>PURE is unlabelled. All accuracy/F1 charts describe the earlier DCAI evaluation.</p><a href="component-01-dataset-and-baseline-report.pdf">PDF report</a>' + body)
    (output / "chart_manifest.json").write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(),
        "matplotlib": version("matplotlib"), "numpy": version("numpy"), "metric_source": str(test_path),
        "accuracy_derived_from_saved_confusion_matrix": accuracy, "charts": charts}, indent=2) + "\n")
    print(f"Saved {len(charts)} charts (PNG/SVG), HTML gallery and PDF to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared", required=True, type=Path)
    parser.add_argument("--models", required=True, type=Path)
    args = parser.parse_args()
    render(args.prepared, args.models)
