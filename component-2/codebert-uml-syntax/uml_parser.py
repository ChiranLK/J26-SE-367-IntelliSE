import re

# An endpoint can be a plain name, "Quoted Name", (Use case) or :Actor:
END = r'(?:"[^"]+"|\([^)]+\)|:[^:\s][^:]*:|[\w.$]+)'
# Any PlantUML arrow: heads, dashes or dots, optional direction hint ([#red], left, up ...)
ARROW = r'(?:<\|?|\*|o|#|x|\+|\^|\})?\|?(?:-+|\.+)(?:\[[^\]]*\]|left|right|up|down|le|ri|do|l|r|u|d)?[-.]*\|?(?:>|\*|o|#|x|\+|\^|\{)?'
REL = re.compile(rf'^\s*(?P<a>{END})\s*(?:"[^"]*"\s*)?(?P<arrow>{ARROW})\s*(?:"[^"]*"\s*)?(?P<b>{END})\s*(?::\s*(?P<label>.*))?$')

CLASS_DECL = re.compile(r'^\s*(?P<kw>abstract\s+class|abstract|class|interface|enum|annotation|entity)\s+'
                        r'(?P<name>"[^"]+"|[\w.$]+)(?:\s+as\s+(?P<alias>[\w.$]+))?(?P<rest>.*)$', re.I)
UC_KW_DECL = re.compile(r'^\s*(?P<kw>actor|usecase)\s+(?P<name>"[^"]+"|\([^)]+\)|:[^:]+:|[\w.$]+)'
                        r'(?:\s+as\s+(?P<alias>"[^"]+"|\([^)]+\)|[\w.$]+))?', re.I)
UC_INLINE = re.compile(r'^\s*(?P<name>\([^)]+\)|:[^:]+:)(?:\s+as\s+(?P<alias>[\w.$]+))?\s*$')
SCOPE = re.compile(r'^\s*(package|namespace|rectangle|frame|folder|node|component)\b\s*(?P<name>"[^"]+"|[\w.$]+)?', re.I)
INCLUDE_EXTEND = re.compile(r'\b(include|extend)s?\b', re.I)

# lines that never declare anything
SKIP_PREFIXES = ("skinparam", "title", "hide", "show", "left to right", "top to bottom", "note")


def clean_name(tok: str) -> str:
    """Name used for comparing: no quotes / brackets / colons, lower case, single spaces."""
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] + tok[-1] in ('""', "()", "::"):
        tok = tok[1:-1]
    return " ".join(tok.split()).lower()


def display_name(tok: str) -> str:
    """Same as clean_name but keeps the letter case (used when we write new lines)."""
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] + tok[-1] in ('""', "()", "::"):
        tok = tok[1:-1]
    return " ".join(tok.split())


def token_kind(tok: str):
    """(Use case) and :Actor: tell their kind by themselves; plain names do not."""
    tok = tok.strip()
    if tok.startswith("(") and tok.endswith(")"):
        return "usecase"
    if tok.startswith(":") and tok.endswith(":") and len(tok) > 2:
        return "actor"
    return None


def parse(text: str):
    """Return (elements, relations).

    elements : dicts with kind ('class' / 'actor' / 'usecase'), name, display,
               ref (how other lines refer to it), scope, line
    relations: dicts with a, b, arrow, label, line and kind
               ('generalization' / 'include_extend' / 'association')
    """
    elements, relations = [], []
    stack = []          # open { } blocks; package names create a scope, other blocks are None

    for no, raw in enumerate(text.split("\n"), 1):
        s = raw.strip()
        if not s or s.startswith("'") or s.startswith("@") or s.lower().startswith(SKIP_PREFIXES):
            continue
        if s == "}":
            if stack:
                stack.pop()
            continue
        scope = tuple(x for x in stack if x)

        m = CLASS_DECL.match(s)
        if m:
            ref = m.group("alias") or m.group("name")
            elements.append({"kind": "class", "name": clean_name(m.group("name")),
                             "display": display_name(m.group("name")), "ref": ref,
                             "scope": scope, "line": no, "has_body": s.endswith("{")})
            # 'class B extends A implements I' is also a generalization
            rest = m.group("rest") or ""
            for kw in ("extends", "implements"):
                km = re.search(rf'\b{kw}\s+([\w.$,\s]+?)(?:\{{|$|\bimplements\b|\bextends\b)', rest)
                if km:
                    for parent in [p.strip() for p in km.group(1).split(",") if p.strip()]:
                        relations.append({"a": parent, "b": ref, "arrow": "<|--", "label": "",
                                          "kind": "generalization", "line": no,
                                          "parent": clean_name(parent), "child": clean_name(ref)})
            if s.endswith("{"):
                stack.append(None)
            continue

        m = UC_KW_DECL.match(s)
        if m:
            name_tok, alias = m.group("name"), m.group("alias")
            # 'actor A1 as "Customer"' writes the display name second
            if alias and alias[0] in '"(' and name_tok[0] not in '"(:':
                name_tok, alias = alias, name_tok
            elements.append({"kind": m.group("kw").lower(), "name": clean_name(name_tok),
                             "display": display_name(name_tok), "ref": alias or name_tok,
                             "scope": scope, "line": no})
            if s.endswith("{"):
                stack.append(None)
            continue

        m = UC_INLINE.match(s)
        if m:
            tok = m.group("name")
            elements.append({"kind": token_kind(tok), "name": clean_name(tok), "display": display_name(tok),
                             "ref": m.group("alias") or tok, "scope": scope, "line": no})
            continue

        m = SCOPE.match(s)
        if m and s.endswith("{"):
            # only package / namespace change the naming scope; rectangle etc. are just boxes
            is_namespace = m.group(1).lower() in ("package", "namespace")
            stack.append(clean_name(m.group("name") or "") if is_namespace else None)
            continue

        m = REL.match(s)
        if m and ("-" in m.group("arrow") or "." in m.group("arrow")):
            a, b, arrow, label = m.group("a"), m.group("b"), m.group("arrow"), (m.group("label") or "")
            if arrow.startswith("<|"):
                kind, parent, child = "generalization", clean_name(a), clean_name(b)
            elif arrow.endswith("|>"):
                kind, parent, child = "generalization", clean_name(b), clean_name(a)
            else:
                kind = "include_extend" if INCLUDE_EXTEND.search(label) else "association"
                parent = child = None
            relations.append({"a": a, "b": b, "arrow": arrow, "label": label, "kind": kind,
                              "line": no, "parent": parent, "child": child})
            # (Use case) and :Actor: written straight into a relation still count as elements
            for tok in (a, b):
                if token_kind(tok):
                    elements.append({"kind": token_kind(tok), "name": clean_name(tok), "display": display_name(tok),
                                     "ref": tok, "scope": scope, "line": no, "inline": True})
            continue

        if s.endswith("{"):
            stack.append(None)

    return elements, relations


def kind_lookup(elements):
    """name or alias (lower case) -> element kind"""
    kinds = {}
    for e in elements:
        kinds.setdefault(e["name"], e["kind"])
        kinds.setdefault(clean_name(e["ref"]), e["kind"])
    return kinds


def endpoint_kind(tok, kinds):
    """'actor' / 'usecase' / 'class' / None for one end of a relation"""
    return token_kind(tok) or kinds.get(clean_name(tok))


def class_bodies(text):
    """{class name: [(line_no, line), ...]} for every class written with { }"""
    bodies, current = {}, None
    for no, raw in enumerate(text.split("\n"), 1):
        s = raw.strip()
        m = CLASS_DECL.match(s)
        if m and s.endswith("{"):
            current = (m.group("alias") or m.group("name")).strip('"')
            bodies[current] = []
            continue
        if current is not None:
            if s == "}":
                current = None
            else:
                bodies[current].append((no, s))
    return bodies