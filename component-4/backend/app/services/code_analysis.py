import ast
import re
from typing import Any, Dict, List, Optional, Tuple


# Regex patterns for detecting potential secrets, API keys, and sensitive tokens
SECRET_PATTERNS = [
    # AWS Access Key ID
    (re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "[REDACTED_AWS_KEY]"),
    # Private Key blocks
    (
        re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Bearer tokens
    (
        re.compile(r"\bBearer\s+[A-Za-z0-9\-_\.=]{20,}\b", re.IGNORECASE),
        "Bearer [REDACTED_BEARER_TOKEN]",
    ),
    # Generic API Keys / tokens / passwords in assignments (e.g., api_key = "...", password = '...')
    (
        re.compile(
            r"""(?i)\b(api_key|apikey|secret_key|secret|password|passwd|auth_token|token|private_key)\s*[:=]\s*['"]([A-Za-z0-9\-_\.!@#$%^&*+=]{8,})['"]"""
        ),
        r'\1="[REDACTED_SECRET]"',
    ),
    # Database URLs with embedded credentials (e.g., postgresql://user:pass@host/db)
    (
        re.compile(
            r"""(?i)(postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/([^:]+):([^@]+)@"""
        ),
        r"\1://\2:[REDACTED_PASSWORD]@",
    ),
]


def sanitize_code_secrets(text: str) -> Tuple[str, int]:
    """
    Sanitizes source code text and diagnostic explanations to prevent inadvertent exposure
    of credentials, API keys, passwords, and sensitive runtime tokens.
    Returns (sanitized_text, redaction_count).
    """
    if not text:
        return "", 0

    sanitized = text
    redaction_count = 0

    for pattern, replacement in SECRET_PATTERNS:
        matches = list(pattern.finditer(sanitized))
        if matches:
            redaction_count += len(matches)
            sanitized = pattern.sub(replacement, sanitized)

    return sanitized, redaction_count


def _format_arg(arg: ast.arg, default: Optional[ast.AST] = None) -> str:
    parts = [arg.arg]
    if arg.annotation:
        try:
            parts.append(f": {ast.unparse(arg.annotation)}")
        except Exception:
            pass
    if default:
        try:
            parts.append(f"={ast.unparse(default)}")
        except Exception:
            pass
    return "".join(parts)


def inspect_python_code_ast(source_code: str, filename: str = "solution.py") -> Dict[str, Any]:
    """
    Safely inspects Python source code using host AST parsing without executing untrusted code.
    Extracts structural definitions (functions, classes, signatures, line numbers, imports)
    to serve as the non-hallucinatory evidence foundation for post-delivery code explanations.
    """
    if not source_code or not source_code.strip():
        return {
            "filename": filename,
            "line_count": 0,
            "module_docstring": None,
            "functions": [],
            "classes": [],
            "imports": [],
            "exports": [],
            "is_valid_syntax": False,
        }

    lines = source_code.splitlines()
    line_count = len(lines)

    try:
        tree = ast.parse(source_code, filename=filename)
    except SyntaxError:
        return {
            "filename": filename,
            "line_count": line_count,
            "module_docstring": None,
            "functions": [],
            "classes": [],
            "imports": [],
            "exports": [],
            "is_valid_syntax": False,
        }

    module_docstring = ast.get_docstring(tree)
    functions: List[Dict[str, Any]] = []
    classes: List[Dict[str, Any]] = []
    imports: List[str] = []
    exports: List[str] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_meta = _extract_function_meta(node, lines)
            functions.append(func_meta)
            exports.append(node.name)
        elif isinstance(node, ast.ClassDef):
            class_meta = _extract_class_meta(node, lines)
            classes.append(class_meta)
            exports.append(node.name)
            # Add class methods
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_meta = _extract_function_meta(item, lines, class_name=node.name)
                    functions.append(method_meta)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append(f"{mod}.{alias.name}" if mod else alias.name)

    return {
        "filename": filename,
        "line_count": line_count,
        "module_docstring": module_docstring,
        "functions": functions,
        "classes": classes,
        "imports": list(dict.fromkeys(imports)),
        "exports": exports,
        "is_valid_syntax": True,
    }


def inspect_python_project(
    project_files: Dict[str, str],
    entrypoint: Optional[str] = None,
    max_source_files: int = 16,
    max_source_chars: int = 16_000,
) -> Dict[str, Any]:
    """Build a bounded, non-executing evidence summary for a Python project.

    Production modules are prioritized over tests, then the configured entrypoint is
    placed first. Raw source excerpts are bounded globally so larger archives cannot
    create unbounded LLM prompts.
    """
    python_files = {
        str(path).replace("\\", "/"): content
        for path, content in (project_files or {}).items()
        if str(path).lower().endswith(".py") and isinstance(content, str)
    }
    source_paths = [p for p in python_files if not p.startswith("tests/") and "/tests/" not in p]
    ordered = sorted(source_paths, key=lambda p: (p != entrypoint, p))[:max_source_files]
    omitted = sorted(set(source_paths) - set(ordered))

    modules: List[Dict[str, Any]] = []
    excerpts: List[Dict[str, str]] = []
    remaining_chars = max_source_chars
    for path in ordered:
        content = python_files[path]
        modules.append(inspect_python_code_ast(content, filename=path))
        if remaining_chars > 0:
            excerpt = content[:remaining_chars]
            excerpts.append({"file_path": path, "source": excerpt})
            remaining_chars -= len(excerpt)

    known_modules = {p[:-3].replace("/", ".") for p in ordered}
    interactions: List[Dict[str, str]] = []
    for module in modules:
        for imported in module.get("imports", []):
            matched = next(
                (known for known in known_modules if imported == known or imported.startswith(f"{known}.") or known.endswith(f".{imported}")),
                None,
            )
            if matched:
                interactions.append({
                    "from": module["filename"],
                    "to": f"{matched.replace('.', '/')}.py",
                    "evidence": f"import {imported}",
                })

    return {
        "entrypoint": entrypoint,
        "project_file_count": len(project_files or {}),
        "python_source_file_count": len(source_paths),
        "analyzed_source_files": ordered,
        "omitted_source_files": omitted,
        "analyzed_line_count": sum(m.get("line_count", 0) for m in modules),
        "modules": modules,
        "module_interactions": interactions,
        "source_excerpts": excerpts,
        "source_excerpt_char_count": sum(len(item["source"]) for item in excerpts),
        "test_files": sorted(p for p in python_files if p.startswith("tests/") or "/tests/" in p),
    }


def _extract_function_meta(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: List[str],
    class_name: Optional[str] = None,
) -> Dict[str, Any]:
    docstring = ast.get_docstring(node)
    start_line = node.lineno
    end_line = getattr(node, "end_lineno", start_line)

    # Extract parameters and default values
    args = node.args
    params: List[Dict[str, Any]] = []

    # Map positional defaults
    defaults_offset = len(args.args) - len(args.defaults)
    formatted_args: List[str] = []

    for i, a in enumerate(args.args):
        default_val = None
        if i >= defaults_offset:
            default_val = args.defaults[i - defaults_offset]
        formatted_args.append(_format_arg(a, default_val))

        param_dict: Dict[str, Any] = {
            "name": a.arg,
            "is_required": default_val is None,
        }
        if a.annotation:
            try:
                param_dict["type"] = ast.unparse(a.annotation)
            except Exception:
                param_dict["type"] = None
        if default_val:
            try:
                param_dict["default"] = ast.unparse(default_val)
            except Exception:
                param_dict["default"] = None
        params.append(param_dict)

    if args.vararg:
        formatted_args.append(f"*{args.vararg.arg}")
    if args.kwarg:
        formatted_args.append(f"**{args.kwarg.arg}")

    return_type = None
    if node.returns:
        try:
            return_type = ast.unparse(node.returns)
        except Exception:
            return_type = None

    display_name = f"{class_name}.{node.name}" if class_name else node.name
    ret_str = f" -> {return_type}" if return_type else ""
    signature = f"def {display_name}({', '.join(formatted_args)}){ret_str}"

    # Extract internal function calls for data-flow awareness
    calls: List[str] = []
    raised_exceptions: List[str] = []
    raised_exception_types: List[str] = []
    return_expressions: List[str] = []
    validation_conditions: List[str] = []
    loop_types: List[str] = []
    operations: List[str] = []

    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            try:
                call_name = ast.unparse(sub.func)
                calls.append(call_name)
                if call_name in {"sum", "len", "round", "min", "max", "abs", "float", "int", "str"}:
                    operations.append(call_name)
            except Exception:
                pass
        elif isinstance(sub, ast.Raise) and sub.exc is not None:
            try:
                raised_exceptions.append(ast.unparse(sub.exc))
                if isinstance(sub.exc, ast.Call) and hasattr(sub.exc.func, "id"):
                    raised_exception_types.append(sub.exc.func.id)
                elif hasattr(sub.exc, "id"):
                    raised_exception_types.append(sub.exc.id)
            except Exception:
                pass
        elif isinstance(sub, ast.Return) and sub.value is not None:
            try:
                return_expressions.append(ast.unparse(sub.value))
            except Exception:
                pass
        elif isinstance(sub, ast.If):
            try:
                validation_conditions.append(ast.unparse(sub.test))
            except Exception:
                pass
        elif isinstance(sub, ast.For):
            loop_types.append("for")
        elif isinstance(sub, ast.While):
            loop_types.append("while")
        elif isinstance(sub, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            operations.append("comprehension")

    return {
        "name": node.name,
        "display_name": display_name,
        "class_name": class_name,
        "signature": signature,
        "line_number": start_line,
        "end_line_number": end_line,
        "docstring": docstring,
        "parameters": params,
        "return_type": return_type,
        "calls": list(dict.fromkeys(calls)),
        "raised_exceptions": list(dict.fromkeys(raised_exceptions))[:6],
        "raised_exception_types": list(dict.fromkeys(raised_exception_types))[:4],
        "return_expressions": list(dict.fromkeys(return_expressions))[:6],
        "validation_conditions": list(dict.fromkeys(validation_conditions))[:8],
        "loop_types": list(dict.fromkeys(loop_types)),
        "operations": list(dict.fromkeys(operations)),
    }


def _extract_class_meta(node: ast.ClassDef, lines: List[str]) -> Dict[str, Any]:
    docstring = ast.get_docstring(node)
    bases: List[str] = []
    for b in node.bases:
        try:
            bases.append(ast.unparse(b))
        except Exception:
            pass

    methods = [
        item.name
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    return {
        "name": node.name,
        "line_number": node.lineno,
        "end_line_number": getattr(node, "end_lineno", node.lineno),
        "docstring": docstring,
        "bases": bases,
        "methods": methods,
    }
