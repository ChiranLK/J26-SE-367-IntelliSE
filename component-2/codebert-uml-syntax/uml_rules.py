import csv
import re
import sys
from collections import Counter, defaultdict

from uml_parser import ARROW, CLASS_DECL, END, REL, class_bodies, clean_name, display_name, endpoint_kind, kind_lookup, parse

RULE_LABELS = ["DUPLICATE_ELEMENT", "GENERALIZATION_CYCLE", "INVALID_USECASE_RELATIONSHIP"]


# ----------------------------------------------------------------------------- training-time rules
def check_rules(text: str, diagram_type: str = None):
    """Return a list of (label, line_no, message). Empty list = no rule broken."""
    elements, relations = parse(text)
    problems = []
    problems += _duplicates(elements)
    problems += _generalization_cycles(relations)
    if diagram_type == "USE_CASE" or any(e["kind"] in ("actor", "usecase") for e in elements):
        problems += _usecase_relationships(elements, relations)
    return problems


def _duplicates(elements):
    problems, seen = [], {}
    for e in elements:
        if e.get("inline"):
            continue        # (Use case) inside a relation is a reference, not a definition
        if e["kind"] == "class" and not e.get("has_body"):
            continue        # a bare 'class A' is a legal forward declaration of the same class
        key = (e["kind"], e["scope"] if e["kind"] == "class" else (), e["name"])
        if key in seen:
            problems.append(("DUPLICATE_ELEMENT", e["line"],
                             f"{e['kind']} '{e['name']}' is already defined on line {seen[key]}"))
        else:
            seen[key] = e["line"]
    return problems


def _generalization_cycles(relations):
    parents, first_line = defaultdict(set), {}
    for r in relations:
        if r["kind"] == "generalization":
            parents[r["child"]].add(r["parent"])
            first_line.setdefault((r["child"], r["parent"]), r["line"])

    problems, reported = [], set()
    for (child, parent), line in first_line.items():
        # walk up from the parent; reaching the child again means a cycle
        todo, visited = [parent], set()
        while todo:
            n = todo.pop()
            if n == child:
                pair = frozenset((child, parent))
                if pair not in reported:
                    problems.append(("GENERALIZATION_CYCLE", line,
                                     f"'{child}' and '{parent}' inherit from each other"))
                    reported.add(pair)
                break
            if n not in visited:
                visited.add(n)
                todo.extend(parents.get(n, ()))
    return problems


def _usecase_relationships(elements, relations):
    kinds = kind_lookup(elements)
    problems = []
    for r in relations:
        ka, kb = endpoint_kind(r["a"], kinds), endpoint_kind(r["b"], kinds)
        if ka is None or kb is None:
            continue        # unknown element, do not guess
        pair = {ka, kb}
        msg = None
        if r["kind"] == "include_extend" and "actor" in pair:
            msg = "<<include>>/<<extend>> may only connect two use cases"
        elif r["kind"] == "generalization" and pair == {"actor", "usecase"}:
            msg = "an actor cannot generalize a use case (or vice versa)"
        elif r["kind"] == "association" and ka == kb == "actor":
            msg = "two actors may not be associated (only generalization)"
        elif r["kind"] == "association" and ka == kb == "usecase":
            msg = "two use cases need <<include>>, <<extend>> or generalization, not a plain association"
        if msg:
            problems.append(("INVALID_USECASE_RELATIONSHIP", r["line"], msg))
    return problems


# ----------------------------------------------------------------------------- validator-only checks
def check_unconnected(text: str, diagram_type: str = "USE_CASE"):
    """Elements that take part in no relationship at all: actors and use cases in a
    use case diagram, classes in a class diagram.
    Returns (label, line, message, kind, ref)."""
    elements, relations = parse(text)
    linked = {clean_name(r["a"]) for r in relations} | {clean_name(r["b"]) for r in relations}
    wanted = ("class",) if diagram_type == "CLASS" else ("actor", "usecase")

    problems, seen = [], set()
    for e in elements:
        if e["kind"] not in wanted or e.get("inline") or (e["kind"], e["name"]) in seen:
            continue
        seen.add((e["kind"], e["name"]))
        if clean_name(e["ref"]) not in linked and e["name"] not in linked:
            problems.append(("UNCONNECTED_ELEMENT", e["line"],
                             f"{e['kind']} '{e['display']}' is not connected to anything", e["kind"], e["ref"]))
    return problems


ATTR = re.compile(r"^[+\-#~]?\s*(\w+)\s*:\s*([\w.]+(?:\s*<\s*\w+\s*>)?(?:\[\])?)\s*$")


def check_attribute_refs(text: str):
    """Class diagrams: an attribute typed with another class of the diagram
    ('customer : Customer', 'seats : List<Seat>') while the two classes have no
    relationship line. In UML that link should be drawn as an association.
    Returns (label, line, message, owner, attribute, target, many)."""
    elements, relations = parse(text)
    classes = {e["ref"].strip('"') for e in elements if e["kind"] == "class"}
    linked_pairs = {frozenset((clean_name(r["a"]), clean_name(r["b"]))) for r in relations}

    problems = []
    for owner, lines in class_bodies(text).items():
        for no, line in lines:
            m = ATTR.match(line)
            if not m:
                continue
            typ = m.group(2)
            inner = re.search(r"<\s*(\w+)\s*>", typ)       # List<Seat> -> Seat
            many = bool(inner) or typ.endswith("[]")
            target = inner.group(1) if inner else typ.rstrip("[]")
            if target in classes and target != owner and \
                    frozenset((clean_name(owner), clean_name(target))) not in linked_pairs:
                problems.append(("ATTRIBUTE_INSTEAD_OF_ASSOCIATION", no,
                                 f"'{line}' in {owner} refers to class {target}, but there is no association line",
                                 owner, line, target, many))
    return problems


def class_keywords(text: str):
    """name -> 'class', 'abstract', 'interface' or 'enum'."""
    kinds = {}
    for line in text.split("\n"):
        m = CLASS_DECL.match(line.strip())
        if m:
            kw = m.group("kw").lower()
            kw = "abstract" if kw.startswith("abstract") else kw
            kinds[clean_name(m.group("alias") or m.group("name"))] = kw
    return kinds


def check_generalization_direction(text: str):
    """Generalization arrows that point the wrong way, e.g. "Student <|-- Person"
    when Person is the abstract parent: an abstract class or an interface is
    drawn as the CHILD of a normal class.
    (A class with two parents is NOT flagged - real ModelSet diagrams use
    multiple inheritance on purpose, so that sign gave too many false alarms.)
    Returns (label, line, message)."""
    _, relations = parse(text)
    kinds = class_keywords(text)

    problems = []
    for r in relations:
        if r["kind"] != "generalization" or r["parent"] not in kinds or r["child"] not in kinds:
            continue
        if kinds[r["child"]] in ("abstract", "interface") and kinds[r["parent"]] == "class":
            # names as written in the diagram
            a, b = display_name(r["a"]), display_name(r["b"])
            parent, child = (a, b) if r["arrow"].startswith("<|") else (b, a)
            what = "an interface" if kinds[r["child"]] == "interface" else "abstract"
            problems.append(("REVERSED_GENERALIZATION", r["line"],
                             f"the generalization direction looks reversed: {child} is {what} "
                             f"but is drawn as the child of the normal class {parent}"))
    return problems


IS_A = re.compile(r"^\s*(is\s+an?|is\s+a\s+kind\s+of|is\s+a\s+type\s+of|kind\s+of|type\s+of|"
                  r"extends|inherits(\s+from)?|subclass(\s+of)?|specializ\w*|generaliz\w*)\s*$", re.I)

BARE_IS = re.compile(r"^\s*(is|are)\s*$", re.I)


def check_missing_generalization(text: str):
    """Inheritance drawn as an association labelled "is a" / "extends" / "kind of" ...
        e.g. Person "1" -- "0..*" Student : is a      -> Person <|-- Student
    (An abstract class with no subclass is NOT flagged: ModelSet has 11 such
    diagrams, mostly library classes or unfinished models, and Qwen would
    invent a subclass to "fix" it.)
    Returns (label, line, message)."""
    _, relations = parse(text)
    kinds = class_keywords(text)
    is_a = [r for r in relations if r["kind"] == "association" and IS_A.match(r["label"] or "")]
    # a bare "is" is too vague on its own ("Room -- Session : is"), so it only counts
    # when one end is abstract or an interface ("Person -- Member : is")
    for r in relations:
        if r["kind"] == "association" and BARE_IS.match(r["label"] or "") and \
                {kinds.get(clean_name(r["a"])), kinds.get(clean_name(r["b"]))} & {"abstract", "interface"}:
            is_a.append(r)

    # the parent is the abstract side; otherwise the class that shows up in
    # several "is a" lines (Person -- Student, Person -- Lecturer)
    count = Counter()
    for r in is_a:
        count[clean_name(r["a"])] += 1
        count[clean_name(r["b"])] += 1

    problems = []
    for r in is_a:
        a, b = display_name(r["a"]), display_name(r["b"])
        ka, kb = kinds.get(clean_name(a)), kinds.get(clean_name(b))
        if kb in ("abstract", "interface") and ka not in ("abstract", "interface"):
            parent, child = b, a
        elif ka in ("abstract", "interface") or count[clean_name(a)] >= count[clean_name(b)]:
            parent, child = a, b
        else:
            parent, child = b, a
        arrow = "<|.." if kinds.get(clean_name(parent)) == "interface" else "<|--"
        problems.append(("MISSING_GENERALIZATION", r["line"],
                         f"inheritance is written as an association; write it as \"{parent} {arrow} {child}\""))

    return sorted(problems, key=lambda p: p[1])


def check_enum_in_class(text: str):
    """'class Grade { enum { A, B, C } }' - an enum written inside a class.
    PlantUML draws it, but Grade is then a normal class. It must be 'enum Grade'.
    Returns (label, line, message)."""
    problems = []
    for owner, lines in class_bodies(text).items():
        for no, line in lines:
            m = re.match(r"^enum\s*\{?\s*([^}]*)\}?\s*$", line.strip(), re.I)
            if m:
                values = [v.strip() for v in re.split(r"[,\s]+", m.group(1)) if v.strip()]
                problems.append(("ENUM_WRITTEN_AS_CLASS", no,
                                 f"{owner} is a list of fixed values, so it must be declared as "
                                 f"\"enum {owner}\" with values {', '.join(values)}"))
    return problems


# "..> Course : uses" written inside a class, without the class name in front
ARROW_FIRST = re.compile(rf"^(?P<arrow>{ARROW})\s*(?P<b>{END})\s*(?::\s*(?P<label>.*))?$")


def check_relation_in_body(text: str):
    """A relationship line written INSIDE a class block:
        class Visit {
          VisitStatus "1" -- "0..*" Visit : has      <- PlantUML shows this as text
        }
    Returns (label, line, message)."""
    problems = []
    for owner, lines in class_bodies(text).items():
        for no, line in lines:
            # check "..> Course" first: REL would read the ".." as a class name
            m = ARROW_FIRST.match(line)
            if m and len(m.group("arrow")) >= 2:      # 2+ characters, so "- name : String" never matches
                moved = f"{owner} {line}"
            else:
                m = REL.match(line)
                if not m or len(m.group("arrow")) < 2 or not ("-" in m.group("arrow") or "." in m.group("arrow")):
                    continue
                moved = line
            problems.append(("RELATIONSHIP_INSIDE_CLASS", no,
                             f"a relationship is written inside class {owner}; write it after all the "
                             f"class blocks as \"{moved}\""))
    return problems


def check_realization(text: str):
    """A class that implements an interface must use the dashed arrow:
    "Printable <|.. Visit", not "Printable <|-- Visit".
    Returns (label, line, message)."""
    _, relations = parse(text)
    kinds = class_keywords(text)
    src_lines = text.split("\n")
    problems = []
    for r in relations:
        if r["kind"] != "generalization" or "." in r["arrow"]:
            continue
        if CLASS_DECL.match(src_lines[r["line"] - 1].strip()):
            continue    # "class Student implements Notifiable" - the keyword is fine
        if kinds.get(r["parent"]) == "interface" and kinds.get(r["child"]) in ("class", "abstract"):
            arrow = r["arrow"].replace("-", ".")
            fixed = f'{display_name(r["a"])} {arrow} {display_name(r["b"])}'
            problems.append(("INVALID_REALIZATION", r["line"],
                             f"a class implements an interface with a solid arrow; write it as \"{fixed}\""))
    return problems



def check_class_extras(text: str):
    """All validator-only class diagram checks in one call. A new class rule is
    added HERE only - uml_syntax_validator.py does not need to change."""
    return (check_generalization_direction(text) + check_missing_generalization(text)
            + check_enum_in_class(text) + check_relation_in_body(text) + check_realization(text))

# ----------------------------------------------------------------------------- self-test
def _selftest(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    per_type, empty, viol, examples = Counter(), Counter(), Counter(), defaultdict(list)
    for r in rows:
        dt = r.get("diagram_type", "")
        per_type[dt] += 1
        elements, _ = parse(r["text"])
        if not elements:
            empty[dt] += 1
        probs = check_rules(r["text"], dt)
        found = {p[0] for p in probs}
        for lab in found:
            viol[(dt, lab)] += 1
            if len(examples[lab]) < 2:
                msg = next(p[2] for p in probs if p[0] == lab)
                examples[lab].append((r.get("diagram_id", "?"), msg))
        if found:
            viol[(dt, "ANY")] += 1
        for lab, check in (("MISSING_GENERALIZATION", check_missing_generalization),
                           ("ENUM_WRITTEN_AS_CLASS", check_enum_in_class),
                           ("RELATIONSHIP_INSIDE_CLASS", check_relation_in_body),
                           ("INVALID_REALIZATION", check_realization)):
            found_extra = check(r["text"]) if dt == "CLASS" else []
            if found_extra:
                viol[(dt, lab)] += 1
                if len(examples[lab]) < 3:
                    examples[lab].append((r.get("diagram_id", "?"), found_extra[0][2]))
        if dt == "CLASS" and check_generalization_direction(r["text"]):
            viol[(dt, "REVERSED_GENERALIZATION")] += 1
            if len(examples["REVERSED_GENERALIZATION"]) < 3:
                examples["REVERSED_GENERALIZATION"].append(
                    (r.get("diagram_id", "?"), check_generalization_direction(r["text"])[0][2]))

    print("diagrams per type:", dict(per_type))
    print("diagrams where NO element was recognised (parser mismatch?):", dict(empty))
    for dt in per_type:
        print(f"\n{dt}: rule violations in clean data")
        for lab in RULE_LABELS + ["ANY", "REVERSED_GENERALIZATION", "MISSING_GENERALIZATION", "ENUM_WRITTEN_AS_CLASS",
                               "RELATIONSHIP_INSIDE_CLASS", "INVALID_REALIZATION"]:
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