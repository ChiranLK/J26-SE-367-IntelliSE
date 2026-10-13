"""The final VALID / INVALID decision.

No model is loaded here, it only looks at the results of the four checks:
PlantUML, linter, UML rules and CodeBERT.

  is_valid = PlantUML VALID
             AND linter finds nothing
             AND UML rules find nothing
             AND NOT (CodeBERT predicts an error with confidence >= threshold)
"""
import re

# Every training example of these labels was confirmed by uml_rules.check_rules(),
# so the rules always see them. If CodeBERT predicts one of them and the rules find
# nothing, it is a false alarm (seen on real Qwen output written in Java style,
# e.g. "+Customer customer" inside another class looked like a duplicate).
RULE_VERIFIABLE = {"DUPLICATE_ELEMENT", "GENERALIZATION_CYCLE", "INVALID_USECASE_RELATIONSHIP"}


def infer_type(text):
    """USE_CASE if the diagram declares an actor or a use case, otherwise CLASS."""
    return "USE_CASE" if re.search(r"^\s*(actor|usecase)\b|^\s*\([^)]+\)|^\s*:[^:]+:", text, re.I | re.M) else "CLASS"


def decide(text, top3, plantuml, lint_problems, rule_problems, threshold):
    """Returns (is_valid, error_type, flagged_by)."""
    status = plantuml[0]
    bert_label, bert_conf = top3[0]["label"], top3[0]["prob"]
    bert_flag = bert_label != "VALID" and bert_conf >= threshold
    if bert_flag and bert_label in RULE_VERIFIABLE and bert_label not in {p[0] for p in rule_problems}:
        bert_flag = False
    flagged_by = [name for name, hit in (("plantuml", status == "ERROR"), ("linter", bool(lint_problems)),
                                          ("uml_rules", bool(rule_problems)),
                                          ("codebert", bert_flag)) if hit]
    is_valid = not flagged_by
    if is_valid:
        return True, None, flagged_by
    # most informative error category for reports / refinement:
    #   1. UML rule (exact, with line)  2. CodeBERT category  3. linter rule  4. CodeBERT runner-up
    if rule_problems:
        error_type = rule_problems[0][0]
    elif bert_label != "VALID" and bert_label not in RULE_VERIFIABLE:
        error_type = bert_label
    elif lint_problems:
        error_type = lint_problems[0][0]
    else:
        error_type = next((c["label"] for c in top3 if c["label"] != "VALID" and c["label"] not in RULE_VERIFIABLE),
                          "UNKNOWN_SYNTAX_ERROR")
    return False, error_type, flagged_by