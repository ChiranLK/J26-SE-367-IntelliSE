"""Conservative lexical safety policy for generated backend JavaScript modules.

This is NOT a JavaScript sandbox, parser, or security proof. It is a
deliberately over-rejecting deny-list applied to the three narrow Task
Management MVP backend modules (service, controller, repository) so that text
which plausibly reaches host, network, dynamic-code, or timer capabilities is
rejected before it is written. It cannot see through every possible
obfuscation, does not understand strings or comments (a forbidden word inside a
comment or string is rejected too), and never executes JavaScript.

Two kinds of finding are distinguished:

* ``UNSAFE`` constructs are recognized capabilities that must not appear.
* ``UNINSPECTABLE`` syntax (escape sequences, non-ASCII characters, computed
  member access) cannot be safely inspected by regex, so it is rejected and the
  outcome is routed to human review rather than guessed at.

The same policy gates the local-model service module in Task 6 generation, the
deterministic templates for the same modules, and Task 9 patch acceptance. It
is intentionally not applied to ``app.js`` (which legitimately imports and reads
``process.env``) or to the browser client (which legitimately uses ``fetch``).
"""

from dataclasses import dataclass
from enum import StrEnum
import re

POLICY_VERSION = "C3_JS_CONSERVATIVE_LEXICAL_POLICY_V1"

SERVICE_MODULE_PATH = "backend/src/services/taskService.js"
CONTROLLER_MODULE_PATH = "backend/src/controllers/taskController.js"
REPOSITORY_MODULE_PATH = "backend/src/repositories/taskRepository.js"

#: Modules this policy applies to. Others have different, legitimate needs.
SAFETY_CHECKED_MODULES = frozenset(
    {SERVICE_MODULE_PATH, CONTROLLER_MODULE_PATH, REPOSITORY_MODULE_PATH}
)

#: The only ``globalThis`` use the fixed service interface requires.
_SECURE_UUID_CALL = re.compile(
    r"globalThis\s*\.\s*crypto\s*\.\s*randomUUID\s*\(\s*\)"
)

#: Pre-existing Task 6 deny-list, kept verbatim and still enforced.
LEGACY_FORBIDDEN_CONTENT = re.compile(
    r"\b(?:child_process|node:fs|fs/promises|process\.|eval\s*\(|"
    r"new\s+Function\s*\(|import\s*(?:\(|\s)|require\s*\(|"
    r"Object\.assign\s*\(|Math\.random\s*\()",
    re.IGNORECASE,
)


class ViolationKind(StrEnum):
    UNSAFE = "UNSAFE"
    UNINSPECTABLE = "UNINSPECTABLE"


@dataclass(frozen=True)
class JsSafetyViolation:
    kind: ViolationKind
    category: str
    label: str


@dataclass(frozen=True)
class JsSafetyReport:
    violations: tuple[JsSafetyViolation, ...]

    @property
    def accepted(self) -> bool:
        return not self.violations

    @property
    def has_unsafe(self) -> bool:
        return any(item.kind is ViolationKind.UNSAFE for item in self.violations)

    @property
    def only_uninspectable(self) -> bool:
        return bool(self.violations) and not self.has_unsafe

    def describe(self) -> str:
        """Static, model-text-free summary safe to place in logs, errors, prompts."""
        return ", ".join(sorted({f"{item.category}: {item.label}" for item in self.violations}))


def _word(*names: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w$])(?:" + "|".join(names) + r")(?![\w$])")


_UNSAFE_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("HOST_ACCESS", "import statement or dynamic import", _word("import")),
    ("HOST_ACCESS", "require or module.require", _word("require")),
    ("HOST_ACCESS", "process object", _word("process")),
    ("HOST_ACCESS", "node: built-in specifier", re.compile(r"node:[A-Za-z_/]+")),
    ("HOST_ACCESS", "child_process", _word("child_process")),
    (
        "HOST_ACCESS",
        "global-object or runtime alias",
        _word(
            "global",
            "window",
            "self",
            "document",
            "navigator",
            "Deno",
            "Bun",
            "WebAssembly",
            "Reflect",
            "Proxy",
        ),
    ),
    ("GLOBAL_ACCESS", "globalThis access", _word("globalThis")),
    (
        "NETWORK",
        "network-capable API",
        _word(
            "fetch",
            "XMLHttpRequest",
            "WebSocket",
            "EventSource",
            "sendBeacon",
            "Worker",
            "SharedWorker",
            "importScripts",
        ),
    ),
    ("DYNAMIC_CODE", "eval", _word("eval")),
    (
        "DYNAMIC_CODE",
        "Function constructor",
        _word("Function", "AsyncFunction", "GeneratorFunction", "AsyncGeneratorFunction"),
    ),
    ("DYNAMIC_CODE", "constructor chain via member access", re.compile(r"\.\s*constructor(?![\w$])")),
    (
        "DYNAMIC_CODE",
        "quoted constructor property name",
        re.compile(r"""['"`]\s*constructor\s*['"`]"""),
    ),
    (
        "DYNAMIC_CODE",
        "prototype manipulation",
        _word(
            "__proto__",
            "prototype",
            "getPrototypeOf",
            "setPrototypeOf",
            "__defineGetter__",
            "__defineSetter__",
            "__lookupGetter__",
            "__lookupSetter__",
        ),
    ),
    (
        "TIMER",
        "timer or deferred-execution API",
        _word(
            "setTimeout",
            "setInterval",
            "setImmediate",
            "queueMicrotask",
            "requestAnimationFrame",
            "requestIdleCallback",
        ),
    ),
)

_ESCAPE_SEQUENCE = re.compile(r"\\(?:u|x|[0-7])")
_NON_ASCII_OR_CONTROL = re.compile(r"[^\x20-\x7e\n\r\t]")
_COMPUTED_ACCESS = re.compile(r"([A-Za-z_$][\w$]*|\)|\]|\?\.|['\"`])\s*\[")
_ARRAY_LITERAL_KEYWORDS = frozenset(
    {
        "return",
        "typeof",
        "case",
        "in",
        "of",
        "yield",
        "await",
        "throw",
        "new",
        "delete",
        "void",
        "else",
        "do",
        "instanceof",
    }
)


def inspect_javascript_safety(
    content: str, *, allow_secure_uuid: bool = False
) -> JsSafetyReport:
    """Return every policy finding for one candidate module (never executes it).

    ``allow_secure_uuid`` permits exactly ``globalThis.crypto.randomUUID()``,
    which the fixed service interface requires, and nothing else about
    ``globalThis``.
    """
    findings: dict[tuple[ViolationKind, str, str], JsSafetyViolation] = {}

    def add(kind: ViolationKind, category: str, label: str) -> None:
        findings[(kind, category, label)] = JsSafetyViolation(kind, category, label)

    scanned = _SECURE_UUID_CALL.sub("secureUuid()", content) if allow_secure_uuid else content

    if LEGACY_FORBIDDEN_CONTENT.search(content):
        add(ViolationKind.UNSAFE, "HOST_ACCESS", "legacy forbidden host-access pattern")
    for category, label, pattern in _UNSAFE_RULES:
        if pattern.search(scanned):
            add(ViolationKind.UNSAFE, category, label)

    if _NON_ASCII_OR_CONTROL.search(content):
        add(ViolationKind.UNINSPECTABLE, "UNINSPECTABLE_SYNTAX", "non-ASCII or control character")
    if _ESCAPE_SEQUENCE.search(content):
        add(
            ViolationKind.UNINSPECTABLE,
            "UNINSPECTABLE_SYNTAX",
            "unicode, hex, or octal escape sequence",
        )
    for match in _COMPUTED_ACCESS.finditer(content):
        if match.group(1) not in _ARRAY_LITERAL_KEYWORDS:
            add(
                ViolationKind.UNINSPECTABLE,
                "UNINSPECTABLE_SYNTAX",
                "computed member access",
            )
            break
    return JsSafetyReport(violations=tuple(findings.values()))


def allows_secure_uuid(relative_path: str) -> bool:
    """Only the service module's fixed interface requires ``crypto.randomUUID``."""
    return relative_path == SERVICE_MODULE_PATH
