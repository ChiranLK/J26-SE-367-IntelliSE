"""Static policy for LLM-written frontend files (JSX/JS/CSS). Lexical, conservative, never executes anything.

The UI runs in the user's browser. Model output is untrusted, so the only network path allowed is the
*trusted* generated API client (``src/api/gpaApi.js``); LLM files may not call ``fetch`` or friends, build HTML from
strings, touch browser storage or cookies, navigate away, load code dynamically or import packages other than
``react``. Imports of project files must resolve inside the allowed file set.
"""

from __future__ import annotations

import posixpath
import re

POLICY_VERSION = "C3_FRONTEND_LEXICAL_POLICY_V1"
MAX_FILE_CHARS = 24000
ALLOWED_PACKAGES = frozenset({"react"})

_FORBIDDEN: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DYNAMIC_CODE", re.compile(r"\beval\s*\(|\bnew\s+Function\b|(?<![\w.])Function\s*\(|\bsetTimeout\s*\(\s*['\"`]|\bsetInterval\s*\(\s*['\"`]")),
    ("NETWORK", re.compile(r"\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\b|\bEventSource\b|\bsendBeacon\b|\bimportScripts\b|\bnew\s+Worker\b|\bnew\s+SharedWorker\b|\bserviceWorker\b")),
    ("HTML_INJECTION", re.compile(r"dangerouslySetInnerHTML|\.innerHTML\b|\.outerHTML\b|insertAdjacentHTML|document\s*\.\s*write|\.srcdoc\b|createContextualFragment")),
    ("NAVIGATION", re.compile(r"\bwindow\s*\.\s*open\b|\blocation\s*(?:\.|=|\[)|\bwindow\s*\.\s*top\b|\bwindow\s*\.\s*parent\b|\bhistory\s*\.\s*(?:push|replace)State\b")),
    ("BROWSER_STORAGE", re.compile(r"\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b|document\s*\.\s*cookie|\bcaches\s*\.")),
    ("HOST_ACCESS", re.compile(r"\bprocess\s*\.|\bglobalThis\b|\brequire\s*\(|\bimport\s*\(|\bimport\.meta\b|\bchild_process\b|\b__proto__\b|\bwindow\s*\[|\bdocument\s*\[")),
)
_IMPORT_FROM = re.compile(r"""^\s*import\s+(?:[^'";]+?\s+from\s+)?['"](?P<spec>[^'"]+)['"]""", re.MULTILINE)
_CSS_FORBIDDEN = re.compile(r"@import|@charset|expression\s*\(|url\s*\(|behavior\s*:|-moz-binding", re.IGNORECASE)
# Control characters (except tab/newline/CR) and bidirectional overrides ("trojan source") hide code from reviewers.
_HIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩​-‏﻿]")


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", "", source)


def check_bundle(files: dict[str, str], expected_paths: frozenset[str], trusted_paths: frozenset[str]) -> list[str]:
    """Return findings for a candidate file bundle; an empty list means the bundle passes the policy."""
    findings: list[str] = []
    missing = sorted(expected_paths - set(files))
    extra = sorted(set(files) - expected_paths)
    if missing:
        findings.append(f"BUNDLE_MISSING_FILES: {missing}")
    if extra:
        findings.append(f"BUNDLE_UNEXPECTED_FILES: {extra}; write exactly the requested files and nothing else")
    importable = expected_paths | trusted_paths
    for path in sorted(set(files) & expected_paths):
        content = files[path]
        if len(content) > MAX_FILE_CHARS:
            findings.append(f"{path}: FILE_TOO_LARGE ({len(content)} > {MAX_FILE_CHARS} characters)")
        if _HIDDEN.search(content):
            findings.append(f"{path}: HIDDEN_CHARACTERS: control or bidirectional characters are not allowed")
        if path.endswith(".css"):
            if _CSS_FORBIDDEN.search(content):
                findings.append(f"{path}: CSS_FORBIDDEN: @import, url(), expression() and similar are not allowed (no external resources)")
            continue
        code = _strip_comments(content)
        for label, pattern in _FORBIDDEN:
            match = pattern.search(code)
            if match:
                findings.append(f"{path}: {label}: '{match.group(0).strip()[:40]}' is not allowed in LLM-written UI code")
        for match in _IMPORT_FROM.finditer(code):
            spec = match.group("spec")
            if spec.startswith("."):
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
                if resolved not in importable:
                    findings.append(f"{path}: IMPORT_NOT_ALLOWED: '{spec}' resolves to {resolved}, which is not one of the project files you may import")
            elif spec not in ALLOWED_PACKAGES:
                findings.append(f"{path}: IMPORT_NOT_ALLOWED: package '{spec}' (only {sorted(ALLOWED_PACKAGES)} may be imported)")
    return findings
