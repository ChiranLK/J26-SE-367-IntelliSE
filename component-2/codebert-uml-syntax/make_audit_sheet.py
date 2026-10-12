"""Manual label check (do this once after step 4, before training).

1) Make the sheet (20 random samples per label):
     python make_audit_sheet.py
   -> data/audit_sheet.csv . Open it in Excel. For every row look at the
      'change' column (ADD: = line added, DEL: = line removed, || separates lines)
      and type Y in 'label_correct' if the label really describes the change,
      N if not. Write a short reason in 'note' for every N.

   Need to see the whole diagram of one row?
     python make_audit_sheet.py --show S036734

2) Score it:
     python make_audit_sheet.py --score
   -> label accuracy per label. Put this table in your thesis
      (e.g. "manual audit of 260 samples: 98.5% labels correct").
"""
import argparse
import csv
import difflib
import random
from collections import Counter, defaultdict


def make(a):
    clean = {r["diagram_id"]: r["text"] for r in csv.DictReader(open(a.clean, encoding="utf-8"))}
    by_label = defaultdict(list)
    for r in csv.DictReader(open(a.data, encoding="utf-8")):
        by_label[r["label"]].append(r)
    rng = random.Random(a.seed)
    out = []
    for lab, rows in sorted(by_label.items()):
        for r in rng.sample(rows, min(a.n, len(rows))):
            src = clean.get(r["diagram_id"], "")
            diff = [("ADD: " if l[0] == "+" else "DEL: ") + l[1:].strip()
                    for l in difflib.unified_diff(src.split("\n"), r["text"].split("\n"), lineterm="", n=0)
                    if l[:1] in "+-" and not l.startswith(("+++", "---"))]
            # 'ADD:' / 'DEL:' instead of '+' / '-' so Excel does not read the cell as a formula (#NAME?)
            out.append({"sample_id": r["sample_id"], "label": lab, "diagram_type": r["diagram_type"],
                        "parser_status": r["parser_status"], "line": r["mutated_line"],
                        "change": " || ".join(diff) if diff else "(no change: original diagram)",
                        "label_correct": "", "note": ""})
    with open(a.sheet, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig so Excel shows it correctly
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} rows -> {a.sheet}. Fill the 'label_correct' column with Y / N.")


def show(a):
    """print one sample with line numbers, the mutated line marked with >>"""
    for r in csv.DictReader(open(a.data, encoding="utf-8")):
        if r["sample_id"] == a.show:
            ml = int(r["mutated_line"])
            print(f"{r['sample_id']}  label={r['label']}  type={r['diagram_type']}  "
                  f"PlantUML={r['parser_status']}  mutated line={ml}\n")
            for i, l in enumerate(r["text"].split("\n"), 1):
                print(f"{'>>' if i == ml else '  '} {i:3d} | {l}")
            return
    print("sample_id not found:", a.show)


def score(a):
    rows = list(csv.DictReader(open(a.sheet, encoding="utf-8-sig")))
    done = [r for r in rows if r["label_correct"].strip().upper() in ("Y", "N")]
    if not done:
        print("no Y/N answers found yet")
        return
    tot, ok = Counter(), Counter()
    for r in done:
        tot[r["label"]] += 1
        ok[r["label"]] += r["label_correct"].strip().upper() == "Y"
    print(f"{'label':30s} {'checked':>8s} {'correct':>8s}")
    for lab in sorted(tot):
        print(f"{lab:30s} {tot[lab]:8d} {100 * ok[lab] / tot[lab]:7.1f}%")
    print(f"{'ALL':30s} {sum(tot.values()):8d} {100 * sum(ok.values()) / sum(tot.values()):7.1f}%")
    for r in done:
        if r["label_correct"].strip().upper() == "N":
            print("  wrong:", r["sample_id"], r["label"], "-", r["note"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/syntax_dataset.csv")
    ap.add_argument("--clean", default="data/clean.csv")
    ap.add_argument("--sheet", default="data/audit_sheet.csv")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--show", default="", help="sample_id to print in full")
    a = ap.parse_args()
    if a.show:
        show(a)
    elif a.score:
        score(a)
    else:
        make(a)