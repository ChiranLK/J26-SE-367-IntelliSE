"""Texts the validator sends back to the LLM.

HINTS          - one short explanation for each error type
ALLOWED_CHANGE - what the LLM is allowed to change when it fixes that error
suggest_fix()  - a concrete "write X instead of Y" for one UML rule problem
"""
import re

from uml_parser import REL, clean_name, parse

HINTS = {
    # --- syntax / notation errors
    "MISSING_STARTUML": "The diagram must start with a line '@startuml'.",
    "MISSING_ENDUML": "The diagram must end with a line '@enduml'.",
    "UNMATCHED_BRACE": "A class/rectangle block has an unmatched '{' or '}'. Every opening brace needs exactly one closing brace.",
    "INVALID_RELATIONSHIP": "A relationship arrow is not valid PlantUML. Use --, -->, ..>, <|--, <|.., *-- or o--.",
    "INVALID_CLASS_DECLARATION": "A class/interface/enum declaration is malformed (keyword spelling or missing name).",
    "INVALID_MEMBER_SYNTAX": "An attribute or method line is malformed (unbalanced parentheses or a broken ':' type part).",
    "INVALID_MULTIPLICITY": "A multiplicity label is malformed. Write it in double quotes, e.g. \"1\" or \"0..*\".",
    "INVALID_USECASE_DECLARATION": "An actor/usecase declaration is malformed (keyword spelling or unclosed quote).",
    "UNSUPPORTED_TOKEN": "The diagram contains text that is not PlantUML (explanations, markdown fences or stray symbols). Remove it.",
    # --- UML rule violations
    "DUPLICATE_ELEMENT": ("The same class / actor / use case is defined more than once. Keep ONE definition "
                          "(merge its attributes and methods) and delete the other definition."),
    "GENERALIZATION_CYCLE": ("Two elements inherit from each other (a generalization cycle). UML does not allow this. "
                             "Keep the inheritance direction that matches the requirements and delete the reverse one."),
    "INVALID_USECASE_RELATIONSHIP": ("A use-case relationship breaks UML rules: <<include>>/<<extend>> may only connect two "
                                     "use cases; actors connect to use cases with a plain association (-->); two actors may "
                                     "only be linked by generalization (<|--); two use cases need <<include>>, <<extend>> "
                                     "or generalization, not a plain association."),
    # --- rule-only findings (no CodeBERT label of their own)
    "UNCONNECTED_ELEMENT": ("Every actor, use case and class must take part in at least one relationship. "
                            "Connect each unconnected element below."),
    "ATTRIBUTE_INSTEAD_OF_ASSOCIATION": ("A class refers to another class only through an attribute. In UML this "
                                         "link must be drawn as an association line between the two classes."),
    "REVERSED_GENERALIZATION": ("A generalization arrow points the wrong way. In \"A <|-- B\" the class on the "
                                "LEFT (A) is the parent and B is the child. Abstract classes and interfaces are "
                                "parents, not children."),
    "MISSING_GENERALIZATION": ("Inheritance must be drawn with a generalization arrow \"Parent <|-- Child\", "
                               "not with an association line labelled \"is a\"."),
    "ENUM_WRITTEN_AS_CLASS": ("A list of fixed values must be declared as an enum (\"enum Name { ... }\"), "
                              "not as a class with an enum inside it."),
    "UNBALANCED_PARENTHESIS": "A line has an unbalanced '(' or ')'.",
    "UNBALANCED_QUOTE": "A line has an unclosed double quote '\"'.",
}

# What the LLM is ALLOWED to change for each error type. The default rule is
# "change nothing structural", but some fixes need to delete or change an element.
ALLOWED_CHANGE = {
    "DUPLICATE_ELEMENT": "You may delete the duplicate definition (move its members into the remaining one).",
    "GENERALIZATION_CYCLE": "You may delete ONE of the two opposite generalization lines.",
    "INVALID_USECASE_RELATIONSHIP": "You may change or delete ONLY the relationship line(s) named in the feedback.",
    "UNSUPPORTED_TOKEN": "You may delete the lines that are not PlantUML.",
    "UNCONNECTED_ELEMENT": "You may ADD one relationship line for each unconnected actor, use case or class.",
    "REVERSED_GENERALIZATION": "You may reverse ONLY the generalization line(s) named in the feedback.",
    "MISSING_GENERALIZATION": ("You may replace the association lines named in the feedback with "
                               "generalization lines."),
    "ENUM_WRITTEN_AS_CLASS": "You may rewrite the class named in the feedback as an enum.",
    "ATTRIBUTE_INSTEAD_OF_ASSOCIATION": ("You may REMOVE the attributes named in the feedback and ADD the "
                                         "association lines it suggests."),
}


STEREOTYPE = re.compile(r"\s*:\s*<<\s*(include|extend)s?\s*>>.*$", re.I)


def suggest_fix(why, line):
    """A concrete instruction for one UML rule violation. Small models fix
    'write X instead of Y' far more reliably than 'X is wrong'."""
    line = line.strip()
    if "may only connect two use cases" in why:
        fixed = STEREOTYPE.sub("", line).replace("..>", "-->")
        return f'Replace "{line}" with "{fixed}".'
    if "two use cases need" in why:
        return (f'Delete "{line}". If one use case always uses the other, write it as '
                f'"A ..> B : <<include>>" instead.')
    if "two actors" in why:
        # deleting the line can leave an actor with no link at all, so offer the UML way too
        m = re.match(r"\s*(\S+)\s+\S+\s+(\S+)", line)
        if m:
            a, b = m.groups()
            return (f'If {b} is a special kind of {a}, write "{a} <|-- {b}". Otherwise delete "{line}" '
                    f'and connect {b} to the use cases it performs.')
        return f'Delete "{line}".'
    if "direction looks reversed" in why:
        # swap the two ends and keep the arrow: "Student <|-- Person" -> "Person <|-- Student"
        m = REL.match(line)
        if m:
            return f'Replace "{line}" with "{m.group("b")} {m.group("arrow")} {m.group("a")}".'
        return f'Reverse "{line}".'
    if "inheritance is written as an association" in why:
        new_line = re.search(r'write it as "(.+)"', why).group(1)
        return f'Replace "{line}" with "{new_line}".'
    if "must be declared as" in why:
        m = re.search(r'"enum (\S+)" with values (.+)$', why)
        name, values = m.group(1), [v.strip() for v in m.group(2).split(",")]
        block = "\n".join([f"enum {name} {{"] + [f"  {v}" for v in values] + ["}"])
        return f"Replace the whole class {name} block with:\n{block}"
    if "generalize a use case" in why:
        return f'Delete "{line}".'
    return ""


def block_end(src_lines, start):
    """Index of the line that closes the { } block opened on src_lines[start]."""
    if not src_lines[start].rstrip().endswith("{"):
        return start
    depth = 0
    for i in range(start, len(src_lines)):
        depth += src_lines[i].count("{") - src_lines[i].count("}")
        if depth <= 0:
            return i
    return len(src_lines) - 1


def merge_duplicate_fix(text, first_no, dup_no):
    """For a class written twice, give the LLM the ONE merged block to write.
    'Merge the two definitions' alone did not work: Qwen kept both blocks
    for three rounds. first_no and dup_no are 1-based line numbers."""
    src_lines = text.split("\n")
    a, b = first_no - 1, dup_no - 1
    a_end, b_end = block_end(src_lines, a), block_end(src_lines, b)
    if a_end == a and b_end == b:
        # actor / use case / class without a body: just delete the second line
        return f'Delete line {dup_no}: "{src_lines[b].strip()}".'

    header = src_lines[a].strip().rstrip("{").strip()
    members = []
    for i in list(range(a + 1, a_end)) + list(range(b + 1, b_end)):
        m = src_lines[i].strip()
        if m and m not in members:
            members.append(m)
    merged = "\n".join([header + " {"] + ["  " + m for m in members] + ["}"])

    where = f"lines {dup_no}-{b_end + 1}" if b_end > b else f"line {dup_no}"
    fix = (f'Delete {where} (the second "{src_lines[b].strip().rstrip("{").strip()}" block). '
           f"Then write the class ONCE, at line {first_no}, exactly like this:\n{merged}")

    # 'class B implements A {' also says B is a child of A - keep that link as a line
    m = re.search(r"\b(extends|implements)\s+([\w.$,\s]+?)\s*(?:\{|$)", src_lines[b])
    if m:
        child = header.split()[-1]
        # (the parser also reads the 'implements' on this line as a relation, so skip it)
        gens = {(r["parent"], r["child"]) for r in parse(text)[1]
                if r["kind"] == "generalization" and r["line"] != dup_no}
        arrow = "<|.." if m.group(1) == "implements" else "<|--"
        missing = [p.strip() for p in m.group(2).split(",")
                   if p.strip() and (clean_name(p), clean_name(child)) not in gens]
        if missing:
            fix += "\nAlso add: " + ", ".join(f'"{p} {arrow} {child}"' for p in missing)
    return fix