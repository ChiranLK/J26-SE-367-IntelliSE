"""Trusted, mutually-exclusive classification of embedded Python project tests."""

import ast
import json
import posixpath
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


TEST_CATEGORIES = ("unit", "integration", "performance")
MANIFEST_NAMES = ("intelise-test-manifest.json", "intelise-tests.json")


def is_python_test_file(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    basename = posixpath.basename(normalized)
    return normalized.endswith(".py") and (
        basename.startswith("test_")
        or basename.endswith("_test.py")
        or "/tests/" in f"/{normalized}"
    )


@dataclass
class ProjectTestClassification:
    assignments: Dict[str, str] = field(default_factory=dict)
    sources: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    has_explicit_metadata: bool = False
    performance_thresholds_ms: Dict[str, float] = field(default_factory=dict)

    def paths_for(self, category: str) -> List[str]:
        return sorted(path for path, assigned in self.assignments.items() if assigned == category)

    def reason_for(self, category: str) -> str:
        paths = self.paths_for(category)
        if self.errors:
            return "Invalid test category metadata: " + "; ".join(self.errors)
        if paths:
            rendered = ", ".join(f"{path} ({self.sources.get(path, 'legacy')})" for path in paths)
            return f"Authorized {category} test files: {rendered}."
        if self.has_explicit_metadata:
            return f"No embedded tests were explicitly authorized for the {category} category."
        if category == "unit":
            return "No embedded Python tests were discovered."
        return f"No trustworthy {category} category declaration was supplied."


def _marker_categories(source: str) -> Tuple[Set[str], List[str]]:
    """Return category markers declared on a module/class/test function."""
    categories: Set[str] = set()
    errors: List[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return categories, [f"test metadata could not be parsed at line {exc.lineno}: {exc.msg}"]

    def category_from_node(node: ast.AST) -> Optional[str]:
        # pytest.mark.<category>
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "pytest"
            and node.value.attr == "mark"
            and node.attr in TEST_CATEGORIES
        ):
            return node.attr
        if isinstance(node, ast.Call):
            return category_from_node(node.func)
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            is_test = isinstance(node, ast.ClassDef) and node.name.startswith("Test")
            is_test = is_test or not isinstance(node, ast.ClassDef) and node.name.startswith("test_")
            if is_test:
                for decorator in node.decorator_list:
                    category = category_from_node(decorator)
                    if category:
                        categories.add(category)
        elif isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets):
                values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
                for value in values:
                    category = category_from_node(value)
                    if category:
                        categories.add(category)

    if len(categories) > 1:
        errors.append(
            "a single test file declares multiple category markers; split it into category-specific files"
        )
    return categories, errors


def _path_category(path: str) -> Optional[Tuple[str, str]]:
    normalized = path.replace("\\", "/").lower()
    basename = posixpath.basename(normalized)
    for category in TEST_CATEGORIES:
        if f"/tests/{category}/" in f"/{normalized}":
            return category, "directory convention"
        # Exact reserved module names are explicit path declarations.  Arbitrary
        # function names and broad name-substring heuristics are intentionally ignored.
        if basename in (f"test_{category}.py", f"{category}_test.py") and "/tests/" in f"/{normalized}":
            return category, "reserved test-module convention"
    return None


def _resolve_manifest_path(raw_path: str, test_paths: List[str]) -> Optional[str]:
    normalized = posixpath.normpath(raw_path.replace("\\", "/")).lstrip("/")
    if normalized.startswith("../") or normalized in ("", "."):
        return None
    exact = [path for path in test_paths if path.replace("\\", "/") == normalized]
    if len(exact) == 1:
        return exact[0]
    suffix = [path for path in test_paths if path.replace("\\", "/").endswith(f"/{normalized}")]
    return suffix[0] if len(suffix) == 1 else None


def classify_project_tests(project_files: Optional[Dict[str, str]]) -> ProjectTestClassification:
    result = ProjectTestClassification()
    if not project_files:
        return result

    test_paths = sorted(path for path in project_files if is_python_test_file(path))
    manifest_candidates = []
    for path, content in project_files.items():
        if not path.lower().endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        if any(
            (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"))
            or (isinstance(node, ast.ClassDef) and node.name.startswith("Test"))
            for node in ast.walk(tree)
        ):
            manifest_candidates.append(path)
    explicit: Dict[str, Tuple[str, str]] = {}

    manifest_paths = [
        path for path in project_files
        if posixpath.basename(path.replace("\\", "/")).lower() in MANIFEST_NAMES
    ]
    if len(manifest_paths) > 1:
        result.errors.append("multiple INTELISE test manifests were supplied")
    elif manifest_paths:
        result.has_explicit_metadata = True
        manifest_path = manifest_paths[0]
        try:
            manifest = json.loads(project_files[manifest_path])
            if not isinstance(manifest, dict) or manifest.get("version") != 1 or not isinstance(manifest.get("tests"), list):
                raise ValueError("manifest requires version=1 and a tests array")
            seen_manifest_paths: Set[str] = set()
            for index, entry in enumerate(manifest["tests"]):
                if not isinstance(entry, dict):
                    raise ValueError(f"tests[{index}] must be an object")
                category = entry.get("category")
                resolved = _resolve_manifest_path(str(entry.get("path", "")), manifest_candidates)
                if category not in TEST_CATEGORIES:
                    raise ValueError(f"tests[{index}].category is invalid")
                if not resolved:
                    raise ValueError(f"tests[{index}].path does not uniquely identify an embedded Python test file")
                if resolved in seen_manifest_paths:
                    raise ValueError(f"test file '{resolved}' is assigned more than once")
                seen_manifest_paths.add(resolved)
                if resolved not in test_paths:
                    test_paths.append(resolved)
                explicit[resolved] = (category, f"validated manifest {manifest_path}")
                if category == "performance" and "threshold_ms" in entry:
                    threshold = entry["threshold_ms"]
                    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 < threshold <= 60000:
                        raise ValueError(f"tests[{index}].threshold_ms must be between 0 and 60000")
                    result.performance_thresholds_ms[resolved] = float(threshold)
        except (json.JSONDecodeError, ValueError) as exc:
            result.errors.append(f"{manifest_path}: {exc}")

    test_paths.sort()
    for path in test_paths:
        markers, marker_errors = _marker_categories(project_files[path])
        result.errors.extend(f"{path}: {message}" for message in marker_errors)
        path_declaration = _path_category(path)
        marker_declaration = next(iter(markers)) if len(markers) == 1 else None
        declarations: List[Tuple[str, str]] = []
        if path in explicit:
            declarations.append(explicit[path])
        if marker_declaration:
            declarations.append((marker_declaration, "pytest category marker"))
            result.has_explicit_metadata = True
        if path_declaration:
            declarations.append(path_declaration)
            result.has_explicit_metadata = True

        declared_categories = {category for category, _source in declarations}
        if len(declared_categories) > 1:
            result.errors.append(f"{path}: conflicting category declarations: {sorted(declared_categories)}")
        elif declarations:
            explicit[path] = declarations[0]

    if result.errors:
        return result

    if result.has_explicit_metadata:
        # Legacy/unclassified embedded tests remain unit tests, while explicitly
        # declared integration/performance files are removed from that set.
        for path in test_paths:
            category, source = explicit.get(path, ("unit", "legacy unclassified unit fallback"))
            result.assignments[path] = category
            result.sources[path] = source
    else:
        for path in test_paths:
            result.assignments[path] = "unit"
            result.sources[path] = "legacy project without category metadata"
    return result


def project_files_for_category(
    project_files: Optional[Dict[str, str]], category: str
) -> Optional[Dict[str, str]]:
    if not project_files:
        return project_files
    classification = classify_project_tests(project_files)
    if classification.errors:
        return {path: content for path, content in project_files.items() if not is_python_test_file(path)}
    selected = set(classification.paths_for(category))
    classified_tests = set(classification.assignments)
    return {
        path: content
        for path, content in project_files.items()
        if path not in classified_tests or path in selected
    }


def integration_boundary_evidence(project_files: Dict[str, str], paths: List[str]) -> Tuple[bool, List[str]]:
    """Require a declared integration suite to exercise project modules/boundaries."""
    project_modules: Set[str] = set()
    for path in project_files:
        normalized = path.replace("\\", "/")
        if normalized.endswith(".py") and not is_python_test_file(path):
            module = normalized[:-3].replace("/", ".")
            parts = module.split(".")
            # Include wrapper-independent suffixes such as app.gpa.
            for index in range(len(parts)):
                project_modules.add(".".join(parts[index:]).removesuffix(".__init__"))

    exercised: Set[str] = set()
    referenced: Set[str] = set()
    external_boundaries: Set[str] = set()
    boundary_roots = {"fastapi", "httpx", "requests", "sqlalchemy", "pymongo", "psycopg", "socket", "subprocess"}
    for path in paths:
        try:
            tree = ast.parse(project_files[path])
        except SyntaxError:
            continue
        imported_names: Dict[str, Tuple[str, bool]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                is_project = module in project_modules
                is_boundary = module.split(".")[0] in boundary_roots
                if is_project or is_boundary:
                    for alias in node.names:
                        imported_names[alias.asname or alias.name] = (module, is_boundary)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    is_project = module in project_modules
                    is_boundary = module.split(".")[0] in boundary_roots
                    if is_project or is_boundary:
                        imported_names[alias.asname or module.split(".")[0]] = (module, is_boundary)

        # Imports alone are not integration evidence. Require actual calls across
        # project modules or through a recognized external boundary.
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in imported_names:
                module, is_boundary = imported_names[node.id]
                if not is_boundary:
                    referenced.add(module)
            if not isinstance(node, ast.Call):
                continue
            call_root = node.func
            while isinstance(call_root, ast.Attribute):
                call_root = call_root.value
            if isinstance(call_root, ast.Name) and call_root.id in imported_names:
                module, is_boundary = imported_names[call_root.id]
                if is_boundary:
                    external_boundaries.add(module.split(".")[0])
                else:
                    exercised.add(module)

        # A submitted application object passed into a called TestClient or
        # similar boundary exercises that application/boundary pair.
        if external_boundaries:
            exercised.update(referenced)

    evidence = sorted([f"project-module:{item}" for item in exercised] + [f"boundary:{item}" for item in external_boundaries])
    return len(exercised) >= 2 or (len(exercised) >= 1 and bool(external_boundaries)), evidence


def performance_workload_evidence(project_files: Dict[str, str], paths: List[str]) -> Tuple[bool, str]:
    combined = "\n".join(project_files[path] for path in paths)
    has_clock = bool(re.search(r"\btime\.(?:perf_counter|perf_counter_ns|monotonic|monotonic_ns)\s*\(", combined))
    has_samples = bool(re.search(r"\b(?:samples?|latencies|durations)(?:_ms)?\s*=", combined))
    has_structured_output = bool(
        re.search(
            r"(?:[A-Z][A-Z0-9_]*_PERFORMANCE|INTELISE_PERFORMANCE).*sample_(?:count|size)=.*p95_ms=.*(?:threshold_ms=)",
            combined,
            re.DOTALL,
        )
    )
    if not has_clock:
        return False, "The declared performance suite has no supported monotonic timing API."
    if not has_samples:
        return False, "The declared performance suite does not collect repeated latency samples."
    if not has_structured_output:
        return False, "The declared performance suite does not emit supported sample_count/p95_ms/threshold_ms evidence."
    return True, "Authorized repeated workload with monotonic timing and structured measurement evidence."
