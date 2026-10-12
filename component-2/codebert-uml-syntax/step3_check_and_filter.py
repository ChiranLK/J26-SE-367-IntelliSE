"""STEP 3 - Keep only clean, parser-valid, de-duplicated, size-limited diagrams.

Input : data/converted.csv (+ .puml files from step 2)
Output: data/clean.csv   (one row per clean diagram, with a 'group' key for splitting)

Filters, in order:
  1. PlantUML check must say VALID (PumlChecker, one JVM for all files)
  2. rule linter must find nothing (balanced braces/quotes/parentheses)
  3. at least --min_elements declared elements (drops trivial templates)
  4. token length <= --max_tokens (CodeBERT limit is 512 incl. special tokens;
     400 leaves room for step 4 mutations such as a duplicated class block)
  5. exact duplicates (after normalisation) removed

(UML rule checks - duplicates, generalization cycles, use-case relationship
rules - are done in step 4, which skips diagrams that break them.)

Group key (used in step 5 so near-duplicates never cross train/test):
  a real ModelSet 'family' if present, otherwise a fingerprint of the sorted
  element names. Step 1 writes the model id as 'family' when ModelSet has none;
  that is NOT a real family, so the fingerprint is used in that case.

Usage: python step3_check_and_filter.py --in data/converted.csv --out data/clean.csv
"""
import argparse
import csv
import hashlib
import re
from collections import Counter

from common import check_files, lint, normalize

DECL = re.compile(r'^\s*(?:abstract class|class|interface|enum|actor|usecase)\s+("?[^"{]+"?)', re.I)


def element_names(text):
    return sorted({m.group(1).strip('" ').lower() for l in text.split("\n") if (m := DECL.match(l))})


def get_token_counter(name):
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(name)
        return lambda t: len(tok(t, add_special_tokens=True)["input_ids"]), "tokenizer"
    except Exception:
        # fallback: RoBERTa BPE on PlantUML averages ~3 chars/token
        return lambda t: len(t) // 3, "char-estimate"


def group_key(row, names):
    """Real ModelSet family if there is one, otherwise a fingerprint of the element names."""
    fam = (row.get("family") or "").strip()
    if fam and fam != row["id"]:
        return fam, "family"
    return "fp_" + hashlib.md5("|".join(names).encode()).hexdigest()[:12], "fingerprint"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/converted.csv")
    ap.add_argument("--out", default="data/clean.csv")
    ap.add_argument("--tokenizer", default="microsoft/codebert-base")
    ap.add_argument("--max_tokens", type=int, default=400, help="leave room for mutations that add text")
    ap.add_argument("--min_elements", type=int, default=2)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.inp, encoding="utf-8")))
    verdict = check_files([r["puml_path"] for r in rows])
    count_tokens, how = get_token_counter(a.tokenizer)
    stats, group_src, seen, keep = Counter(), Counter(), set(), []
    for r in rows:
        text = normalize(open(r["puml_path"], encoding="utf-8").read())
        if verdict.get(r["puml_path"], ("ERROR",))[0] != "VALID":
            stats["parser_error"] += 1; continue
        if lint(text):
            stats["lint_error"] += 1; continue
        names = element_names(text)
        if len(names) < a.min_elements:
            stats["too_small"] += 1; continue
        n_tok = count_tokens(text)
        if n_tok > a.max_tokens:
            stats["too_long"] += 1; continue
        h = hashlib.md5(text.encode()).hexdigest()
        if h in seen:
            stats["duplicate"] += 1; continue
        seen.add(h)
        group, src = group_key(r, names)
        group_src[src] += 1
        keep.append({"diagram_id": r["id"], "diagram_type": r["diagram_type"], "domain": r["domain"],
                     "group": group, "n_tokens": n_tok, "text": text})
        stats["kept_" + r["diagram_type"]] += 1

    if not keep:
        raise SystemExit(f"0 diagrams kept. stats={dict(stats)}")

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(keep[0].keys()))
        w.writeheader()
        w.writerows(keep)
    print(f"token counting: {how}")
    print(dict(stats))
    print(f"group key source: {dict(group_src)} | distinct groups: {len({k['group'] for k in keep})}")
    print(f"clean diagrams: {len(keep)} -> {a.out}")


if __name__ == "__main__":
    main()