"""Design-to-Code and architecture-conformance verification for hybrid runs.

Both verifiers are read-only: they inspect generated text and return findings
(rule ID, expected vs observed structure, evidence, module, severity,
confidence, artifact digest). They never patch code; a FAIL can only *trigger*
the central regeneration workflow, which records its own evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import posixpath
import re
from typing import Any

from intelise_c3.domain.design_context import DesignContext
from intelise_c3.hybrid.gpa_templates import DATABASE_ENTITIES, operations_for

VERIFIER_VERSION = "c3-hybrid-verifier-1.0.0"
_UML_MARKER = re.compile(r"//\s*@c3-uml\s+(?P<uml>[A-Za-z_][A-Za-z0-9_]*)\s*\n\s*export\s+class\s+(?P<cls>[A-Za-z_][A-Za-z0-9_]*)")
_IMPORT = re.compile(r"""(?:^|\n)\s*import\s+(?:[^'";]+?\s+from\s+)?['"](?P<spec>[^'"]+)['"]|import\(\s*['"](?P<dyn>[^'"]+)['"]\s*\)|require\(\s*['"](?P<req>[^'"]+)['"]\s*\)""")
_SQL_CALL = re.compile(r"\b(?:pool|client)\.query\(")
_DB_PACKAGES = {"pg", "pg-pool", "postgres", "mysql", "mysql2", "sqlite3", "better-sqlite3", "mongodb"}


@dataclass
class Finding:
    rule_id: str
    status: str  # PASS | FAIL | REVIEW_REQUIRED
    code: str
    expected: str
    observed: str
    evidence: str
    module_id: str | None
    severity: str
    confidence: float

    def as_json(self, artifact_digest: str | None) -> dict[str, Any]:
        return {**self.__dict__, "artifact_digest_sha256": artifact_digest}


@dataclass
class VerificationReport:
    verifier: str
    rule_set: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def status(self) -> str:
        statuses = {finding.status for finding in self.findings}
        if "FAIL" in statuses:
            return "FAIL"
        if "REVIEW_REQUIRED" in statuses:
            return "REVIEW_REQUIRED"
        return "PASS"

    def as_json(self, artifact_digest: str | None) -> dict[str, Any]:
        return {
            "verifier": self.verifier,
            "verifier_version": VERIFIER_VERSION,
            "rule_set": self.rule_set,
            "status": self.status,
            "fail_count": sum(f.status == "FAIL" for f in self.findings),
            "review_count": sum(f.status == "REVIEW_REQUIRED" for f in self.findings),
            "pass_count": sum(f.status == "PASS" for f in self.findings),
            "findings": [finding.as_json(artifact_digest) for finding in self.findings],
            "execution_claim": "STATIC_INSPECTION_ONLY",
            "patch_authority": "NONE - findings may trigger the central regeneration workflow only",
        }

    def regeneration_triggers(self) -> list[str]:
        return sorted({f.module_id for f in self.findings if f.status == "FAIL" and f.module_id})


_EXPORT_CLASS = re.compile(r"export\s+class\s+(?P<cls>[A-Za-z_][A-Za-z0-9_]*)")


_METHOD_ANY_INDENT = re.compile(
    r"^(?P<indent>[ \t]+)(?:static\s+)?(?:async\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{", re.MULTILINE
)
_CONTROL_KEYWORDS = frozenset({"if", "for", "while", "switch", "catch", "function", "return", "with", "else", "do", "try"})


def _methods_after(content: str, start: int) -> list[str]:
    """Method names of the class whose header ends at ``start``, for any consistent indentation.

    Members sit at the class body's own (smallest) indentation; deeper matches are statements such as
    ``if (x) {`` and are ignored.
    """
    end = content.find("\n}\n", start)
    body = content[start:end if end != -1 else len(content)]
    candidates = [
        (len(m.group("indent").expandtabs(2)), m.group("name"))
        for m in _METHOD_ANY_INDENT.finditer(body)
        if m.group("name") not in _CONTROL_KEYWORDS
    ]
    if not candidates:
        return []
    member_indent = min(indent for indent, _ in candidates)
    return sorted({name for indent, name in candidates if indent == member_indent} - {"constructor"})


def extract_symbols(files: dict[str, str], design_classes: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Classes bound to UML by a ``// @c3-uml X`` marker, or by an exact released-class name (bounded LLM output)."""
    symbols = []
    for path, content in sorted(files.items()):
        if not path.endswith((".js", ".mjs", ".jsx")):
            continue
        marked = set()
        for match in _UML_MARKER.finditer(content):
            marked.add(match.group("cls"))
            symbols.append({"path": path, "class": match.group("cls"), "uml_class": match.group("uml"),
                            "methods": _methods_after(content, match.end()), "binding": "C3_UML_MARKER"})
        for match in _EXPORT_CLASS.finditer(content):
            name = match.group("cls")
            if name in design_classes and name not in marked:
                symbols.append({"path": path, "class": name, "uml_class": name,
                                "methods": _methods_after(content, match.end()), "binding": "EXACT_CLASS_NAME"})
    return symbols


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _module_of(path: str, file_modules: dict[str, str]) -> str | None:
    return file_modules.get(path)


def verify_design_to_code(
    design: DesignContext,
    files: dict[str, str],
    file_modules: dict[str, str],
    persistence_required: bool,
    type_map: dict[str, dict[str, str]],
    deferred_classes: frozenset[str] = frozenset(),
    clear_history: bool = False,
) -> VerificationReport:
    """``deferred_classes`` are rule-unsupported classes already escalated to human review."""
    report = VerificationReport("DESIGN_TO_CODE", "V-D2C-GPA-1.0.0")
    add = report.findings.append
    symbols = extract_symbols(files, frozenset(parsed.name for parsed in design.classes))
    by_uml: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        by_uml.setdefault(symbol["uml_class"], []).append(symbol)
    design_classes = {parsed.name: parsed for parsed in design.classes}

    for parsed in design.classes:
        if not parsed.methods:
            continue
        implementations = by_uml.get(parsed.name, [])
        if not implementations and parsed.name in deferred_classes:
            add(Finding("V-D2C-CLASSES", "REVIEW_REQUIRED", "CLASS_PENDING_HUMAN_REVIEW", f"class bound to UML {parsed.name}",
                        "not generated: no deterministic rule and no accepted bounded generation", "-", None, "MEDIUM", 1.0))
            continue
        if not implementations:
            add(Finding("V-D2C-CLASSES", "FAIL", "MISSING_CLASS", f"class bound to UML {parsed.name}",
                        "no @c3-uml binding found", "backend/src/**", None, "HIGH", 1.0))
            continue
        expected = sorted(method.name for method in parsed.methods)
        for implementation in implementations:
            missing = sorted(set(expected) - set(implementation["methods"]))
            module_id = _module_of(implementation["path"], file_modules)
            if missing:
                add(Finding("V-D2C-METHODS", "FAIL", "MISSING_METHOD", f"{parsed.name}: {expected}",
                            f"{implementation['class']}: {implementation['methods']}", implementation["path"], module_id, "HIGH", 1.0))
            else:
                add(Finding("V-D2C-METHODS", "PASS", "METHODS_PRESENT", f"{parsed.name}: {expected}",
                            f"{implementation['class']}: {implementation['methods']}", implementation["path"], module_id, "INFO", 1.0))
    for uml_class, implementations in sorted(by_uml.items()):
        if uml_class not in design_classes:
            for implementation in implementations:
                add(Finding("V-D2C-EXTRA", "REVIEW_REQUIRED", "UNSUPPORTED_EXTRA_ELEMENT", "only released UML classes",
                            f"{implementation['class']} bound to unknown UML {uml_class}", implementation["path"],
                            _module_of(implementation["path"], file_modules), "MEDIUM", 0.9))

    openapi_text = files.get("openapi/openapi.json")
    openapi = json.loads(openapi_text) if openapi_text else {"paths": {}, "components": {"schemas": {}}}
    schemas = openapi.get("components", {}).get("schemas", {})
    migration = "\n".join(content for path, content in files.items() if path.startswith("database/migrations/"))
    for parsed in design.classes:
        if not parsed.attributes:
            continue
        schema = schemas.get(parsed.name)
        if schema is None:
            add(Finding("V-D2C-FIELDS", "FAIL", "MISSING_SCHEMA", f"OpenAPI schema {parsed.name}", "absent",
                        "openapi/openapi.json", file_modules.get("openapi/openapi.json"), "HIGH", 1.0))
            continue
        properties = schema.get("properties", {})
        table = next((entity.table for entity in DATABASE_ENTITIES if entity.uml_class == parsed.name), None)
        table_block = ""
        if table:
            match = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", migration, re.DOTALL)
            table_block = match.group(1) if match else ""
        for attribute in parsed.attributes:
            expected_type = type_map.get(attribute.type_name, {}).get("json_schema")
            observed = properties.get(attribute.name)
            if observed is None:
                add(Finding("V-D2C-FIELDS", "FAIL", "MISSING_FIELD", f"{parsed.name}.{attribute.name}", "absent from OpenAPI schema",
                            "openapi/openapi.json", file_modules.get("openapi/openapi.json"), "HIGH", 1.0))
            elif observed.get("type") != expected_type:
                add(Finding("V-D2C-TYPES", "FAIL", "TYPE_MISMATCH", f"{parsed.name}.{attribute.name}: {expected_type}",
                            f"{observed.get('type')}", "openapi/openapi.json", file_modules.get("openapi/openapi.json"), "HIGH", 1.0))
            else:
                add(Finding("V-D2C-TYPES", "PASS", "FIELD_TYPE_MATCH", f"{parsed.name}.{attribute.name}: {expected_type}",
                            str(observed.get("type")), "openapi/openapi.json", file_modules.get("openapi/openapi.json"), "INFO", 1.0))
            if persistence_required and table:
                column = _snake(attribute.name)
                if column not in re.findall(r"^\s*([a-z_]+)\s", table_block, re.MULTILINE):
                    add(Finding("V-D2C-ENTITIES", "FAIL", "MISSING_COLUMN", f"{table}.{column}", "absent from migration",
                                "database/migrations", file_modules.get("database/migrations/001_create_gpa_calculations.sql"), "HIGH", 1.0))

    for relationship in design.relationships:
        source, target = relationship.source_class, relationship.target_class
        if relationship.relationship_type == "COMPOSITION":
            items = schemas.get(source, {}).get("properties", {}).get(f"{target[0].lower()}{target[1:]}s") or \
                schemas.get(source, {}).get("properties", {}).get("modules")
            ok = bool(items and items.get("items", {}).get("$ref", "").endswith(f"/{target}"))
            child = next((e.table for e in DATABASE_ENTITIES if e.uml_class == target), None)
            parent = next((e.table for e in DATABASE_ENTITIES if e.uml_class == source), None)
            fk = bool(child and parent and re.search(rf"REFERENCES {parent}\(id\) ON DELETE CASCADE", migration))
            status = "PASS" if ok and (fk or not persistence_required) else "FAIL"
            add(Finding("V-D2C-RELATIONSHIPS", status, "COMPOSITION" if status == "PASS" else "MISSING_RELATIONSHIP",
                        f"{source} *-- {target}: nested array + cascading FK", f"schema array={ok}, fk={fk}",
                        "openapi/openapi.json; database/migrations", file_modules.get("openapi/openapi.json"), "HIGH" if status == "FAIL" else "INFO", 0.95))
        elif relationship.label == "uses":
            role = "repository" if target.endswith("Repository") else f"{target[0].lower()}{target[1:]}"
            impl = next((s for s in by_uml.get(source, [])), None)
            content = files.get(impl["path"], "") if impl else ""
            injected = bool(re.search(rf"constructor\(\{{[^}}]*\b{role}\b", content))
            add(Finding("V-D2C-RELATIONSHIPS", "PASS" if injected else "FAIL", "INJECTED_DEPENDENCY" if injected else "MISSING_RELATIONSHIP",
                        f"{source} uses {target} via constructor injection of '{role}'", "injected" if injected else "not injected",
                        impl["path"] if impl else "-", _module_of(impl["path"], file_modules) if impl else None,
                        "INFO" if injected else "HIGH", 0.9))

    paths = openapi.get("paths", {})
    observed_ops = {
        (method.upper(), path, operation.get("operationId"))
        for path, methods in paths.items()
        for method, operation in methods.items()
    }
    routes = files.get("backend/src/routes/gpaRoutes.js", "")
    expected_ops = operations_for(persistence_required, clear_history)
    for op in expected_ops:
        in_openapi = (op.method, op.path, op.operation_id) in observed_ops
        route_path = op.path.removeprefix("/api/v1")
        in_routes = f"router.{op.method.lower()}('{route_path}'" in routes
        status = "PASS" if in_openapi and in_routes else "FAIL"
        add(Finding("V-D2C-ENDPOINTS", status, "ENDPOINT_PRESENT" if status == "PASS" else "MISSING_ENDPOINT",
                    f"{op.method} {op.path} ({op.operation_id})", f"openapi={in_openapi}, route={in_routes}",
                    "openapi/openapi.json; backend/src/routes/gpaRoutes.js", file_modules.get("backend/src/routes/gpaRoutes.js"),
                    "INFO" if status == "PASS" else "HIGH", 1.0))
    expected_ids = {op.operation_id for op in expected_ops}
    for method, path, operation_id in sorted(observed_ops, key=str):
        if operation_id not in expected_ids:
            add(Finding("V-D2C-EXTRA", "REVIEW_REQUIRED", "UNSUPPORTED_EXTRA_ELEMENT", "only rule-derived operations",
                        f"{method} {path} ({operation_id})", "openapi/openapi.json", file_modules.get("openapi/openapi.json"), "MEDIUM", 0.9))

    tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z_]+)", migration))
    if persistence_required:
        for entity in DATABASE_ENTITIES:
            status = "PASS" if entity.table in tables else "FAIL"
            add(Finding("V-D2C-ENTITIES", status, "ENTITY_PRESENT" if status == "PASS" else "MISSING_DATABASE_ENTITY",
                        f"table {entity.table} for {entity.uml_class}", "present" if status == "PASS" else "absent",
                        "database/migrations", file_modules.get("database/migrations/001_create_gpa_calculations.sql"),
                        "INFO" if status == "PASS" else "HIGH", 1.0))
        for table in sorted(tables - {entity.table for entity in DATABASE_ENTITIES}):
            add(Finding("V-D2C-EXTRA", "REVIEW_REQUIRED", "UNSUPPORTED_EXTRA_ELEMENT", "only design-derived tables", table,
                        "database/migrations", None, "MEDIUM", 0.9))
    return report


def _layer(path: str, layer_map: dict[str, str]) -> str | None:
    best = None
    for prefix, layer in layer_map.items():
        if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, layer)
    return best[1] if best else None


def verify_architecture(files: dict[str, str], file_modules: dict[str, str], convention: dict[str, Any]) -> VerificationReport:
    report = VerificationReport("ARCHITECTURE_CONFORMANCE", f"V-ARCH-NODE-LAYERING/{convention['item_id']}")
    layer_map: dict[str, str] = convention["layer_by_directory"]
    allowed: dict[str, list[str]] = convention["allowed_dependencies"]
    checked = 0
    for path, content in sorted(files.items()):
        if not path.endswith((".js", ".mjs", ".jsx")) or path.startswith(("backend/test/", "deployment/")):
            continue
        source_layer = _layer(path, layer_map)
        if source_layer is None:
            continue
        module_id = file_modules.get(path)
        for match in _IMPORT.finditer(content):
            spec = match.group("spec") or match.group("dyn") or match.group("req")
            checked += 1
            if spec.startswith("."):
                target_path = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
                target_layer = _layer(target_path, layer_map)
                if source_layer == "FRONTEND" and target_path.startswith("backend/"):
                    target_layer = "DATABASE" if "/db/" in target_path or "/repositories/" in target_path else "BACKEND"
            elif source_layer == "FRONTEND" and spec in _DB_PACKAGES:
                target_layer = "DATABASE"
            elif spec in _DB_PACKAGES and source_layer not in {"DATABASE", "REPOSITORY", "COMPOSITION_ROOT"}:
                target_layer = "DATABASE"
            else:
                continue
            if target_layer is None or target_layer == source_layer:
                continue
            if target_layer not in allowed.get(source_layer, []):
                report.findings.append(Finding(
                    "V-ARCH-NODE-LAYERING", "FAIL", "FORBIDDEN_DEPENDENCY",
                    f"{source_layer} may depend on {allowed.get(source_layer, [])}",
                    f"{source_layer} -> {target_layer} ({spec})", path, module_id, "HIGH", 1.0,
                ))
        if source_layer not in {"REPOSITORY", "DATABASE", "COMPOSITION_ROOT"} and _SQL_CALL.search(content):
            report.findings.append(Finding(
                "V-ARCH-NODE-LAYERING", "FAIL", "DATABASE_ACCESS_OUTSIDE_REPOSITORY",
                "SQL only in repository modules", f"{source_layer} issues SQL", path, module_id, "HIGH", 1.0,
            ))
    if not any(f.status == "FAIL" for f in report.findings):
        report.findings.append(Finding(
            "V-ARCH-NODE-LAYERING", "PASS", "LAYERING_CONFORMS",
            "Route -> Controller -> Service -> Repository -> Database", f"{checked} imports inspected, no forbidden edge",
            "backend/src; frontend/src", None, "INFO", 1.0,
        ))
    return report
