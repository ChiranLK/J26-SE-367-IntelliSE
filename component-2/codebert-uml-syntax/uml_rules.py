"""UML well-formedness rules for Class and Use Case diagrams written in PlantUML.

PlantUML happily renders all of the problems below, but the UML standard does
not allow them. We use these checks in step 4 to keep the labels clean:
  1. a diagram is only used as VALID if it breaks NONE of these rules, and
  2. a rule-based mutant is only kept if the rule really detects the violation.

Rules (label -> meaning)
  DUPLICATE_ELEMENT            the same class is defined twice WITH a body ({ ... }), or the
                               same actor / use case name is declared twice (two shapes)
  GENERALIZATION_CYCLE         A inherits from B and B (directly or indirectly) from A
  INVALID_USECASE_RELATIONSHIP an actor in <<include>>/<<extend>>, an association
                               between two actors, a plain association between two
                               use cases, or generalization between an actor and a
                               use case

Self-test on your real data (run after step 3):
  python uml_rules.py data/clean.csv
"""
import csv
import re
import sys
from collections import Counter, defaultdict

# ----------------------------------------------------------------------------- regexes
END = r'(?:"[^"]+"|\([^)]+\)|:[^:\s][^:]*:|[\w.$]+)'          # Name, "Name", (Use case), :Actor:
ARROW = r'(?:<\|?|\*|o|#|x|\+|\^|\})?\|?(?:-+|\.+)(?:\[[^\]]*\]|left|right|up|down|le|ri|do|l|r|u|d)?[-.]*\|?(?:>|\*|o|#|x|\+|\^|\{)?'
REL = re.compile(rf'^\s*(?P<a>{END})\s*(?:"[^"]*"\s*)?(?P<arrow>{ARROW})\s*(?:"[^"]*"\s*)?(?P<b>{END})\s*(?::\s*(?P<label>.*))?$')

CLASS_DECL = re.compile(r'^\s*(?P<kw>abstract\s+class|abstract|class|interface|enum|annotation|entity)\s+'
                        r'(?P<name>"[^"]+"|[\w.$]+)(?:\s+as\s+(?P<alias>[\w.$]+))?(?P<rest>.*)$', re.I)
UC_KW_DECL = re.compile(r'^\s*(?P<kw>actor|usecase)\s+(?P<name>"[^"]+"|\([^)]+\)|:[^:]+:|[\w.$]+)'
                        r'(?:\s+as\s+(?P<alias>"[^"]+"|\([^)]+\)|[\w.$]+))?', re.I)
UC_INLINE = re.compile(r'^\s*(?P<name>\([^)]+\)|:[^:]+:)(?:\s+as\s+(?P<alias>[\w.$]+))?\s*$')
SCOPE = re.compile(r'^\s*(package|namespace|rectangle|frame|folder|node|component)\b\s*(?P<name>"[^"]+"|[\w.$]+)?', re.I)
INCLUDE_EXTEND = re.compile(r'\b(include|extend)s?\b', re.I)

RULE_LABELS = ["DUPLICATE_ELEMENT", "GENERALIZATION_CYCLE", "INVALID_USECASE_RELATIONSHIP"]


def clean_name(tok: str) -> str:
    tok = tok.strip()
    if len(tok) >= 2 and ((tok[0] == '"' and tok[-1] == '"') or (tok[0] == '(' and tok[-1] == ')')
                          or (tok[0] == ':' and tok[-1] == ':')):
        tok = tok[1:-1]
    return " ".join(tok.split()).lower()


def display_name(tok: str) -> str:
    """Like clean_name but keeps the original letter case (used to write new lines)."""
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] + tok[-1] in ('""', "()", "::"):
        tok = tok[1:-1]
    return " ".join(tok.split())


def token_kind(tok: str):
    tok = tok.strip()
    if tok.startswith("(") and tok.endswith(")"):
        return "usecase"
    if tok.startswith(":") and tok.endswith(":") and len(tok) > 2:
        return "actor"
    return None


# ----------------------------------------------------------------------------- parser
def parse(text: str):
    """Return (elements, relations).
    elements : list of dicts {kind, name, ref, scope, line}
               kind is 'class' / 'actor' / 'usecase'; ref = how other lines refer to it
    relations: list of dicts {a, b, arrow, label, kind, line}
               kind is 'generalization' / 'include_extend' / 'association'
    """
    elements, relations = [], []
    stack = []                                      # scope stack (package names or None)
    for no, raw in enumerate(text.split("\n"), 1):
        s = raw.strip()
        if not s or s.startswith("'") or s.startswith("@") or s.lower().startswith(("skinparam", "title", "hide", "show", "left to right", "top to bottom", "note")):
            continue
        if s == "}":
            if stack:
                stack.pop()
            continue
        scope = tuple(x for x in stack if x)

        m = CLASS_DECL.match(s)
        if m:
            name = clean_name(m.group("name"))
            ref = m.group("alias") or m.group("name")
            elements.append({"kind": "class", "name": name, "display": display_name(m.group("name")), "ref": ref,
                             "scope": scope, "line": no, "has_body": s.endswith("{")})
            rest = m.group("rest") or ""
            for kw in ("extends", "implements"):
                km = re.search(rf'\b{kw}\s+([\w.$,\s]+?)(?:\{{|$|\bimplements\b|\bextends\b)', rest)
                if km:
                    for parent in [p.strip() for p in km.group(1).split(",") if p.strip()]:
                        relations.append({"a": parent, "b": ref, "arrow": "<|--", "label": "",
                                          "kind": "generalization", "line": no, "parent": clean_name(parent),
                                          "child": clean_name(ref)})
            if s.endswith("{"):
                stack.append(None)
            continue

        m = UC_KW_DECL.match(s)
        if m:
            kind = m.group("kw").lower()
            name_tok, alias = m.group("name"), m.group("alias")
            # 'actor A1 as "Customer"' style: the quoted part is the display name
            if alias and alias[0] in '"(' and name_tok[0] not in '"(:':
                name_tok, alias = alias, name_tok
            elements.append({"kind": kind, "name": clean_name(name_tok), "display": display_name(name_tok), "ref": alias or name_tok,
                             "scope": scope, "line": no})
            if s.endswith("{"):
                stack.append(None)
            continue

        m = UC_INLINE.match(s)
        if m:
            tok = m.group("name")
            elements.append({"kind": token_kind(tok), "name": clean_name(tok), "display": display_name(tok), "ref": m.group("alias") or tok,
                             "scope": scope, "line": no})
            continue

        m = SCOPE.match(s)
        if m and s.endswith("{"):
            # only package/namespace create a naming scope; rectangle etc. are just boxes
            is_ns = m.group(1).lower() in ("package", "namespace")
            stack.append(clean_name(m.group("name") or "") if is_ns else None)
            continue

        m = REL.match(s)
        if m and ("-" in m.group("arrow") or "." in m.group("arrow")):
            a, b, arrow, label = m.group("a"), m.group("b"), m.group("arrow"), (m.group("label") or "")
            if arrow.startswith("<|"):
                kind, parent, child = "generalization", clean_name(a), clean_name(b)
            elif arrow.endswith("|>"):
                kind, parent, child = "generalization", clean_name(b), clean_name(a)
            else:
                kind, parent, child = ("include_extend" if INCLUDE_EXTEND.search(label) else "association"), None, None
            relations.append({"a": a, "b": b, "arrow": arrow, "label": label, "kind": kind, "line": no,
                              "parent": parent, "child": child})
            # inline (Use case) / :Actor: endpoints also count as elements
            for tok in (a, b):
                if token_kind(tok):
                    elements.append({"kind": token_kind(tok), "name": clean_name(tok), "display": display_name(tok), "ref": tok,
                                     "scope": scope, "line": no, "inline": True})
            continue

        if s.endswith("{"):
            stack.append(None)
    return elements, relations


def endpoint_kind(tok, kinds):
    """'actor' / 'usecase' / 'class' / None for a relation endpoint"""
    return token_kind(tok) or kinds.get(clean_name(tok))


def _lookup(elements):
    """map every name and alias (lower-case) -> element kind"""
    kinds = {}
    for e in elements:
        kinds.setdefault(e["name"], e["kind"])
        kinds.setdefault(clean_name(e["ref"]), e["kind"])
    return kinds


# ----------------------------------------------------------------------------- rules
def check_rules(text: str, diagram_type: str = None):
    """Return a list of (label, line_no, message). Empty list = follows all rules."""
    elements, relations = parse(text)
    problems = []

    # DUPLICATE_ELEMENT: two *declarations* with the same kind + name in the same scope
    seen = {}
    for e in elements:
        if e.get("inline"):
            continue                                # (Use case) used inside a relation is a reference, not a definition
        if e["kind"] == "class" and not e.get("has_body"):
            continue                                # 'class A' without a body is a legal forward declaration in
                                                    # PlantUML (it renders the same class), so it is not a duplicate
        key = (e["kind"], e["scope"] if e["kind"] == "class" else (), e["name"])
        if key in seen:
            problems.append(("DUPLICATE_ELEMENT", e["line"],
                             f"{e['kind']} '{e['name']}' is already defined on line {seen[key]}"))
        else:
            seen[key] = e["line"]

    # GENERALIZATION_CYCLE: follow child -> parent links
    parents = defaultdict(set)
    gen_lines = {}
    for r in relations:
        if r["kind"] == "generalization":
            parents[r["child"]].add(r["parent"])
            gen_lines.setdefault((r["child"], r["parent"]), r["line"])
    reported = set()
    for (child, parent), line in gen_lines.items():
        todo, visited = [parent], set()
        while todo:
            n = todo.pop()
            if n == child:
                cyc = frozenset((child, parent))
                if cyc not in reported:
                    problems.append(("GENERALIZATION_CYCLE", line, f"'{child}' and '{parent}' inherit from each other"))
                    reported.add(cyc)
                break
            if n not in visited:
                visited.add(n)
                todo.extend(parents.get(n, ()))

    # INVALID_USECASE_RELATIONSHIP (only meaningful when actors / use cases exist)
    kinds = _lookup(elements)
    is_uc = diagram_type == "USE_CASE" or any(e["kind"] in ("actor", "usecase") for e in elements)
    if is_uc:
        for r in relations:
            ka, kb = endpoint_kind(r["a"], kinds), endpoint_kind(r["b"], kinds)
            if ka is None or kb is None:
                continue                            # unknown element -> do not guess
            pair = {ka, kb}
            if r["kind"] == "include_extend" and "actor" in pair:
                problems.append(("INVALID_USECASE_RELATIONSHIP", r["line"], "<<include>>/<<extend>> may only connect two use cases"))
            elif r["kind"] == "generalization" and pair == {"actor", "usecase"}:
                problems.append(("INVALID_USECASE_RELATIONSHIP", r["line"], "an actor cannot generalize a use case (or vice versa)"))
            elif r["kind"] == "association" and ka == kb == "actor":
                problems.append(("INVALID_USECASE_RELATIONSHIP", r["line"], "two actors may not be associated (only generalization)"))
            elif r["kind"] == "association" and ka == kb == "usecase":
                problems.append(("INVALID_USECASE_RELATIONSHIP", r["line"], "two use cases need <<include>>, <<extend>> or generalization, not a plain association"))
    return problems


# ----------------------------------------------------------------------------- self-test
def _selftest(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    per_type, empty, viol, examples = Counter(), Counter(), Counter(), defaultdict(list)
    for r in rows:
        dt = r.get("diagram_type", "")
        per_type[dt] += 1
        els, rels = parse(r["text"])
        if not els:
            empty[dt] += 1
        probs = check_rules(r["text"], dt)
        found = {p[0] for p in probs}
        for lab in found:
            viol[(dt, lab)] += 1
            if len(examples[lab]) < 2:
                msg = next(p[2] for p in probs if p[0] == lab)          # message of THIS rule
                examples[lab].append((r.get("diagram_id", "?"), msg))
        if found:
            viol[(dt, "ANY")] += 1
    print("diagrams per type:", dict(per_type))
    print("diagrams where NO element was recognised (parser mismatch?):", dict(empty))
    for dt in per_type:
        print(f"\n{dt}: rule violations in clean data")
        for lab in RULE_LABELS + ["ANY"]:
            n = viol[(dt, lab)]
            print(f"  {lab:30s} {n:6d}  ({100 * n / max(per_type[dt], 1):5.1f}%)")
    for lab, ex in examples.items():
        print(f"\nexamples for {lab}:")
        for did, msg in ex:
            print(f"  {did}: {msg}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        _selftest(sys.argv[1])