"""STEP 8 - The runtime syntax-validation node for Component 2 (use from LangGraph / FastAPI).

    from uml_syntax_validator import SyntaxValidator, build_refinement_prompt
    v = SyntaxValidator("models/codebert-uml-syntax")
    report = v.validate(llm_output_text, diagram_type="CLASS")   # or "USE_CASE" / None = auto
    if not report["is_valid"]:
        prompt = build_refinement_prompt(report)   # send to Qwen2.5-Coder

Decision rule (PlantUML stays the final parser authority, as in the proposal):
  is_valid = PlantUML VALID
             AND linter finds nothing                       (braces, quotes, parentheses, markers)
             AND UML rules find nothing                     (duplicates, generalization cycles,
                                                             use-case relationship rules)
             AND NOT (CodeBERT predicts an error with confidence >= error_threshold)
The last three conditions catch "silent defects" that PlantUML renders without
complaint. Choose error_threshold on the VALIDATION set with step 7
(table "CodeBERT on the diagrams that passed the deterministic gate").

CLI test: python uml_syntax_validator.py --model models/codebert-uml-syntax --file some.puml
"""
import argparse
import json
import re

from common import LABELS, PersistentChecker, encode_head_tail, lint, normalize, strip_llm_wrapping
from uml_rules import check_rules

HINTS = {
    # --- syntax / notation errors
    "MISSING_STARTUML": "The diagram must start with a line '@startuml'.",
    "MISSING_ENDUML": "The diagram must end with a line '@enduml'.",
    "UNMATCHED_BRACE": "A class/rectangle block has an unmatched '{' or '}'. Every opening brace needs exactly one closing brace.",
    "INVALID_RELATIONSHIP": "A relationship arrow is not valid PlantUML. Use --, -->, ..>, <|--, <|.., *-- or o--.",
    "INVALID_CLASS_DECLARATION": "A class/interface/enum declaration is malformed (keyword spelling or missing name).",
    "INVALID_MEMBER_SYNTAX": "An attribute or method line is malformed (unbalanced parentheses or a broken ':' type part).",
    "INVALID_MULTIPLICITY": "A multiplicity label is malformed. Write it in double quotes, e.g. \"1\" or \"0..*\".",
    "INVALID_USECASE_DECLARATION": "An actor/usecase declaration is malformed (keyword spelling or unclosed quote).",
    "UNSUPPORTED_TOKEN": "The diagram contains text that is not PlantUML (explanations, markdown fences or stray symbols). Remove it.",
    # --- UML rule violations
    "DUPLICATE_ELEMENT": ("The same class / actor / use case is defined more than once. Keep ONE definition "
                          "(merge its attributes and methods) and delete the other definition."),
    "GENERALIZATION_CYCLE": ("Two elements inherit from each other (a generalization cycle). UML does not allow this. "
                             "Keep the inheritance direction that matches the requirements and delete the reverse one."),
    "INVALID_USECASE_RELATIONSHIP": ("A use-case relationship breaks UML rules: <<include>>/<<extend>> may only connect two "
                                     "use cases; actors connect to use cases with a plain association (-->); two actors may "
                                     "only be linked by generalization (<|--); two use cases need <<include>>, <<extend>> "
                                     "or generalization, not a plain association."),
    # --- linter-only findings (no CodeBERT label of their own)
    "UNBALANCED_PARENTHESIS": "A line has an unbalanced '(' or ')'.",
    "UNBALANCED_QUOTE": "A line has an unclosed double quote '\"'.",
}

# What the LLM is ALLOWED to change for each error type. The default rule is
# "change nothing structural", but some fixes need to delete or change an element.
ALLOWED_CHANGE = {
    "DUPLICATE_ELEMENT": "You may delete the duplicate definition (move its members into the remaining one).",
    "GENERALIZATION_CYCLE": "You may delete ONE of the two opposite generalization lines.",
    "INVALID_USECASE_RELATIONSHIP": "You may change or delete ONLY the relationship line(s) named in the feedback.",
    "UNSUPPORTED_TOKEN": "You may delete the lines that are not PlantUML.",
}


def infer_type(text):
    """USE_CASE if the diagram declares an actor or a use case, otherwise CLASS."""
    return "USE_CASE" if re.search(r"^\s*(actor|usecase)\b|^\s*\([^)]+\)|^\s*:[^:]+:", text, re.I | re.M) else "CLASS"


def decide(text, top3, plantuml, lint_problems, rule_problems, threshold):
    """Pure decision logic (no model needed) -> (is_valid, error_type, flagged_by)."""
    status = plantuml[0]
    bert_label, bert_conf = top3[0]["label"], top3[0]["prob"]
    flagged_by = [name for name, hit in (("plantuml", status == "ERROR"), ("linter", bool(lint_problems)),
                                          ("uml_rules", bool(rule_problems)),
                                          ("codebert", bert_label != "VALID" and bert_conf >= threshold)) if hit]
    is_valid = not flagged_by
    if is_valid:
        return True, None, flagged_by
    # most informative error category for reports / refinement:
    #   1. UML rule (exact, with line)  2. CodeBERT category  3. linter rule  4. CodeBERT runner-up
    if rule_problems:
        error_type = rule_problems[0][0]
    elif bert_label != "VALID":
        error_type = bert_label
    elif lint_problems:
        error_type = lint_problems[0][0]
    else:
        error_type = next((c["label"] for c in top3 if c["label"] != "VALID"), "UNKNOWN_SYNTAX_ERROR")
    return False, error_type, flagged_by


class SyntaxValidator:
    def __init__(self, model_dir, error_threshold=0.90, max_len=512, device=None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(self.device).eval()
        model_labels = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]
        if model_labels != LABELS:
            raise SystemExit(f"{model_dir} was trained with {len(model_labels)} labels, common.LABELS has "
                             f"{len(LABELS)}. Retrain the model with the current common.py.")
        self.checker = PersistentChecker()
        self.th, self.max_len = error_threshold, max_len

    def classify(self, text):
        with self.torch.no_grad():
            enc = self.tok.pad([encode_head_tail(self.tok, text, self.max_len)], return_tensors="pt").to(self.device)
            probs = self.torch.softmax(self.model(**enc).logits, -1)[0].cpu()
        top = self.torch.topk(probs, 3)
        return [{"label": LABELS[i], "prob": round(float(p), 4)} for p, i in zip(top.values, top.indices)]

    def validate(self, raw_text, diagram_type=None):
        text = normalize(strip_llm_wrapping(raw_text))
        dtype = diagram_type or infer_type(text)
        top3 = self.classify(text)
        status, line, msg = self.checker.check(text)
        lint_problems = lint(text)
        rule_problems = check_rules(text, dtype)
        is_valid, error_type, flagged_by = decide(text, top3, (status, line, msg), lint_problems,
                                                  rule_problems, self.th)

        feedback = [] if is_valid else [HINTS.get(error_type, "PlantUML reported a syntax error.")]
        if status == "ERROR":
            feedback.append(f"PlantUML: {msg.strip('; ')}" + (f" at line {line}." if line > 0 else "."))
        for rule, ln, why in rule_problems:
            feedback.append(f"UML rule {rule} at line {ln}: {why}.")
        for rule, ln in lint_problems:
            feedback.append(f"Linter: {rule} near line {ln}.")
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


def build_refinement_prompt(report):
    """Targeted-repair prompt for the local LLM (proposal section 3.7.4)."""
    allowed = ALLOWED_CHANGE.get(report["syntax_error_type"], "")
    return (
        "You are fixing a PlantUML diagram. Change ONLY what is needed to fix the problem below. "
        "Do not rename, add or remove classes, actors, use cases, attributes, methods or relationships"
        + (f", except: {allowed}" if allowed else ".") + "\n\n"
        f"Diagram type: {report['diagram_type']}\n"
        f"Detected error type: {report['syntax_error_type']}\n"
        "Validator feedback:\n- " + "\n- ".join(report["feedback"]) + "\n\n"
        "Diagram (line numbers in the feedback count from the first line '@startuml'):\n"
        + report["plantuml_source"] + "\n"
        "Return only the corrected PlantUML, starting with @startuml and ending with @enduml."
    )


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