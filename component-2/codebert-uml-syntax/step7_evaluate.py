"""STEP 7 - Evaluate on the held-out TEST split and compare with baselines.

Reports (answers Research Question 1 and Table 5 of the proposal):
  * per-class precision / recall / F1 + confusion matrix for CodeBERT (13 labels)
  * binary error detection (valid vs invalid) for:
      - PlantUML only
      - rule linter only (braces / quotes / parentheses / markers)
      - UML rules only (duplicates, generalization cycles, use-case relationships)
      - deterministic gate = PlantUML OR linter OR UML rules   (no machine learning)
      - CodeBERT only
      - full gate = deterministic gate OR CodeBERT             (what the pipeline uses)
    The difference between the last row and the deterministic gate is the real
    added value of CodeBERT.
  * "parser-silent" errors (PlantUML accepted a broken diagram) and errors that
    NO deterministic check caught, and how many of them CodeBERT caught
  * CodeBERT precision/recall at confidence thresholds on diagrams that passed
    the deterministic gate (helps choose the pipeline threshold, e.g. 0.9)
  * macro-F1 per diagram type and per domain, latency per diagram
  * several --model paths (e.g. 3 training seeds) -> mean +- std summary

Usage:
  python step7_evaluate.py
  python step7_evaluate.py --model models/codebert-uml-syntax-s42 models/codebert-uml-syntax-s7 models/codebert-uml-syntax-s123
  # strict ablation: evaluate the strict model on the NORMAL test set (same diagrams)
  python step7_evaluate.py --model models/codebert-strict --test data/splits/test.csv --out results/strict
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_recall_fscore_support

from common import LABEL2ID, LABELS, encode_head_tail, lint
from uml_rules import check_rules


def binary_scores(y_true_err, y_pred_err):
    p, r, f, _ = precision_recall_fscore_support(y_true_err, y_pred_err, average="binary", zero_division=0)
    return {"precision": round(float(p), 4), "recall": round(float(r), 4), "f1": round(float(f), 4)}


def load_model(path, device):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSequenceClassification.from_pretrained(path).to(device).eval()
    model_labels = [model.config.id2label[i] for i in range(model.config.num_labels)]
    if model_labels != LABELS:
        raise SystemExit(f"{path} was trained with a different label list ({len(model_labels)} labels) than "
                         f"common.LABELS ({len(LABELS)} labels). Retrain it, or delete the old model.")
    return tok, model


def predict(model, tok, texts, max_len, batch, device):
    import torch
    probs, t0 = [], time.time()
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = [encode_head_tail(tok, t, max_len) for t in texts[i:i + batch]]
            padded = tok.pad(enc, return_tensors="pt").to(device)
            probs.append(torch.softmax(model(**padded).logits, -1).cpu().numpy())
    return np.concatenate(probs), (time.time() - t0) / max(1, len(texts))


def deterministic_columns(df):
    """PlantUML / linter / UML-rule verdicts (no model needed, computed once)."""
    df = df.copy()
    df["true_err"] = (df["label"] != "VALID").astype(int)
    df["parser_err"] = (df["parser_status"] == "ERROR").astype(int)
    df["lint_err"] = df["text"].map(lambda t: int(bool(lint(t))))
    df["rules_err"] = [int(bool(check_rules(t, dt))) for t, dt in zip(df["text"], df["diagram_type"])]
    df["det_err"] = ((df["parser_err"] + df["lint_err"] + df["rules_err"]) > 0).astype(int)
    return df


def analyse(df, probs, out, sec_per, device, verbose=True):
    out.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["pred"] = [LABELS[i] for i in probs.argmax(1)]
    df["confidence"] = probs.max(1)
    y, p = df["label"].map(LABEL2ID).values, df["pred"].map(LABEL2ID).values
    say = print if verbose else (lambda *x, **k: None)

    present = sorted(set(y) | set(p))
    names = [LABELS[i] for i in present]
    report = classification_report(y, p, labels=present, target_names=names, digits=4, zero_division=0, output_dict=True)
    say(classification_report(y, p, labels=present, target_names=names, digits=4, zero_division=0))
    pd.DataFrame(confusion_matrix(y, p, labels=present), index=names, columns=names).to_csv(out / "confusion_matrix.csv")

    # ---------- binary error detection vs baselines
    bert_err = (df["pred"] != "VALID").astype(int)
    full = ((df["det_err"] + bert_err) > 0).astype(int)
    t = df["true_err"]
    detection = {"PlantUML only": binary_scores(t, df["parser_err"]),
                 "Rule linter only": binary_scores(t, df["lint_err"]),
                 "UML rules only": binary_scores(t, df["rules_err"]),
                 "Deterministic gate (PlantUML OR linter OR rules)": binary_scores(t, df["det_err"]),
                 "CodeBERT only": binary_scores(t, bert_err),
                 "Full gate (deterministic OR CodeBERT)": binary_scores(t, full)}
    say("\nBinary error detection on test set:")
    for k, v in detection.items():
        say(f"  {k:50s} P={v['precision']:.3f} R={v['recall']:.3f} F1={v['f1']:.3f}")

    silent = df[(df["true_err"] == 1) & (df["parser_err"] == 0)]
    missed = df[(df["true_err"] == 1) & (df["det_err"] == 0)]          # only a learned model can catch these
    silent_caught = int((silent["pred"] != "VALID").sum())
    missed_caught = int((missed["pred"] != "VALID").sum())
    say(f"\nParser-silent errors (PlantUML accepted): {len(silent)}; caught by CodeBERT: {silent_caught}")
    say(f"Errors missed by ALL deterministic checks: {len(missed)}; caught by CodeBERT: {missed_caught}")
    if len(missed):
        say("  missed errors by label:", missed["label"].value_counts().to_dict())

    # ---------- confidence thresholds on diagrams that passed the deterministic gate
    passed = df[df["det_err"] == 0]
    thresholds = {}
    for th in (0.5, 0.7, 0.9, 0.95):
        flag = ((passed["pred"] != "VALID") & (passed["confidence"] >= th)).astype(int)
        thresholds[str(th)] = binary_scores(passed["true_err"], flag) | {"flagged": int(flag.sum())}
    say(f"\nCodeBERT on the {len(passed)} diagrams that passed the deterministic gate:")
    for th, v in thresholds.items():
        say(f"  confidence >= {th:4s}: flagged {v['flagged']:5d}  P={v['precision']:.3f} R={v['recall']:.3f} F1={v['f1']:.3f}")

    by_type = {k: round(float(f1_score(g["label"], g["pred"], average="macro", zero_division=0)), 4)
               for k, g in df.groupby("diagram_type")}
    by_domain = {d: round(float(f1_score(g["label"], g["pred"], average="macro", zero_division=0)), 4)
                 for d, g in df.groupby("domain") if len(g) >= 20}
    say("\nmacro-F1 by diagram type:", by_type)

    summary = {
        "test_rows": len(df), "accuracy": round(report["accuracy"], 4),
        "macro_f1": round(report["macro avg"]["f1-score"], 4),
        "weighted_f1": round(report["weighted avg"]["f1-score"], 4),
        "per_class": {k: {m: round(v[m], 4) for m in ("precision", "recall", "f1-score", "support")}
                      for k, v in report.items() if k in LABELS},
        "error_detection": detection,
        "parser_silent_errors": {"count": len(silent), "caught_by_codebert": silent_caught},
        "missed_by_deterministic": {"count": len(missed), "caught_by_codebert": missed_caught},
        "codebert_after_deterministic_gate": thresholds,
        "macro_f1_by_diagram_type": by_type, "macro_f1_by_domain": by_domain,
        "latency_ms_per_diagram": round(sec_per * 1000, 1), "device": device,
    }
    json.dump(summary, open(out / "test_metrics.json", "w"), indent=2)
    df[df["label"] != df["pred"]].to_csv(out / "misclassified.csv", index=False)  # for error analysis
    say(f"\nlatency: {summary['latency_ms_per_diagram']} ms/diagram on {device}")
    say(f"saved -> {out}/test_metrics.json, confusion_matrix.csv, misclassified.csv")
    return summary


def seed_summary(summaries, out):
    keys = {"accuracy": lambda s: s["accuracy"], "macro_f1": lambda s: s["macro_f1"],
            "weighted_f1": lambda s: s["weighted_f1"],
            "full_gate_f1": lambda s: s["error_detection"]["Full gate (deterministic OR CodeBERT)"]["f1"],
            "codebert_only_f1": lambda s: s["error_detection"]["CodeBERT only"]["f1"]}
    res = {}
    print(f"\n===== summary over {len(summaries)} models (mean +- std) =====")
    for k, f in keys.items():
        v = np.array([f(s) for s in summaries.values()])
        res[k] = {"mean": round(float(v.mean()), 4), "std": round(float(v.std(ddof=1)), 4), "values": v.round(4).tolist()}
        print(f"  {k:18s} {v.mean():.4f} +- {v.std(ddof=1):.4f}")
    json.dump(res, open(out / "seed_summary.json", "w"), indent=2)
    print(f"saved -> {out}/seed_summary.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", nargs="+", default=["models/codebert-uml-syntax"])
    ap.add_argument("--test", default="data/splits/test.csv")
    ap.add_argument("--out", default="results")
    ap.add_argument("--max_len", type=int, default=512)
    ap.add_argument("--batch", type=int, default=32)
    a = ap.parse_args()

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    df = deterministic_columns(pd.read_csv(a.test, keep_default_na=False))
    out = Path(a.out)
    summaries = {}
    for m in a.model:
        print(f"\n################ {m} ################")
        tok, model = load_model(m, device)
        probs, sec_per = predict(model, tok, df["text"].tolist(), a.max_len, a.batch, device)
        sub = out / Path(m).name if len(a.model) > 1 else out
        summaries[m] = analyse(df, probs, sub, sec_per, device)
    if len(summaries) > 1:
        seed_summary(summaries, out)


if __name__ == "__main__":
    main()