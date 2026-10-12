"""STEP 6 - Fine-tune CodeBERT (microsoft/codebert-base) as a PlantUML syntax-error classifier.

Task      : single-label sequence classification, 13 classes (VALID + 9 syntax error
            types + 3 UML rule violations, see common.LABELS)
Input     : data/splits/train.csv, data/splits/val.csv  (column 'text' and 'label')
Output    : models/codebert-uml-syntax/  (weights, tokenizer, label map, run_config.json)

Recommended hardware: a free Colab / Kaggle T4 GPU (~10-20 min per epoch for ~25k samples).
CPU-only works for a smoke test with --max_train_samples 300 --epochs 1.

Usage:
  python step6_train_codebert.py
  # 3 training seeds (same split!) -> report mean +- std in the thesis
  python step6_train_codebert.py --seed 42  --out models/codebert-uml-syntax-s42
  python step6_train_codebert.py --seed 7   --out models/codebert-uml-syntax-s7
  python step6_train_codebert.py --seed 123 --out models/codebert-uml-syntax-s123
  # strict ablation dataset
  python step6_train_codebert.py --train data/splits_strict/train.csv --val data/splits_strict/val.csv --out models/codebert-strict
  # quick smoke test
  python step6_train_codebert.py --max_train_samples 300 --epochs 1 --batch 8
"""
import argparse
import json
import math
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from datasets import Dataset
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support
from transformers import (AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding,
                          EarlyStoppingCallback, Trainer, TrainingArguments, set_seed)
import transformers

from common import ID2LABEL, LABEL2ID, LABELS, encode_head_tail

VALID_ID = LABEL2ID["VALID"]


class WeightedTrainer(Trainer):
    """Cross-entropy with class weights, so rarer error types (e.g. multiplicity)
    are not ignored by the model."""

    def __init__(self, class_weights=None, **kw):
        super().__init__(**kw)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        w = self.class_weights.to(outputs.logits.device) if self.class_weights is not None else None
        loss = torch.nn.functional.cross_entropy(outputs.logits, labels, weight=w)
        return (loss, outputs) if return_outputs else loss


def compute_metrics(eval_pred):
    logits, y = eval_pred
    p = logits.argmax(-1)
    # binary view: does the model at least know it's broken?
    yb, pb = (y != VALID_ID).astype(int), (p != VALID_ID).astype(int)
    bp, br, bf, _ = precision_recall_fscore_support(yb, pb, average="binary", zero_division=0)
    return {"accuracy": accuracy_score(y, p),
            "macro_f1": f1_score(y, p, average="macro", zero_division=0),
            "weighted_f1": f1_score(y, p, average="weighted", zero_division=0),
            "error_detect_precision": bp, "error_detect_recall": br, "error_detect_f1": bf}


def load(path, tok, max_len, limit=None, seed=42):
    df = pd.read_csv(path, keep_default_na=False)
    unknown = sorted(set(df["label"]) - set(LABEL2ID))
    if unknown:
        raise SystemExit(f"{path} has labels that are not in common.LABELS: {unknown}")
    if limit:
        df = df.sample(n=min(limit, len(df)), random_state=seed)
    enc = [encode_head_tail(tok, t, max_len) for t in df["text"]]
    ds = Dataset.from_dict({"input_ids": [e["input_ids"] for e in enc],
                            "attention_mask": [e["attention_mask"] for e in enc],
                            "labels": [LABEL2ID[l] for l in df["label"]]})
    return ds, df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/splits/train.csv")
    ap.add_argument("--val", default="data/splits/val.csv")
    ap.add_argument("--model", default="microsoft/codebert-base")
    ap.add_argument("--out", default="models/codebert-uml-syntax")
    ap.add_argument("--epochs", type=float, default=5)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--grad_accum", type=int, default=1)
    ap.add_argument("--max_len", type=int, default=512)
    ap.add_argument("--warmup_ratio", type=float, default=0.1)
    ap.add_argument("--weight_decay", type=float, default=0.01)
    ap.add_argument("--patience", type=int, default=2)
    ap.add_argument("--max_train_samples", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    set_seed(a.seed)

    tok = AutoTokenizer.from_pretrained(a.model)
    train_ds, train_df = load(a.train, tok, a.max_len, a.max_train_samples or None, a.seed)
    val_ds, _ = load(a.val, tok, a.max_len)
    print(f"train {len(train_ds)} | val {len(val_ds)} | labels {len(LABELS)}")

    counts = np.bincount(train_ds["labels"], minlength=len(LABELS)).astype(float)
    weights = torch.tensor(np.where(counts > 0, counts.sum() / (len(LABELS) * np.maximum(counts, 1)), 0.0),
                           dtype=torch.float)
    print("class weights:", {LABELS[i]: round(float(w), 2) for i, w in enumerate(weights)})
    missing = [LABELS[i] for i, c in enumerate(counts) if c == 0]
    if missing:
        print("note: no training samples for", missing, "(expected for the strict dataset)")

    model = AutoModelForSequenceClassification.from_pretrained(
        a.model, num_labels=len(LABELS), id2label=ID2LABEL, label2id=LABEL2ID)

    # warm-up given as a number of steps: works in transformers v4 AND v5
    # (v5 removed the 'warmup_ratio' argument)
    steps_per_epoch = math.ceil(len(train_ds) / (a.batch * a.grad_accum))
    warmup_steps = int(a.warmup_ratio * steps_per_epoch * a.epochs)

    use_cuda = torch.cuda.is_available()
    args = TrainingArguments(
        output_dir=a.out + "_checkpoints",
        num_train_epochs=a.epochs,
        learning_rate=a.lr,
        per_device_train_batch_size=a.batch,
        per_device_eval_batch_size=a.batch * 2,
        gradient_accumulation_steps=a.grad_accum,
        warmup_steps=warmup_steps,
        weight_decay=a.weight_decay,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        fp16=use_cuda,
        logging_steps=50,
        report_to="none",
        seed=a.seed,
    )
    trainer = WeightedTrainer(
        class_weights=weights, model=model, args=args,
        train_dataset=train_ds, eval_dataset=val_ds,
        data_collator=DataCollatorWithPadding(tok),
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=a.patience)],
    )
    t0 = time.time()
    trainer.train()
    minutes = (time.time() - t0) / 60
    metrics = trainer.evaluate()
    print("best validation metrics:", json.dumps(metrics, indent=2))

    Path(a.out).mkdir(parents=True, exist_ok=True)
    trainer.save_model(a.out)
    tok.save_pretrained(a.out)
    # everything needed to reproduce the run (proposal Appendix C checklist)
    json.dump({"base_model": a.model, "labels": LABELS, "hyperparameters": vars(a),
               "warmup_steps": warmup_steps,
               "train_rows": len(train_ds), "val_rows": len(val_ds),
               "train_label_counts": train_df["label"].value_counts().to_dict(),
               "val_metrics": metrics, "train_minutes": round(minutes, 1),
               "gpu": torch.cuda.get_device_name(0) if use_cuda else "cpu",
               "torch": torch.__version__, "transformers": transformers.__version__,
               "python": platform.python_version()},
              open(Path(a.out) / "run_config.json", "w"), indent=2)
    print(f"saved model -> {a.out}  ({minutes:.1f} min)")


if __name__ == "__main__":
    main()