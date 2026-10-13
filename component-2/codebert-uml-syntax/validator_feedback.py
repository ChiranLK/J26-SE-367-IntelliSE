import re

from uml_parser import parse
from validator_messages import HINTS, merge_duplicate_fix, suggest_fix


def build_feedback(text, is_valid, error_type, plantuml, lint_problems, rule_problems, unconnected, attr_refs):
    status, line, msg = plantuml
    src_lines = text.split("\n")

    def quote(ln):
        if 0 < ln <= len(src_lines) and src_lines[ln - 1].strip():
            return f' The line is: "{src_lines[ln - 1].strip()}"'
        return ""

    # 1. general hint for the main error type
    feedback = [] if is_valid else [HINTS.get(error_type, "PlantUML reported a syntax error.")]

    # 2. PlantUML parser message
    if status == "ERROR":
        feedback.append(f"PlantUML: {msg.strip('; ')}" + (f" at line {line}.{quote(line)}" if line > 0 else "."))

    # 3. UML rule problems
    # The same mistake repeated on many lines (e.g. 20 use cases chained with
    # arrows) is written as ONE instruction, otherwise a small model gets lost.
    by_msg = {}
    for rule, ln, why in rule_problems:
        by_msg.setdefault((rule, why), []).append(ln)
    for (rule, why), lns in by_msg.items():
        shown = [src_lines[ln - 1].strip() for ln in lns if 0 < ln <= len(src_lines)]
        fixes = [f for f in (suggest_fix(why, x) for x in shown) if f]
        first = re.search(r"already defined on line (\d+)", why)
        if rule == "DUPLICATE_ELEMENT" and first:
            fixes = [merge_duplicate_fix(text, int(first.group(1)), ln) for ln in lns]
        if len(lns) <= 2:
            for ln in lns:
                feedback.append(f"UML rule {rule} at line {ln}: {why}.{quote(ln)}")
        else:
            feedback.append(f"UML rule {rule} on {len(lns)} lines: {why}.")
        if fixes:
            feedback.append("How to fix: " + " ".join(fixes))

    # 4. unconnected elements - suggestion uses real names from the diagram
    if unconnected:
        actors = [ref for _, _, _, kind, ref in unconnected if kind == "actor"]
        ucs = [ref for _, _, _, kind, ref in unconnected if kind == "usecase"]
        main_actor = next((r["a"] for r in parse(text)[1] if r["kind"] == "association"), "Actor")
        tips = [f'connect use case {u} to the actor who performs it (for example "{main_actor} --> {u}")'
                for u in ucs]
        tips += [f'connect actor {a} to the use case it takes part in (for example "UseCase --> {a}")'
                 for a in actors]
        tips += [f'connect class {c} to the class it belongs to with an association line'
                 for _, _, _, kind, c in unconnected if kind == "class"]
        feedback.append("How to fix: " + "; ".join(tips) + ".")

    # 5. class-typed attributes that should be association lines
    if attr_refs:
        fixes = []
        for _, _, _, owner, attr_line, target, many in attr_refs:
            mult = f'{owner} "1" -- "0..*" {target}' if many else f'{target} "1" -- "0..*" {owner}'
            fixes.append(f'in class {owner} remove "{attr_line}" and add the line {mult} '
                         f'(adjust the multiplicities to the SRS)')
        feedback.append("How to fix: " + "; ".join(fixes) + ".")

    # 6. linter findings
    for rule, ln in lint_problems:
        feedback.append(f"Linter: {rule} near line {ln}.{quote(ln)}")
    return feedback