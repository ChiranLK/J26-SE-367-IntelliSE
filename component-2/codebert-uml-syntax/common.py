"""Shared helpers: label set, text normalisation, PlantUML checking and a rule-based linter.

Every other script imports from here so that training and inference use exactly
the same normalisation and the same label ids.
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLANTUML_JAR = os.environ.get("PLANTUML_JAR", str(HERE / "tools" / "plantuml.jar"))
CHECKER_SRC = str(HERE / "tools" / "PumlChecker.java")

# ---------------------------------------------------------------------------
# Label set (index = class id used by CodeBERT). Do NOT reorder after training.
# The first 10 are syntax / notation errors. The last 3 are UML well-formedness
# rules (see uml_rules.py): PlantUML renders them, but UML does not allow them.
# ---------------------------------------------------------------------------
LABELS = [
    "VALID",
    "MISSING_STARTUML",
    "MISSING_ENDUML",
    "UNMATCHED_BRACE",
    "INVALID_RELATIONSHIP",
    "INVALID_CLASS_DECLARATION",
    "INVALID_MEMBER_SYNTAX",
    "INVALID_MULTIPLICITY",
    "INVALID_USECASE_DECLARATION",
    "UNSUPPORTED_TOKEN",
    # --- UML rule violations (new) ---
    "DUPLICATE_ELEMENT",
    "GENERALIZATION_CYCLE",
    "INVALID_USECASE_RELATIONSHIP",
]
LABEL2ID = {l: i for i, l in enumerate(LABELS)}
ID2LABEL = {i: l for l, i in LABEL2ID.items()}


# ---------------------------------------------------------------------------
# Normalisation (same at train time and inference time)
# ---------------------------------------------------------------------------
_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*$")


def strip_llm_wrapping(text: str) -> str:
    """Remove markdown fences / chatter OUTSIDE @startuml..@enduml.
    Use this on raw LLM output BEFORE validation. Anything inside the block is kept,
    so prose the LLM wrote *inside* the diagram is still caught as an error."""
    lines = text.replace("\r\n", "\n").split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip().lower().startswith("@startuml")), None)
    end = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip().lower().startswith("@enduml")), None)
    if start is not None and end is not None and end >= start:
        return "\n".join(lines[start:end + 1])
    # markers missing: only drop fence lines, keep everything else for the validator
    return "\n".join(l for l in lines if not _FENCE.match(l))


def normalize(text: str) -> str:
    """Canonical text fed to CodeBERT: unix newlines, no trailing spaces,
    no blank-line runs, 2-space indentation."""
    out, blank = [], False
    for line in text.replace("\r\n", "\n").replace("\t", "  ").split("\n"):
        line = line.rstrip()
        if not line.strip():
            if not blank and out:
                out.append("")
            blank = True
            continue
        blank = False
        indent = len(line) - len(line.lstrip(" "))
        out.append("  " * (indent // 2 if indent else 0) + line.strip())
    return "\n".join(out).strip() + "\n"


# ---------------------------------------------------------------------------
# Tokenisation with head+tail truncation (same at train and inference time)
# ---------------------------------------------------------------------------
def encode_head_tail(tokenizer, text: str, max_len: int = 512):
    """CodeBERT accepts max 512 tokens. Plain truncation cuts the END of the
    diagram, which would hide '@enduml' and trailing relationships. Instead keep
    the first and the last tokens. Returns a dict with input_ids/attention_mask."""
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    room = max_len - 2  # <s> ... </s>
    if len(ids) > room:
        head = room // 2
        ids = ids[:head] + ids[-(room - head):]
    ids = [tokenizer.cls_token_id] + ids + [tokenizer.sep_token_id]
    return {"input_ids": ids, "attention_mask": [1] * len(ids)}


# ---------------------------------------------------------------------------
# PlantUML checking (one JVM for many files -> ~150 diagrams/second)
# ---------------------------------------------------------------------------
def check_files(paths):
    """Return {path: (status, line, message)} using tools/PumlChecker.java.
    status is 'VALID' or 'ERROR'."""
    if not paths:
        return {}
    proc = subprocess.run(
        ["java", "-cp", PLANTUML_JAR, CHECKER_SRC],
        input="\n".join(str(p) for p in paths) + "\n",
        capture_output=True, text=True, check=False,
    )
    res = {}
    for row in proc.stdout.splitlines():
        parts = row.split("\t")
        if len(parts) >= 3:
            res[parts[0]] = (parts[1], int(parts[2]), parts[3] if len(parts) > 3 else "")
    if not res:
        raise RuntimeError("PlantUML checker produced no output. stderr:\n" + proc.stderr[-2000:])
    return res


def check_texts(texts):
    """Check a list of PlantUML strings. Returns list of (status, line, message)."""
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for i, t in enumerate(texts):
            p = os.path.join(d, f"{i}.puml")
            Path(p).write_text(t, encoding="utf-8")
            paths.append(p)
        res = check_files(paths)
        return [res.get(p, ("ERROR", -1, "checker failed")) for p in paths]


class PersistentChecker:
    """Keeps ONE PlantUML JVM running for the FastAPI/LangGraph service, so each
    check costs milliseconds instead of ~1 s of JVM start-up."""

    def __init__(self, jar=PLANTUML_JAR):
        self.proc = subprocess.Popen(["java", "-cp", jar, CHECKER_SRC], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.tmp = tempfile.mkdtemp(prefix="puml_")
        self.n = 0

    def check(self, text: str):
        self.n += 1
        p = os.path.join(self.tmp, f"{self.n}.puml")
        Path(p).write_text(text, encoding="utf-8")
        self.proc.stdin.write(p + "\n")
        self.proc.stdin.flush()
        parts = self.proc.stdout.readline().rstrip("\n").split("\t")
        os.remove(p)
        if len(parts) < 3:
            return ("ERROR", -1, "PlantUML checker not responding")
        return (parts[1], int(parts[2]), parts[3] if len(parts) > 3 else "")

    def close(self):
        self.proc.kill()


# ---------------------------------------------------------------------------
# Rule-based linter (baseline + extra deterministic safety net)
# ---------------------------------------------------------------------------
def lint(text: str):
    """Cheap structural checks PlantUML itself does NOT enforce.
    Returns list of (rule, line_no) problems; empty list = no problems."""
    problems = []
    lines = text.split("\n")
    stripped = [l.strip() for l in lines]
    if not any(s.lower().startswith("@startuml") for s in stripped):
        problems.append(("MISSING_STARTUML", 1))
    if not any(s.lower().startswith("@enduml") for s in stripped):
        problems.append(("MISSING_ENDUML", len(lines)))
    depth = 0
    for i, s in enumerate(stripped, 1):
        if s.startswith("'"):
            continue
        depth += s.count("{") - s.count("}")
        if depth < 0:
            problems.append(("UNMATCHED_BRACE", i))
            depth = 0
        if s.count("(") != s.count(")"):
            problems.append(("UNBALANCED_PARENTHESIS", i))
        if s.count('"') % 2:
            problems.append(("UNBALANCED_QUOTE", i))
    if depth > 0:
        problems.append(("UNMATCHED_BRACE", len(lines)))
    return problems