"""STEP 8 - The runtime syntax-validation node for Component 2 (use from LangGraph / FastAPI).

    from uml_syntax_validator import SyntaxValidator, build_refinement_prompt
    v = SyntaxValidator("models/codebert-uml-syntax")
    report = v.validate(llm_output_text, diagram_type="CLASS")   # or "USE_CASE" / None = auto
    if not report["is_valid"]:
        prompt = build_refinement_prompt(report)   # send to Qwen2.5-Coder

This file only connects the parts. Each part lives in its own file:
  codebert_classifier.py  - load CodeBERT, predict the top 3 labels
  validator_decision.py   - VALID / INVALID decision from all checks
  validator_messages.py   - hint texts, allowed changes, fix suggestions
  validator_feedback.py   - feedback lines for the LLM
  refinement_prompt.py    - the repair prompt sent back to the LLM
The PlantUML check and the linter are in common.py, the UML rules in uml_rules.py.

CLI test: python uml_syntax_validator.py --model models/codebert-uml-syntax --file some.puml
"""
import argparse
import json

from codebert_classifier import CodeBertClassifier
from common import PersistentChecker, lint, normalize, strip_llm_wrapping
from refinement_prompt import build_refinement_prompt
from uml_rules import (check_attribute_refs, check_enum_in_class, check_generalization_direction,
                       check_missing_generalization, check_rules, check_unconnected)
from validator_decision import decide, infer_type
from validator_feedback import build_feedback


class SyntaxValidator:
    def __init__(self, model_dir, error_threshold=0.90, max_len=512, device=None):
        self.codebert = CodeBertClassifier(model_dir, max_len, device)
        self.checker = PersistentChecker()
        self.th = error_threshold

    def classify(self, text):
        return self.codebert.top3(text)

    def validate(self, raw_text, diagram_type=None):
        text = normalize(strip_llm_wrapping(raw_text))
        dtype = diagram_type or infer_type(text)

        # 1. run every check
        top3 = self.classify(text)                            # CodeBERT
        status, line, msg = self.checker.check(text)          # PlantUML
        lint_problems = lint(text)                            # linter
        rule_problems = check_rules(text, dtype)              # UML rules
        unconnected = check_unconnected(text, dtype)
        attr_refs = check_attribute_refs(text) if dtype == "CLASS" else []
        if dtype == "CLASS":
            rule_problems += check_generalization_direction(text)
            rule_problems += check_missing_generalization(text)
            rule_problems += check_enum_in_class(text)
        rule_problems += [(rule, ln, msg) for rule, ln, msg, _, _ in unconnected]
        rule_problems += [(rule, ln, msg) for rule, ln, msg, *_ in attr_refs]

        # 2. decide
        is_valid, error_type, flagged_by = decide(text, top3, (status, line, msg), lint_problems,
                                                  rule_problems, self.th)

        # 3. explain
        feedback = build_feedback(text, is_valid, error_type, (status, line, msg), lint_problems,
                                  rule_problems, unconnected, attr_refs)

        return {
            "is_valid": is_valid,
            "syntax_status": "VALID" if is_valid else "INVALID",
            "syntax_error_type": error_type,
            "diagram_type": dtype,
            "flagged_by": flagged_by,                     # which checks failed (for logs / evaluation)
            "codebert": {"prediction": top3[0]["label"], "confidence": top3[0]["prob"], "top3": top3,
                         "threshold": self.th},
            "plantuml": {"status": status, "line": line, "message": msg},
            "lint": [{"rule": r, "line": l} for r, l in lint_problems],
            "uml_rules": [{"rule": r, "line": l, "message": m} for r, l, m in rule_problems],
            "feedback": feedback,
            "plantuml_source": text,
        }

    def close(self):
        self.checker.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/codebert-uml-syntax")
    ap.add_argument("--file", required=True)
    ap.add_argument("--type", choices=["CLASS", "USE_CASE"], default=None, help="diagram type (default: auto)")
    ap.add_argument("--threshold", type=float, default=0.90)
    a = ap.parse_args()
    with SyntaxValidator(a.model, error_threshold=a.threshold) as v:
        r = v.validate(open(a.file, encoding="utf-8").read(), a.type)
        print(json.dumps({k: r[k] for k in r if k != "plantuml_source"}, indent=2))
        if not r["is_valid"]:
            print("\n--- refinement prompt ---\n" + build_refinement_prompt(r))