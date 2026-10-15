from validator_messages import ALLOWED_CHANGE


def build_refinement_prompt(report):
    types = [report["syntax_error_type"]] + [p["rule"] for p in report.get("uml_rules", [])]
    allowed = " ".join(dict.fromkeys(ALLOWED_CHANGE[t] for t in types if t in ALLOWED_CHANGE))
    rules = ("Do not rename, add or remove classes, actors, use cases, attributes, methods or relationships"
             + (f", except: {allowed}" if allowed else "."))
    return (
        f"Here is a PlantUML {report['diagram_type'].replace('_', ' ').lower()} diagram that has a problem.\n\n"
        + report["plantuml_source"] + "\n"
        f"Problem type: {report['syntax_error_type']}\n"
        "What is wrong:\n- " + "\n- ".join(report["feedback"]) + "\n\n"
        "Fix ONLY these problems. " + rules + "\n"
        "The corrected diagram must be different from the one above.\n"
        "Return only the corrected PlantUML, starting with @startuml and ending with @enduml."
    )