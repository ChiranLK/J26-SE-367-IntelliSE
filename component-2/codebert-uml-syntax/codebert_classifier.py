"""Loads the fine-tuned CodeBERT model and predicts the error type of a diagram.

    clf = CodeBertClassifier("models/codebert-uml-syntax-s42")
    clf.top3(text)   # [{"label": "VALID", "prob": 0.98}, {...}, {...}]
"""
from common import LABELS, encode_head_tail


class CodeBertClassifier:
    def __init__(self, model_dir, max_len=512, device=None):
        # imported here so the other files can be used without torch installed
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.max_len = max_len
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(self.device).eval()

        # the model must know the same 13 labels, in the same order, as common.py
        model_labels = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]
        if model_labels != LABELS:
            raise SystemExit(f"{model_dir} was trained with {len(model_labels)} labels, common.LABELS has "
                             f"{len(LABELS)}. Retrain the model with the current common.py.")

    def top3(self, text):
        with self.torch.no_grad():
            enc = self.tok.pad([encode_head_tail(self.tok, text, self.max_len)], return_tensors="pt").to(self.device)
            probs = self.torch.softmax(self.model(**enc).logits, -1)[0].cpu()
        top = self.torch.topk(probs, 3)
        return [{"label": LABELS[i], "prob": round(float(p), 4)} for p, i in zip(top.values, top.indices)]