import argparse
import csv
import random
import re
from collections import Counter
from pathlib import Path

from common import LABEL2ID, check_texts, lint, normalize
from uml_parser import endpoint_kind, kind_lookup, parse
from uml_rules import check_rules
from step3_check_and_filter import get_token_counter

REL_ARROW = re.compile(r"(<\|--|<\|\.\.|\*--|o--|\.\.>|-->|--)")
BAD_ARROWS = ["->->", "--|>>", "<-->>", "~~>", "-->>", "-->-->", "--x-->", "-- >", "*-->*", "->o<-"]
CLASS_DECL = re.compile(r"^(\s*)(abstract class|class|interface|enum)(\s+)(\w+)(.*)$")
CLASS_TYPOS = {"class": ["clss", "clas", "classs", "calss", "cls"], "interface": ["interfce", "intrface", "interfacee"],
               "enum": ["enm", "enumm", "emun"], "abstract class": ["abstract clss", "abstrct class", "abstract clas"]}
UC_DECL = re.compile(r"^(\s*)(actor|usecase)\b(.*)$")
UC_TYPOS = {"actor": ["actr", "acotr", "actorr", "ator"], "usecase": ["usecse", "use case", "usecasee", "usecas"]}
MULT = re.compile(r'"(\d+|\*|\d+\.\.(?:\d+|\*))"')
# Typical things an LLM writes INTO a diagram. (';' and '...' were removed because
# PlantUML treats them as harmless, so labelling them as errors would be noisy.)
LLM_NOISE = ["Here is the updated class diagram:", "Here is the corrected PlantUML code:", "```", "```plantuml",
             "Note: this class handles the main logic.", "The diagram below shows the relationships.",
             "<<<>>>", "// TODO: add remaining classes", "# relationships", "Explanation:",
             "1. The Customer places an Order.", "**Classes:**", "- Customer: represents a user"]


def lines_of(t):
    return t.rstrip("\n").split("\n")


def join(ls):
    return "\n".join(ls) + "\n"


def body_range(ls):
    s = next(i for i, l in enumerate(ls) if l.strip().lower().startswith("@startuml"))
    e = max(i for i, l in enumerate(ls) if l.strip().lower().startswith("@enduml"))
    return s, e


def indent_of(line):
    return line[: len(line) - len(line.lstrip())]


# ------------------------------------------------------------- syntax error operators
# each returns (new_text, 1-based line number of the defect) or None if not applicable
def m_missing_startuml(t, dt, rng):
    ls = lines_of(t); s, _ = body_range(ls)
    del ls[s]
    return join(ls), 1


def m_missing_enduml(t, dt, rng):
    ls = lines_of(t); _, e = body_range(ls)
    del ls[e]
    return join(ls), len(ls)


def m_unmatched_brace(t, dt, rng):
    ls = lines_of(t)
    closes = [i for i, l in enumerate(ls) if l.strip() == "}"]
    opens = [i for i, l in enumerate(ls) if l.rstrip().endswith("{")]
    if not closes:
        return None
    if opens and rng.random() < 0.5:
        i = rng.choice(opens)
        ls[i] = ls[i].rstrip()[:-1].rstrip()        # drop the '{' -> orphan '}'
    else:
        i = rng.choice(closes)
        del ls[i]                                    # drop a '}' -> block never closes
    return join(ls), i + 1


def m_invalid_relationship(t, dt, rng):
    ls = lines_of(t)
    cand = [i for i, l in enumerate(ls) if REL_ARROW.search(l) and not l.strip().startswith(("class", "actor", "usecase", "'"))
            and not l.strip().startswith(("+", "-", "#", "~")) and len(l.split()) >= 3]
    if not cand:
        return None
    i = rng.choice(cand)
    ls[i] = REL_ARROW.sub(rng.choice(BAD_ARROWS), ls[i], count=1)
    return join(ls), i + 1


def m_invalid_class_declaration(t, dt, rng):
    if dt != "CLASS":
        return None
    ls = lines_of(t)
    cand = [i for i, l in enumerate(ls) if CLASS_DECL.match(l)]
    if not cand:
        return None
    i = rng.choice(cand)
    ind, kw, sp, name, rest = CLASS_DECL.match(ls[i]).groups()
    if rng.random() < 0.7:
        ls[i] = f"{ind}{rng.choice(CLASS_TYPOS[kw])}{sp}{name}{rest}"   # keyword typo
    else:
        ls[i] = f"{ind}{kw}{rest if rest.strip() else ' {'}"            # missing class name
    return join(ls), i + 1


def m_invalid_member_syntax(t, dt, rng):
    if dt != "CLASS":
        return None
    ls = lines_of(t)
    ops = [i for i, l in enumerate(ls) if "(" in l and ")" in l and not CLASS_DECL.match(l) and "--" not in l]
    attrs = [i for i, l in enumerate(ls) if re.match(r"^\s+[+\-#~]?\w+ : \w+$", l)]
    if ops and (not attrs or rng.random() < 0.7):
        i = rng.choice(ops)
        ls[i] = ls[i].replace(")", "", 1) if rng.random() < 0.5 else ls[i].replace("(", "((", 1)
    elif attrs:
        i = rng.choice(attrs)
        ls[i] = re.sub(r" : \w+$", rng.choice([" : :", " ::"]), ls[i])   # ' :' (type left out) removed: UML allows it
    else:
        return None
    return join(ls), i + 1


def m_invalid_multiplicity(t, dt, rng):
    ls = lines_of(t)
    cand = [i for i, l in enumerate(ls) if MULT.search(l)]
    if not cand:
        return None
    i = rng.choice(cand)
    ms = list(MULT.finditer(ls[i]))
    m = rng.choice(ms)
    ls[i] = ls[i][:m.start()] + '"' + m.group(1) + ls[i][m.end():]     # drop closing quote
    return join(ls), i + 1


def m_invalid_usecase_declaration(t, dt, rng):
    if dt != "USE_CASE":
        return None
    ls = lines_of(t)
    cand = [i for i, l in enumerate(ls) if UC_DECL.match(l)]
    if not cand:
        return None
    i = rng.choice(cand)
    ind, kw, rest = UC_DECL.match(ls[i]).groups()
    if '"' in rest and rng.random() < 0.4:
        j = rest.rfind('"')
        ls[i] = f"{ind}{kw}{rest[:j]}{rest[j + 1:]}"                    # unclosed quote in the name
    else:
        ls[i] = f"{ind}{rng.choice(UC_TYPOS[kw])}{rest}"                # keyword typo
    return join(ls), i + 1


# Inside a class body PlantUML reads 'Name: text' or '# name' as an attribute, so noise of that
# shape would be a legal member there. Only use it outside class bodies.
MEMBER_LIKE = re.compile(r"^\s*[+\-#~]?\s*\w+\s*:"        # 'Name: text'      -> attribute
                         r"|^\s*[+\-#~]\s*\w+\s*$")          # '# relationships' -> protected attribute


def m_unsupported_token(t, dt, rng):
    ls = lines_of(t); s, e = body_range(ls)
    pos = rng.randint(s + 1, e)          # somewhere inside the diagram body
    depth = sum(l.count("{") - l.count("}") for l in ls[s + 1:pos])
    choices = [n for n in LLM_NOISE if not (depth > 0 and MEMBER_LIKE.match(n))]
    ls.insert(pos, rng.choice(choices))
    return join(ls), pos + 1


# ------------------------------------------------------------- UML rule operators (new)
def m_duplicate_element(t, dt, rng):
    """Define an existing class / actor / use case a second time."""
    ls = lines_of(t); _, e = body_range(ls)
    els, _ = parse(t)
    wanted = ("class",) if dt == "CLASS" else ("actor", "usecase")
    decls = [x for x in els if not x.get("inline") and x["kind"] in wanted
             and (x["kind"] != "class" or x.get("has_body"))]   # a bare 'class A' copy is legal PlantUML
    if not decls:
        return None
    d = rng.choice(decls)
    i = d["line"] - 1
    if dt == "CLASS":
        if ls[i].rstrip().endswith("{"):             # copy the whole block, maybe with fewer members
            depth, j = 0, i
            for j in range(i, e):
                depth += ls[j].count("{") - ls[j].count("}")
                if depth <= 0:
                    break
            members = ls[i + 1:j]
            if len(members) > 1 and rng.random() < 0.5:
                members = rng.sample(members, k=max(1, len(members) // 2))
            block = [ls[i]] + members + [ls[j]]
            pos = j + 1
        else:
            block, pos = [ls[i]], i + 1
    else:                                            # same display name, new alias -> a second actor / use case
        kw = d["kind"]
        alias = ("A" if kw == "actor" else "UC") + f"_d{rng.randint(100, 999)}"
        block, pos = [f'{indent_of(ls[i])}{kw} "{d["display"]}" as {alias}'], i + 1
    ls[pos:pos] = block
    return join(ls), pos + 1


def m_generalization_cycle(t, dt, rng):
    """Make a parent inherit from its own child (A <|-- B and B <|-- A)."""
    ls = lines_of(t); _, e = body_range(ls)
    els, rels = parse(t)
    gens = [r for r in rels if r["kind"] == "generalization" and r["parent"] != r["child"]]
    if gens:
        r = rng.choice(gens)
        child, parent = (r["b"], r["a"]) if r["arrow"].startswith("<|") else (r["a"], r["b"])
        new = [f"{child} <|-- {parent}" if rng.random() < 0.5 else f"{parent} --|> {child}"]
    elif dt == "CLASS":
        cls = [x["ref"] for x in els if x["kind"] == "class" and not x["scope"] and not x.get("inline")]
        if len(cls) < 2:
            return None
        a, b = rng.sample(cls, 2)
        new = [f"{a} <|-- {b}", f"{b} <|-- {a}"]
    else:
        return None
    ls[e:e] = new                                    # relationships go just before @enduml (top level)
    return join(ls), e + 1


def m_invalid_usecase_relationship(t, dt, rng):
    """Break a UML use-case rule: actor in include/extend, actor-actor association,
    actor-use case generalization, or a plain association between two use cases."""
    if dt != "USE_CASE":
        return None
    ls = lines_of(t); _, e = body_range(ls)
    els, rels = parse(t)
    kinds = kind_lookup(els)
    refs = {}
    for x in els:                                    # one reference token per element (prefer declarations)
        if x["kind"] in ("actor", "usecase") and (x["name"] not in refs or not x.get("inline")):
            refs[x["name"]] = (x["kind"], x["ref"])
    actors = [r for k, r in refs.values() if k == "actor"]
    ucs = [r for k, r in refs.values() if k == "usecase"]
    assoc = [r for r in rels if r["kind"] == "association"
             and {endpoint_kind(r["a"], kinds), endpoint_kind(r["b"], kinds)} == {"actor", "usecase"}]
    variants = []
    if assoc:
        variants.append("actor_include")
    if len(actors) >= 2:
        variants.append("actor_actor")
    if actors and ucs:
        variants.append("gen_actor_uc")
    if len(ucs) >= 2:
        variants.append("uc_uc")
    if not variants:
        return None
    v = rng.choice(variants)
    if v == "actor_include":                         # turn 'Customer --> UC1' into 'Customer ..> UC1 : <<include>>'
        r = rng.choice(assoc)
        a, b = (r["a"], r["b"]) if endpoint_kind(r["a"], kinds) == "actor" else (r["b"], r["a"])
        i = r["line"] - 1
        ls[i] = f"{indent_of(ls[i])}{a} ..> {b} : <<{rng.choice(['include', 'extend'])}>>"
        return join(ls), i + 1
    if v == "actor_actor":
        a, b = rng.sample(actors, 2)
        new = f"{a} {rng.choice(['--', '-->'])} {b}"
    elif v == "gen_actor_uc":
        a, u = rng.choice(actors), rng.choice(ucs)
        new = f"{u} <|-- {a}" if rng.random() < 0.5 else f"{a} <|-- {u}"
    else:
        u1, u2 = rng.sample(ucs, 2)
        new = f"{u1} {rng.choice(['--', '-->'])} {u2}"
    ls.insert(e, new)
    return join(ls), e + 1


# PlantUML must reject the mutant (some "wrong" arrows/keywords are actually legal).
PARSER_CONFIRMED = {"INVALID_RELATIONSHIP", "INVALID_CLASS_DECLARATION",
                    "INVALID_MULTIPLICITY", "INVALID_USECASE_DECLARATION"}
# PlantUML renders these, so the UML rule checker must confirm the violation.
RULE_VERIFIED = {"DUPLICATE_ELEMENT", "GENERALIZATION_CYCLE", "INVALID_USECASE_RELATIONSHIP"}

OPERATORS = {
    "MISSING_STARTUML": m_missing_startuml,
    "MISSING_ENDUML": m_missing_enduml,
    "UNMATCHED_BRACE": m_unmatched_brace,
    "INVALID_RELATIONSHIP": m_invalid_relationship,
    "INVALID_CLASS_DECLARATION": m_invalid_class_declaration,
    "INVALID_MEMBER_SYNTAX": m_invalid_member_syntax,
    "INVALID_MULTIPLICITY": m_invalid_multiplicity,
    "INVALID_USECASE_DECLARATION": m_invalid_usecase_declaration,
    "UNSUPPORTED_TOKEN": m_unsupported_token,
    "DUPLICATE_ELEMENT": m_duplicate_element,
    "GENERALIZATION_CYCLE": m_generalization_cycle,
    "INVALID_USECASE_RELATIONSHIP": m_invalid_usecase_relationship,
}


# ------------------------------------------------------------- valid augmentations
def a_valid(t, dt, rng):
    ls = lines_of(t); s, e = body_range(ls)
    ops = ["comment", "title", "skin", "shuffle"]
    for op in rng.sample(ops, k=rng.randint(1, 3)):
        s, e = body_range(ls)
        if op == "comment":
            ls.insert(rng.randint(s + 1, e), f"' REQ-{rng.randint(1, 99):02d} {rng.choice(['traceability', 'generated', 'reviewed'])}")
        elif op == "title":
            ls.insert(s + 1, f"title {rng.choice(['System Design', 'Domain Model', 'Use Case View', 'Design v2'])}")
        elif op == "skin":
            opts = (["hide empty members", "skinparam classAttributeIconSize 0", "skinparam shadowing false"]
                    if dt == "CLASS" else ["skinparam actorStyle awesome", "skinparam packageStyle rectangle", "skinparam shadowing false"])
            ls.insert(s + 1, rng.choice(opts))
        elif op == "shuffle":
            rel = [i for i in range(s + 1, e) if REL_ARROW.search(ls[i]) and not ls[i].startswith(" ")
                   and not ls[i].strip().startswith(("class", "actor", "usecase", "'", "title", "skinparam", "hide"))]
            vals = [ls[i] for i in rel]
            rng.shuffle(vals)
            for i, v in zip(rel, vals):
                ls[i] = v
    return join(ls)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/clean.csv")
    ap.add_argument("--out", default="data/syntax_dataset.csv")
    ap.add_argument("--valid_augments", type=int, default=2, help="extra VALID variants per diagram")
    ap.add_argument("--per_operator", type=int, default=2, help="mutants per operator per diagram")
    ap.add_argument("--max_per_label", type=int, default=0, help="cap rows per label (0 = no cap)")
    ap.add_argument("--strict", action="store_true", help="keep a mutant only if PlantUML rejects it (every label)")
    ap.add_argument("--max_tokens", type=int, default=512,
                    help="drop samples longer than CodeBERT can read, so no defect is cut off by truncation")
    ap.add_argument("--tokenizer", default="microsoft/codebert-base")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    confirmed = (set(OPERATORS) - RULE_VERIFIED) if a.strict else PARSER_CONFIRMED

    clean = list(csv.DictReader(open(a.inp, encoding="utf-8")))
    samples, skipped = [], Counter()
    for r in clean:
        orig, dt = r["text"], r["diagram_type"]
        # label-quality rule 1: the source must really be a correct UML diagram
        rule_probs, lint_probs = check_rules(orig, dt), lint(orig)
        if rule_probs or lint_probs:
            skipped[f"source breaks UML rule ({(rule_probs or lint_probs)[0][0]})"] += 1
            continue
        base = {k: r[k] for k in ("diagram_id", "group", "diagram_type", "domain")}
        samples.append({**base, "label": "VALID", "mutated_line": -1, "text": orig})
        for _ in range(a.valid_augments):
            samples.append({**base, "label": "VALID", "mutated_line": -1, "text": normalize(a_valid(orig, dt, rng))})
        for label, op in OPERATORS.items():
            tries = a.per_operator * (4 if (label in confirmed or label in RULE_VERIFIED) else 1)
            for _ in range(tries):
                res = op(orig, dt, rng)
                if res is None:
                    continue
                txt, line = res
                txt = normalize(txt)
                if txt != orig:
                    samples.append({**base, "label": label, "mutated_line": line, "text": txt})

    # de-duplicate identical (text, label) pairs, then optionally balance
    uniq = {}
    for s in samples:
        uniq.setdefault((s["text"], s["label"]), s)
    samples = list(uniq.values())
    if a.max_per_label:
        rng.shuffle(samples)
        cnt, kept = Counter(), []
        for s in samples:
            if cnt[s["label"]] < a.max_per_label:
                kept.append(s); cnt[s["label"]] += 1
        samples = kept

    # label-quality rule 5: CodeBERT must be able to SEE the whole sample. A mutant
    # longer than 512 tokens would be truncated, and the defect could be cut away.
    count_tokens, how = get_token_counter(a.tokenizer)
    before = len(samples)
    lengths = [count_tokens(s["text"]) for s in samples]
    too_long = Counter(s["label"] for s, n in zip(samples, lengths) if n > a.max_tokens)
    samples = [s for s, n in zip(samples, lengths) if n <= a.max_tokens]
    print(f"token check ({how}): removed {before - len(samples)} samples longer than {a.max_tokens} tokens",
          dict(too_long) if too_long else "")

    print(f"clean diagrams used: {len(clean) - sum(skipped.values())} / {len(clean)}")
    print(f"running PlantUML on {len(samples)} samples ...")
    verdicts = check_texts([s["text"] for s in samples])
    rows, dropped, kept_per = [], Counter(), Counter()
    for i, (s, (st, ln, msg)) in enumerate(zip(samples, verdicts)):
        if s["label"] == "VALID" and st != "VALID":   # an augmentation broke the diagram -> discard
            dropped["VALID augmentation rejected by PlantUML"] += 1
            continue
        verified = True
        if s["label"] in confirmed and st != "ERROR":
            dropped[f"{s['label']} still legal PlantUML"] += 1
            verified = False
        elif s["label"] in RULE_VERIFIED and s["label"] not in {p[0] for p in check_rules(s["text"], s["diagram_type"])}:
            dropped[f"{s['label']} not confirmed by rule checker"] += 1
            verified = False
        if not verified:
            continue
        if s["label"] in confirmed or s["label"] in RULE_VERIFIED:
            key = (s["diagram_id"], s["label"])
            if kept_per[key] >= a.per_operator:
                continue
            kept_per[key] += 1
        rows.append({"sample_id": f"S{i:06d}", **s, "label_id": LABEL2ID[s["label"]],
                     "parser_status": st, "parser_line": ln, "parser_message": msg})

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    cols = ["sample_id", "diagram_id", "group", "diagram_type", "domain", "label", "label_id",
            "mutated_line", "parser_status", "parser_line", "parser_message", "text"]
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print("skipped source diagrams:", dict(skipped))
    print("dropped mutants:", dict(dropped))
    print(f"\n{'label':30s} {'rows':>6s} {'CLASS':>6s} {'UC':>6s} {'parser rejects':>15s}")
    by = Counter(r["label"] for r in rows)
    by_t = Counter((r["label"], r["diagram_type"]) for r in rows)
    rej = Counter(r["label"] for r in rows if r["parser_status"] == "ERROR")
    for lab in LABEL2ID:
        if by[lab]:
            print(f"{lab:30s} {by[lab]:6d} {by_t[(lab, 'CLASS')]:6d} {by_t[(lab, 'USE_CASE')]:6d} "
                  f"{rej[lab]:8d} ({100 * rej[lab] / by[lab]:5.1f}%)")
        else:
            print(f"{lab:30s} {0:6d}   <-- no samples for this label!")
    print(f"\nwrote {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    main()