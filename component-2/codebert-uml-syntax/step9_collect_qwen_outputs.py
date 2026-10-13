import argparse
import csv
import json
import time
import urllib.request
from collections import Counter

from common import LABELS, check_texts, lint, normalize, strip_llm_wrapping
from uml_rules import check_rules

# Same prompts as run_pipeline.py, so this test set shows the mistakes the
# real pipeline will see.
from prompts import TEMPLATES, generation_prompt


def srs_text(proj):
    lines = [f"Project: {proj.get('name', proj['project_id'])}", "", "Functional Requirements:", ""]
    lines += [f"{r['id']}: {r['text']}" for r in proj["requirements"]]
    return "\n".join(lines)


# linter problem -> closest label (only a suggestion; you confirm it by hand)
LINT_TO_LABEL = {"MISSING_STARTUML": "MISSING_STARTUML", "MISSING_ENDUML": "MISSING_ENDUML",
                 "UNMATCHED_BRACE": "UNMATCHED_BRACE"}


def chat(base_url, model, prompt, temperature):
    body = json.dumps({"model": model, "temperature": temperature,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def suggest(text, dtype, parser_status, parser_line):
    """All deterministic problems (sorted by line) + a suggested label for the first one."""
    lines = text.split("\n")
    probs = []
    for p, ln in lint(text):
        lab = LINT_TO_LABEL.get(p)
        if lab is None:                                   # unbalanced ( or "
            line = lines[ln - 1].strip().lower() if 0 < ln <= len(lines) else ""
            if line.startswith(("actor", "usecase")):
                lab = "INVALID_USECASE_DECLARATION"
            elif p == "UNBALANCED_QUOTE" and ("--" in line or ".." in line):
                lab = "INVALID_MULTIPLICITY"
            elif p == "UNBALANCED_PARENTHESIS" and dtype == "CLASS":
                lab = "INVALID_MEMBER_SYNTAX"
            else:
                lab = "?"
        probs.append((ln, lab, p))
    for lab, ln, msg in check_rules(text, dtype):
        probs.append((ln, lab, msg))
    if parser_status == "ERROR" and not probs:
        probs.append((parser_line, "?", "PlantUML error - decide the label by hand"))
    probs.sort(key=lambda x: x[0] if x[0] and x[0] > 0 else 10 ** 6)
    label = probs[0][1] if probs else "VALID"
    return label, "; ".join(f"line {ln}: {lab} ({msg})" for ln, lab, msg in probs)


def collect(a):
    projects = json.load(open(a.srs, encoding="utf-8"))
    rows = []
    for proj in projects:
        srs = srs_text(proj)
        for dtype in TEMPLATES:
            for run in range(a.runs):
                t0 = time.time()
                try:
                    raw = chat(a.base_url, a.model, generation_prompt(srs, dtype), a.temperature)
                except Exception as ex:                   # server stopped / timeout: keep going
                    print(f"{proj['project_id']} {dtype} run {run}: FAILED ({ex})")
                    continue
                rows.append({"sample_id": f"Q{len(rows):04d}", "project_id": proj["project_id"],
                             "diagram_id": f"{proj['project_id']}_{dtype}_{run}", "group": proj["project_id"],
                             "domain": proj.get("domain", proj["project_id"]), "diagram_type": dtype, "run": run,
                             "seconds": round(time.time() - t0, 1), "raw_output": raw,
                             "text": normalize(strip_llm_wrapping(raw))})
                print(f"{proj['project_id']} {dtype} run {run}: {rows[-1]['seconds']}s")
    if not rows:
        raise SystemExit("no outputs collected - is Ollama / LM Studio running?")

    verdicts = check_texts([r["text"] for r in rows])
    seen = set()
    for r, (st, ln, msg) in zip(rows, verdicts):
        label, problems = suggest(r["text"], r["diagram_type"], st, ln)
        r.update({"parser_status": st, "parser_line": ln, "parser_message": msg,
                  "problems": problems, "suggested_label": label, "label": label, "reviewed": "",
                  "duplicate_output": "yes" if r["text"] in seen else ""})
        seen.add(r["text"])
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig: opens cleanly in Excel
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} outputs -> {a.out}")
    print("suggested labels:", dict(Counter(r["suggested_label"] for r in rows)))
    print("Now review every row by hand (see the instructions at the top of this file).")


def finalize(a):
    rows = list(csv.DictReader(open(a.out, encoding="utf-8-sig")))
    done = [r for r in rows if r.get("reviewed", "").strip().upper() == "Y"]
    keep, other, bad, dup = [], 0, Counter(), 0
    seen = set()
    for r in done:
        lab = r["label"].strip().upper()
        if lab == "OTHER":
            other += 1; continue
        if lab not in LABELS:
            bad[lab or "(empty)"] += 1; continue
        if r["text"] in seen:                             # same output twice -> count once
            dup += 1; continue
        seen.add(r["text"])
        keep.append({**r, "label": lab})
    if not keep:
        raise SystemExit("no reviewed rows yet (write Y in the 'reviewed' column)")
    with open(a.final, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(keep[0].keys()))
        w.writeheader()
        w.writerows(keep)
    changed = sum(1 for r in done if r["label"].strip().upper() != r["suggested_label"])
    print(f"reviewed {len(done)} / {len(rows)} rows")
    print(f"kept {len(keep)} -> {a.final}  | duplicates removed: {dup}")
    print(f"errors outside the 13 labels (OTHER): {other}   <- report this in the thesis")
    print(f"labels you changed from the suggestion: {changed}")
    if bad:
        print("WARNING: unknown labels (fix the spelling):", dict(bad))
    print("label counts:", dict(Counter(r["label"] for r in keep)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srs", default="sample_srs.json")
    ap.add_argument("--base_url", default="http://localhost:11434/v1")
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--out", default="data/qwen_outputs.csv")
    ap.add_argument("--final", default="data/qwen_test.csv")
    ap.add_argument("--finalize", action="store_true", help="turn the reviewed CSV into the step 7 test file")
    a = ap.parse_args()
    finalize(a) if a.finalize else collect(a)


if __name__ == "__main__":
    main()