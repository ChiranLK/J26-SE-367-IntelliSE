"""Static acceptance checks for the model-written behaviour domain module.

Order: conservative lexical safety policy (shared with the CRUD/Task paths),
then the skeleton interface (every class, base, enum and method signature,
checked inside its own class body), then leftover TODO markers, then a
parse-only ``node --check``. Nothing is executed. Findings are static,
model-text-free labels so they can be fed back to the model and logged.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from intelise_c3.generation.behaviour_spec import TODO_MARKER, BehaviourSpec
from intelise_c3.generation.js_safety import POLICY_VERSION, inspect_javascript_safety

BEHAVIOUR_VALIDATOR_VERSION = "C3_BEHAVIOUR_VALIDATOR_V0"


@dataclass(frozen=True)
class BehaviourFinding:
    code: str
    message: str


@dataclass(frozen=True)
class BehaviourValidation:
    findings: tuple[BehaviourFinding, ...]
    syntax_check: str  # PASSED | FAILED | SKIPPED_NODE_NOT_FOUND | NOT_RUN

    @property
    def accepted(self) -> bool:
        return not self.findings

    def feedback(self) -> str:
        lines = []
        for f in self.findings:
            lines.append(f"- {f.code}: {f.message}")
            for needle, hint in _FIX_HINTS:
                if needle in f.message or needle == f.code:
                    lines.append(f"  How to fix: {hint}")
        return "\n".join(lines)


#: Static, model-text-free repair hints keyed by policy label or finding code.
_FIX_HINTS = (
    (
        "computed member access",
        "never write name[...] (no a[i], obj[key], list[list.length - 1]). Keep a direct "
        "reference in a variable or field instead, or use list.at(index).",
    ),
    ("escape sequence", "remove backslash escapes such as \\n or \\u; use plain ASCII text."),
    ("non-ASCII", "use only plain ASCII characters, including in strings and comments."),
    ("globalThis", "do not use globalThis; everything the module needs must be local."),
    ("MISSING_METHOD", "restore the exact method name and parameter list from the skeleton."),
    ("MISSING_CLASS", "restore the exact export class line from the skeleton, including extends."),
    ("UNIMPLEMENTED_METHOD", "implement every method; no TODO error may remain."),
    ("SYNTAX_ERROR", "return one complete, syntactically valid ES module with balanced braces."),
    (
        "PROBE_INVALID_FIELD",
        "every field must hold a real value after each call; store inputs in fields and compute "
        "results from those fields (never read a field you did not assign).",
    ),
    ("PROBE_CALL_THREW", "valid inputs must not throw; check the order of calls and keep needed state in fields."),
    ("PROBE_NO_OBSERVABLE_EFFECT", "public methods must update the facade's fields so the effect is visible."),
    ("PROBE_LOAD_FAILED", "the module must load without errors: declare classes before use and avoid top-level code."),
    ("PROBE_TIMEOUT", "remove endless loops; every method must finish quickly."),
    (
        "PROBE_INPUT_IGNORED",
        "the computation must use that input. Store each input in its own field when it is given "
        "and pass the stored fields (not the same field twice) to the computation.",
    ),
)


def clean_model_output(text: str) -> str:
    """Strip one surrounding Markdown fence if the model added it anyway."""
    cleaned = text.strip()
    fence = re.match(r"^```[A-Za-z]*\s*\n(.*?)\n?```\s*$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    return cleaned + "\n"


def _class_bodies(content: str) -> dict[str, str]:
    """Text from each top-level ``export class X`` to the next top-level export."""
    starts = [(m.start(), m.group(1)) for m in re.finditer(r"(?m)^export\s+class\s+([A-Za-z_$][\w$]*)", content)]
    boundaries = sorted({m.start() for m in re.finditer(r"(?m)^export\s+", content)} | {len(content)})
    bodies = {}
    for start, name in starts:
        end = next(b for b in boundaries if b > start)
        bodies[name] = content[start:end]
    return bodies


def validate_domain_module(content: str, spec: BehaviourSpec) -> BehaviourValidation:
    findings: list[BehaviourFinding] = []

    safety = inspect_javascript_safety(content)
    if not safety.accepted:
        findings.append(
            BehaviourFinding("UNSAFE_GENERATED_CONTENT", f"{POLICY_VERSION} rejected: {safety.describe()}")
        )

    bodies = _class_bodies(content)
    for item in spec.classes:
        if item.kind == "ENUM":
            if not re.search(rf"(?m)^export\s+const\s+{re.escape(item.name)}\s*=", content):
                findings.append(BehaviourFinding("MISSING_ENUM", f"export const {item.name} is missing"))
            continue
        base = rf"\s+extends\s+{re.escape(item.base)}" if item.base else ""
        if not re.search(rf"(?m)^export\s+class\s+{re.escape(item.name)}{base}\s*\{{", content):
            expected = f"export class {item.name}" + (f" extends {item.base}" if item.base else "")
            findings.append(BehaviourFinding("MISSING_CLASS", f"'{expected} {{' is missing or changed"))
            continue
        body = bodies.get(item.name, "")
        for method in item.methods:
            params = r"\s*,\s*".join(re.escape(p.name) for p in method.params)
            pattern = rf"(?m)^\s*(?:async\s+)?{re.escape(method.name)}\s*\(\s*{params}\s*\)\s*\{{"
            if not re.search(pattern, body):
                signature = f"{method.name}({', '.join(p.name for p in method.params)})"
                findings.append(
                    BehaviourFinding("MISSING_METHOD", f"{item.name}.{signature} is missing or its parameters changed")
                )

    if TODO_MARKER in content:
        findings.append(BehaviourFinding("UNIMPLEMENTED_METHOD", f"'{TODO_MARKER}' markers remain"))

    syntax = "NOT_RUN"
    if not any(f.code == "UNSAFE_GENERATED_CONTENT" for f in findings):
        syntax = _node_check(content)
        if syntax == "FAILED":
            findings.append(BehaviourFinding("SYNTAX_ERROR", "node --check could not parse the module"))
    return BehaviourValidation(tuple(findings), syntax)


def extract_class_block(output: str, name: str) -> str | None:
    """Take exactly ``export class <name> ... }`` from a model answer (tolerates a missing export)."""
    text = clean_model_output(output)
    text = re.sub(rf"(?m)^class\s+{re.escape(name)}\b", f"export class {name}", text)
    match = re.search(rf"(?m)^export\s+class\s+{re.escape(name)}\b", text)
    if match is None:
        return None
    rest = text[match.start():]
    # Cut at the first following top-level export or top-level statement after the class closes.
    depth, end, opened = 0, None, False
    for index, char in enumerate(rest):
        if char == "{":
            depth += 1
            opened = True
        elif char == "}":
            depth -= 1
            if opened and depth == 0:
                end = index + 1
                break
    if end is None:
        return rest.strip() + "\n"  # unbalanced: let node --check report it
    return rest[:end].strip() + "\n"


def validate_class_block(block: str | None, item, assembled: str) -> BehaviourValidation:
    """Checks for one model-written class, plus a parse-only check of the assembled module."""
    if block is None:
        return BehaviourValidation(
            (BehaviourFinding("MISSING_CLASS", f"the answer did not contain 'export class {item.name}'"),), "NOT_RUN"
        )
    findings: list[BehaviourFinding] = []
    safety = inspect_javascript_safety(block)
    if not safety.accepted:
        findings.append(BehaviourFinding("UNSAFE_GENERATED_CONTENT", f"{POLICY_VERSION} rejected: {safety.describe()}"))
    base = rf"\s+extends\s+{re.escape(item.base)}" if item.base else ""
    if not re.search(rf"(?m)^export\s+class\s+{re.escape(item.name)}{base}\s*\{{", block):
        expected = f"export class {item.name}" + (f" extends {item.base}" if item.base else "")
        findings.append(BehaviourFinding("MISSING_CLASS", f"'{expected} {{' is missing or changed"))
    for method in item.methods:
        params = r"\s*,\s*".join(re.escape(p.name) for p in method.params)
        if not re.search(rf"(?m)^\s*(?:async\s+)?{re.escape(method.name)}\s*\(\s*{params}\s*\)\s*\{{", block):
            signature = f"{method.name}({', '.join(p.name for p in method.params)})"
            findings.append(BehaviourFinding("MISSING_METHOD", f"{item.name}.{signature} is missing or its parameters changed"))
    if TODO_MARKER in block:
        findings.append(BehaviourFinding("UNIMPLEMENTED_METHOD", f"'{TODO_MARKER}' markers remain"))
    syntax = "NOT_RUN"
    if not findings:
        syntax = _node_check(assembled)
        if syntax == "FAILED":
            findings.append(BehaviourFinding("SYNTAX_ERROR", "node --check could not parse the module with this class"))
    return BehaviourValidation(tuple(findings), syntax)


@dataclass(frozen=True)
class BehaviourProbe:
    status: str  # PASSED | WARNINGS | FAILED | TIMEOUT | SKIPPED_NODE_NOT_FOUND | ERROR
    findings: tuple[BehaviourFinding, ...]
    steps: tuple[dict, ...]
    warnings: tuple[BehaviourFinding, ...] = ()


def node_permission_args(directory: Path, *extra_read: Path) -> list[str]:
    """Node permission model: read only inside ``directory`` (and any ``extra_read`` folder); no writes, child processes or workers."""
    return ["--permission", *(f"--allow-fs-read={folder}{os.sep}*" for folder in (directory, *extra_read))]


def run_behaviour_probe(content: str, spec_json: str) -> BehaviourProbe:
    """Run the static smoke probe once in a permission-restricted Node child process.

    This executes the candidate module, so it only runs after the lexical policy,
    interface and syntax checks passed. The probe uses fixed sample inputs and has
    no expected answers: passing means "no crash, no undefined/NaN state, some
    visible effect", not "correct".
    """
    from intelise_c3.generation.behaviour_templates import PROBE_MJS, RUNTIME_MJS

    node = shutil.which("node")
    if node is None:
        return BehaviourProbe("SKIPPED_NODE_NOT_FOUND", (), ())
    with tempfile.TemporaryDirectory(prefix="c3-behaviour-probe-") as directory:
        root = Path(directory).resolve()
        (root / "domain.mjs").write_text(content, encoding="utf-8")
        (root / "runtime.mjs").write_text(RUNTIME_MJS, encoding="utf-8")
        (root / "probe.mjs").write_text(PROBE_MJS, encoding="utf-8")
        (root / "behaviour-spec.json").write_text(spec_json, encoding="utf-8")
        try:
            result = subprocess.run(
                [node, *node_permission_args(root), str(root / "probe.mjs")],
                capture_output=True,
                timeout=20,
                cwd=root,
                env={"PATH": os.environ.get("PATH", ""), "SystemRoot": os.environ.get("SystemRoot", "")},
            )
        except subprocess.TimeoutExpired:
            return BehaviourProbe(
                "TIMEOUT",
                (BehaviourFinding("PROBE_TIMEOUT", "the probe did not finish within 20 s (possible endless loop)"),),
                (),
            )
    import json

    lines = [line for line in result.stdout.decode("utf-8", "replace").splitlines() if line.strip()]
    try:
        payload = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        payload = None
    if payload is None:
        reason = "the module crashed while loading (see the error type)"
        stderr = result.stderr.decode("utf-8", "replace")
        error_type = re.search(r"\b([A-Z][A-Za-z]*Error)\b", stderr)
        if error_type:
            reason = f"loading the module raised {error_type.group(1)}"
        return BehaviourProbe("ERROR", (BehaviourFinding("PROBE_LOAD_FAILED", reason),), ())
    findings = tuple(BehaviourFinding(item["code"], item["message"]) for item in payload.get("findings", []))
    warnings = tuple(BehaviourFinding(item["code"], item["message"]) for item in payload.get("warnings", []))
    status = "FAILED" if findings else "WARNINGS" if warnings else "PASSED"
    return BehaviourProbe(status, findings, tuple(payload.get("steps", [])), warnings)


def _node_check(content: str) -> str:
    """Parse-only syntax check; ``node --check`` does not run the module."""
    node = shutil.which("node")
    if node is None:
        return "SKIPPED_NODE_NOT_FOUND"
    with tempfile.TemporaryDirectory(prefix="c3-behaviour-check-") as directory:
        path = Path(directory) / "domain.mjs"
        path.write_text(content, encoding="utf-8")
        try:
            result = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True,
                timeout=20,
                env={"PATH": os.environ.get("PATH", ""), "SystemRoot": os.environ.get("SystemRoot", "")},
            )
        except subprocess.TimeoutExpired:
            return "FAILED"
    return "PASSED" if result.returncode == 0 else "FAILED"
