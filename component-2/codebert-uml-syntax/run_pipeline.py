import argparse
import csv
import json
import re
import time
from pathlib import Path

from common import normalize, strip_llm_wrapping
from llm_client import DEFAULT_MODEL, ask, is_running
from prompts import generation_prompt
from uml_parser import clean_name, parse
from uml_syntax_validator import SyntaxValidator, build_refinement_prompt

LOG_FIELDS = ["time", "project", "diagram_type", "llm_model", "rounds", "valid_first_try",
              "valid_final", "error_types", "flagged_by", "llm_seconds", "out_file"]


def for_display(puml):
    # show - + # ~ as text instead of the coloured square / circle icons.
    # Only added to the saved files, the validator always sees the diagram as Qwen wrote it.
    return puml.replace("@startuml", "@startuml\nskinparam classAttributeIconSize 0", 1)


def missing_fixes(last_report, puml):
    """Lines the last feedback asked for ('Replace "A" with "B"') that are not in the
    new diagram. Qwen sometimes deletes a line instead of replacing it, e.g. it was told
    to write "Person <|-- Trainer" and just removed the old line. The rules cannot see
    that, because the diagram is still valid UML - only the inheritance is gone."""
    have = {(frozenset((clean_name(r["a"]), clean_name(r["b"]))), r["kind"]) for r in parse(puml)[1]}
    missing = []
    for line in last_report["feedback"]:
        if not line.startswith("How to fix:"):
            continue
        for wanted in re.findall(r'with "([^"]+)"', line):
            rels = parse(wanted)[1]
            if len(rels) != 1:
                continue
            r = rels[0]
            if (frozenset((clean_name(r["a"]), clean_name(r["b"]))), r["kind"]) not in have:
                missing.append(wanted)
    return missing


def run_one(validator, srs_text, diagram_type, project, out_dir, model, max_rounds, temperature):
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = generation_prompt(srs_text, diagram_type)
    errors, flags, llm_time = [], [], 0.0
    previous = None
    report = last_report = None

    temp = temperature
    for rnd in range(max_rounds + 1):
        t0 = time.time()
        reply = ask(prompt, model=model, temperature=temp)
        round_secs = time.time() - t0
        llm_time += round_secs

        puml = normalize(strip_llm_wrapping(reply))
        (out_dir / f"{project}_{diagram_type}_r{rnd}.puml").write_text(for_display(puml), encoding="utf-8")

        report = validator.validate(puml, diagram_type)
        if last_report is not None:
            lost = missing_fixes(last_report, puml)
            if lost:
                if report["is_valid"]:
                    report.update(is_valid=False, syntax_status="INVALID", feedback=[],
                                  syntax_error_type=last_report["syntax_error_type"])
                report["flagged_by"] = report["flagged_by"] + ["repair_check"]
                report["feedback"] += [f'The last fix was not done: the diagram must contain the line "{x}". '
                                       f'Add it after the class blocks.' for x in lost]
        status = "VALID" if report["is_valid"] else report["syntax_error_type"]
        print(f"  round {rnd}: {status}  {report['flagged_by']}   (LLM {round_secs:.0f}s)")

        if rnd == 0:
            valid_first = report["is_valid"]
        if report["is_valid"]:
            break
        errors.append(report["syntax_error_type"])
        flags.append("+".join(report["flagged_by"]))
        if rnd == max_rounds:
            break

        if puml == previous:
            # The model sent back the same diagram. Try once more with a higher
            # temperature, so it does not keep repeating itself.
            if temp >= 0.7:
                print("  same diagram again, stopping")
                break
            temp = 0.7
            print("  same diagram as last round, retrying with temperature 0.7")
        previous = puml
        last_report = report
        prompt = "The diagram was made from this SRS:\n\n" + srs_text.strip() + "\n\n" + build_refinement_prompt(report)

    final_file = out_dir / f"{project}_{diagram_type}_final.puml"
    final_file.write_text(for_display(report["plantuml_source"]), encoding="utf-8")
    return {
        "time": time.strftime("%Y-%m-%d %H:%M"),
        "project": project,
        "diagram_type": diagram_type,
        "llm_model": model,
        "rounds": rnd,
        "valid_first_try": valid_first,
        "valid_final": report["is_valid"],
        "error_types": ";".join(errors),
        "flagged_by": ";".join(flags),
        "llm_seconds": round(llm_time, 1),
        "out_file": str(final_file),
    }


def append_log(rows, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new_file:
            w.writeheader()
        w.writerows(rows)


def summary(rows):
    n = len(rows)
    first = sum(r["valid_first_try"] for r in rows)
    final = sum(r["valid_final"] for r in rows)
    broken = n - first
    fixed = sum(1 for r in rows if not r["valid_first_try"] and r["valid_final"])
    print(f"\nruns: {n}")
    print(f"valid on first try : {first}/{n}")
    print(f"valid after repair : {final}/{n}")
    if broken:
        print(f"refinement success : {fixed}/{broken} = {100 * fixed / broken:.1f}% of the broken diagrams were fixed")


def srs_from_json_project(p):
    lines = [f"Project: {p.get('name', p['project_id'])}", "", "Functional Requirements:", ""]
    lines += [f"{r['id']}: {r['text']}" for r in p["requirements"]]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srs", help="text file with one SRS")
    ap.add_argument("--srs_json", help="JSON file with many projects (like sample_srs.json)")
    ap.add_argument("--type", choices=["CLASS", "USE_CASE", "BOTH"], default="BOTH")
    ap.add_argument("--validator_model", default="models/codebert-uml-syntax-s42")
    ap.add_argument("--llm", default=DEFAULT_MODEL)
    ap.add_argument("--max_rounds", type=int, default=3, help="repair attempts after the first generation")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--log", default="results/pipeline_log.csv")
    a = ap.parse_args()

    if not (a.srs or a.srs_json):
        ap.error("give --srs or --srs_json")
    if not is_running():
        raise SystemExit("Ollama is not running. Start the Ollama app and try again.")

    if a.srs:
        jobs = [(Path(a.srs).stem, Path(a.srs).read_text(encoding="utf-8"))]
    else:
        projects = json.load(open(a.srs_json, encoding="utf-8"))
        jobs = [(p["project_id"], srs_from_json_project(p)) for p in projects]
    types = ["CLASS", "USE_CASE"] if a.type == "BOTH" else [a.type]

    rows = []
    with SyntaxValidator(a.validator_model) as validator:
        for project, srs_text in jobs:
            for dt in types:
                print(f"{project} / {dt}")
                rows.append(run_one(validator, srs_text, dt, project, Path(a.out),
                                    a.llm, a.max_rounds, a.temperature))
    append_log(rows, Path(a.log))
    summary(rows)
    print(f"\nlog -> {a.log}   diagrams -> {a.out}/")


if __name__ == "__main__":
    main()