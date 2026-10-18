"""Read-only structural verification for the generated React/Node Task MVP."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
import re

from fastapi import status

from intelise_c3.contracts.structural_verification import StructuralVerificationRequest
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation import (
    GeneratedArtifactType,
    GeneratedFileRecord,
    GenerationManifest,
)
from intelise_c3.domain.structural_verification import (
    StructuralFindingCategory,
    StructuralFindingStatus,
    StructuralVerificationFinding,
    StructuralVerificationReport,
    StructuralVerificationSummary,
)
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.generation.crud_templates import is_dynamic_crud_manifest
from intelise_c3.generation.templates import (
    API_TASK_CREATE,
    API_TASK_DELETE,
    API_TASK_LIST,
    API_TASK_UPDATE,
)
from intelise_c3.services.structural_finding import make_structural_finding
from intelise_c3.traceability.verification import ManifestVerificationService


RULE_SET_VERSION = "C3_TASK_MVP_STRUCTURAL_RULES_V1"

APP_PATH = "backend/src/app.js"
ROUTES_PATH = "backend/src/routes/taskRoutes.js"
CONTROLLER_PATH = "backend/src/controllers/taskController.js"
SERVICE_PATH = "backend/src/services/taskService.js"
REPOSITORY_PATH = "backend/src/repositories/taskRepository.js"
OPENAPI_PATH = "api/openapi.yaml"
FRONTEND_API_PATH = "frontend/src/api/tasks.js"
FRONTEND_APP_PATH = "frontend/src/App.jsx"
FRONTEND_LIST_PATH = "frontend/src/components/TaskList.jsx"
DATABASE_PATH = "backend/src/db/schema.sql"

_REQUIRED_MODULES = {
    APP_PATH: ("express-application", GeneratedArtifactType.API),
    ROUTES_PATH: ("task-routes", GeneratedArtifactType.API),
    CONTROLLER_PATH: ("task-controller", GeneratedArtifactType.CONTROLLER),
    SERVICE_PATH: ("task-service", GeneratedArtifactType.BUSINESS_LOGIC),
    REPOSITORY_PATH: ("task-repository-seam", GeneratedArtifactType.REPOSITORY),
    OPENAPI_PATH: ("task-openapi-definition", GeneratedArtifactType.API),
    FRONTEND_API_PATH: ("task-api-client", GeneratedArtifactType.API),
    FRONTEND_APP_PATH: ("task-application-shell", GeneratedArtifactType.FRONTEND),
    FRONTEND_LIST_PATH: ("task-list-component", GeneratedArtifactType.FRONTEND),
    DATABASE_PATH: ("task-database-schema", GeneratedArtifactType.DATABASE),
}

_API_POLICY = {
    API_TASK_LIST: ("GET", "/api/v1/tasks", "listTasks", "list"),
    API_TASK_CREATE: ("POST", "/api/v1/tasks", "createTask", "create"),
    API_TASK_UPDATE: ("PATCH", "/api/v1/tasks/{id}", "updateTask", "update"),
    API_TASK_DELETE: ("DELETE", "/api/v1/tasks/{id}", "deleteTask", "remove"),
}

_API_SHAPE_POLICY = {
    API_TASK_LIST: (None, "Task[]"),
    API_TASK_CREATE: ("CreateTaskRequest", "Task"),
    API_TASK_UPDATE: ("UpdateTaskRequest", "Task"),
    API_TASK_DELETE: (None, None),
}

_REPOSITORY_SIGNATURES = {
    "list": (),
    "findById": ("id",),
    "create": ("task",),
    "update": ("id", "changes"),
    "remove": ("id",),
}

_SERVICE_SIGNATURES = {
    "list": (),
    "create": ("title",),
    "update": ("id", "changes"),
    "remove": ("id",),
}

_REPOSITORY_USAGE_PATTERNS = {
    "repository.list()": re.compile(r"repository\.list\s*\(\s*\)"),
    "repository.findById(id)": re.compile(r"repository\.findById\s*\(\s*id\s*\)"),
    "repository.create(task)": re.compile(r"repository\.create\s*\(\s*task\s*\)"),
    "repository.update(id, changes)": re.compile(
        r"repository\.update\s*\(\s*id\s*,\s*\{\s*completed\s*:"
    ),
    "repository.remove(id)": re.compile(r"repository\.remove\s*\(\s*id\s*\)"),
}


class StructuralVerificationService:
    """Verify supported structures without importing or executing generated code."""

    def __init__(
        self,
        verifier: ManifestVerificationService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._verifier = verifier
        self._clock = clock or (lambda: datetime.now(UTC))

    def verify(
        self,
        request: StructuralVerificationRequest,
    ) -> StructuralVerificationReport:
        workspace = self._verifier.verify(
            request.manifest,
            request.workspace_relative_path,
        )
        design_hash = canonical_sha256(request.design_context)
        self._validate_design_binding(request.manifest, request.design_context, design_hash)
        self._validate_supported_stack(request.manifest)

        if self._uses_dynamic_crud_rules(request.manifest):
            return self._verify_dynamic(request, workspace, design_hash)

        records = {record.relative_path: record for record in request.manifest.files}
        contents = self._read_relevant_sources(workspace, records)
        findings = (
            self._check_design_boundary(request.manifest, request.design_context, records),
            self._check_module_boundary(request.manifest, records),
            self._check_layering(request.manifest, records, contents),
            self._check_express_flow(request.manifest, records, contents),
            self._check_openapi(request.manifest, records, contents),
            self._check_frontend_client(request.manifest, records, contents),
            self._check_repository_contract(request.manifest, records, contents),
            self._check_database_artifacts(
                request.manifest,
                request.design_context,
                records,
                contents,
            ),
            self._review_required_limitations(request.manifest, records),
        )
        fail_count = sum(item.status is StructuralFindingStatus.FAIL for item in findings)
        review_count = sum(
            item.status is StructuralFindingStatus.REVIEW_REQUIRED for item in findings
        )
        pass_count = sum(item.status is StructuralFindingStatus.PASS for item in findings)
        overall = (
            StructuralFindingStatus.FAIL
            if fail_count
            else StructuralFindingStatus.REVIEW_REQUIRED
            if review_count
            else StructuralFindingStatus.PASS
        )
        source = request.manifest.source
        return StructuralVerificationReport(
            generation_run_id=request.manifest.generation_run_id,
            project_id=source.project_id,
            srs_version=source.srs_version,
            uml_version=source.uml_version,
            source_contract_versions=source.source_contract_versions,
            requirement_ids=source.requirement_ids,
            uml_ids=source.uml_ids,
            artifact_digest_sha256=request.manifest.artifact_digest_sha256,
            evidence_digest_sha256=request.manifest.run_evidence.evidence_digest_sha256,
            design_context_sha256=design_hash,
            verified_at_utc=self._clock().astimezone(UTC).isoformat(),
            overall_status=overall,
            summary=StructuralVerificationSummary(
                pass_count=pass_count,
                fail_count=fail_count,
                review_required_count=review_count,
            ),
            findings=findings,
        )

    @staticmethod
    def _validate_design_binding(
        manifest: GenerationManifest,
        design: DesignContext,
        design_hash: str,
    ) -> None:
        if design_hash != manifest.run_evidence.input_hashes.design_context_sha256:
            StructuralVerificationService._fail(
                "DESIGN_CONTEXT_DIGEST_MISMATCH",
                "design_context",
                "The supplied DesignContext does not match the generation-run evidence.",
            )
        source = manifest.source
        expected_requirements = tuple(item.requirement_id for item in design.requirements)
        expected_uml = tuple(item.uml_id for item in design.source_uml_elements)
        expected_anchor_ids = tuple(item.anchor_id for item in design.requirement_uml_anchors)
        identity_matches = (
            design.project_id == source.project_id
            and design.srs_version == source.srs_version
            and design.uml_version == source.uml_version
            and design.design_context_version == source.design_context_version
            and design.generation_context_version == source.generation_context_version
            and design.source_contract_versions == source.source_contract_versions
            and design.upstream_provenance.c1_approval_provenance_ref
            == source.c1_approval_provenance_ref
            and design.upstream_provenance.c1_validation_report_ref
            == source.c1_validation_report_ref
            and design.upstream_provenance.c2_validation_report_ref
            == source.c2_validation_report_ref
            and expected_requirements == source.requirement_ids
            and expected_uml == source.uml_ids
            and expected_anchor_ids == source.design_anchor_ids
            and design.requirement_uml_anchors == source.requirement_uml_anchors
            and design.ui_artifacts == source.ui_artifacts
        )
        if not identity_matches:
            StructuralVerificationService._fail(
                "DESIGN_CONTEXT_IDENTITY_MISMATCH",
                "design_context",
                "DesignContext identities or provenance differ from the verified manifest.",
            )

    @staticmethod
    def _uses_dynamic_crud_rules(manifest: GenerationManifest) -> bool:
        return is_dynamic_crud_manifest(manifest)

    def _verify_dynamic(
        self,
        request: StructuralVerificationRequest,
        workspace: Path,
        design_hash: str,
    ) -> StructuralVerificationReport:
        from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder
        from intelise_c3.services.dynamic_structural_verification import (
            DYNAMIC_RULE_SET_VERSION,
            DynamicStructuralVerificationService,
        )

        spec = CrudApplicationSpecBuilder().build(request.design_context)
        records = {record.relative_path: record for record in request.manifest.files}
        findings = DynamicStructuralVerificationService().verify(
            manifest=request.manifest,
            design=request.design_context,
            spec=spec,
            workspace=workspace,
            records=records,
        )
        fail_count = sum(item.status is StructuralFindingStatus.FAIL for item in findings)
        review_count = sum(
            item.status is StructuralFindingStatus.REVIEW_REQUIRED for item in findings
        )
        pass_count = sum(item.status is StructuralFindingStatus.PASS for item in findings)
        overall = (
            StructuralFindingStatus.FAIL
            if fail_count
            else StructuralFindingStatus.REVIEW_REQUIRED
            if review_count
            else StructuralFindingStatus.PASS
        )
        source = request.manifest.source
        return StructuralVerificationReport(
            rule_set_version=DYNAMIC_RULE_SET_VERSION,
            generation_run_id=request.manifest.generation_run_id,
            project_id=source.project_id,
            srs_version=source.srs_version,
            uml_version=source.uml_version,
            source_contract_versions=source.source_contract_versions,
            requirement_ids=source.requirement_ids,
            uml_ids=source.uml_ids,
            artifact_digest_sha256=request.manifest.artifact_digest_sha256,
            evidence_digest_sha256=request.manifest.run_evidence.evidence_digest_sha256,
            design_context_sha256=design_hash,
            verified_at_utc=self._clock().astimezone(UTC).isoformat(),
            overall_status=overall,
            summary=StructuralVerificationSummary(
                pass_count=pass_count,
                fail_count=fail_count,
                review_required_count=review_count,
            ),
            findings=findings,
        )

    @staticmethod
    def _validate_supported_stack(manifest: GenerationManifest) -> None:
        if (
            manifest.selected_stack_id != "react-nodejs"
            or manifest.selected_frontend != "REACT"
            or manifest.selected_backend != "NODE_JS"
        ):
            StructuralVerificationService._fail(
                "UNSUPPORTED_VERIFICATION_STACK",
                "manifest.selected_stack_id",
                "This rule set supports only the React + Node.js Task MVP.",
            )

    @staticmethod
    def _read_relevant_sources(
        workspace: Path,
        records: dict[str, GeneratedFileRecord],
    ) -> dict[str, str]:
        contents: dict[str, str] = {}
        for relative_path in _REQUIRED_MODULES:
            if relative_path not in records:
                continue
            try:
                contents[relative_path] = (workspace / relative_path).read_text(
                    encoding="utf-8"
                )
            except (OSError, UnicodeError) as exception:
                raise ApplicationError(
                    [
                        ErrorDetail(
                            code="UNREADABLE_GENERATED_SOURCE",
                            field=relative_path,
                            message="A verified structural source is not valid UTF-8 text.",
                        )
                    ],
                    status_code=status.HTTP_409_CONFLICT,
                ) from exception
        return contents

    def _check_design_boundary(
        self,
        manifest: GenerationManifest,
        design: DesignContext,
        records: dict[str, GeneratedFileRecord],
    ) -> StructuralVerificationFinding:
        expected_classes = {"Task", "TaskService", "TaskRepository"}
        observed_classes = {item.name for item in design.classes}
        missing_classes = expected_classes - observed_classes
        unsupported_classes = observed_classes - expected_classes
        task = next((item for item in design.classes if item.name == "Task"), None)
        attributes = {item.name for item in task.attributes} if task else set()
        missing_attributes = {"id", "title", "completed"} - attributes
        required_methods = {
            "TaskService": {"list", "create", "update", "remove"},
            "TaskRepository": {"list", "findById", "create", "update", "remove"},
        }
        missing_methods: list[str] = []
        for class_name, names in required_methods.items():
            parsed = next((item for item in design.classes if item.name == class_name), None)
            observed = {item.name for item in parsed.methods} if parsed else set()
            missing_methods.extend(
                f"{class_name}.{name}" for name in sorted(names - observed)
            )
        expected_relationships = {
            ("TaskService", "TaskRepository"),
            ("TaskRepository", "Task"),
        }
        observed_relationships = {
            (item.source_class, item.target_class) for item in design.relationships
        }
        missing_relationships = expected_relationships - observed_relationships
        unsupported_relationships = observed_relationships - expected_relationships
        if missing_classes or missing_attributes or missing_methods or missing_relationships:
            finding_status = StructuralFindingStatus.FAIL
            message = "The supported Task design boundary is incomplete."
        elif unsupported_classes or unsupported_relationships:
            finding_status = StructuralFindingStatus.REVIEW_REQUIRED
            message = "The design includes structures outside the narrow Task MVP rule set."
        else:
            finding_status = StructuralFindingStatus.PASS
            message = "The Task, service, repository, and relationship boundary is present."
        observed = tuple(
            sorted(
                [f"class:{name}" for name in observed_classes]
                + [f"attribute:Task.{name}" for name in attributes]
                + [f"relationship:{left}->{right}" for left, right in observed_relationships]
            )
        )
        expected = tuple(
            sorted(
                [f"class:{name}" for name in expected_classes]
                + [f"attribute:Task.{name}" for name in {"id", "title", "completed"}]
                + [f"relationship:{left}->{right}" for left, right in expected_relationships]
            )
        )
        return self._finding(
            manifest,
            records,
            finding_id="C3SV-DESIGN-001",
            rule_id="TASK_DESIGN_BOUNDARY_V1",
            category=StructuralFindingCategory.DESIGN,
            finding_status=finding_status,
            message=message,
            paths=(SERVICE_PATH, REPOSITORY_PATH, OPENAPI_PATH, DATABASE_PATH),
            expected=expected,
            observed=observed,
            remediation=(
                "Regenerate from a supported complete Task design or obtain researcher review."
                if finding_status is not StructuralFindingStatus.PASS
                else None
            ),
        )

    def _check_module_boundary(
        self,
        manifest: GenerationManifest,
        records: dict[str, GeneratedFileRecord],
    ) -> StructuralVerificationFinding:
        invalid: list[str] = []
        observed: list[str] = []
        for path, (module_identity, artifact_type) in _REQUIRED_MODULES.items():
            record = records.get(path)
            if record is None:
                invalid.append(f"missing:{path}")
                continue
            observed.append(f"{path}:{record.module_identity}:{record.artifact_type.value}")
            if record.module_identity != module_identity or record.artifact_type is not artifact_type:
                invalid.append(f"conflict:{path}")
        finding_status = (
            StructuralFindingStatus.FAIL if invalid else StructuralFindingStatus.PASS
        )
        return self._finding(
            manifest,
            records,
            finding_id="C3SV-MODULE-001",
            rule_id="TASK_REQUIRED_MODULES_V1",
            category=StructuralFindingCategory.MODULE,
            finding_status=finding_status,
            message=(
                "Required generated module identities are complete and consistent."
                if not invalid
                else "Required generated modules are missing or conflict with the manifest."
            ),
            paths=tuple(_REQUIRED_MODULES),
            expected=tuple(
                f"{path}:{identity}:{artifact_type.value}"
                for path, (identity, artifact_type) in _REQUIRED_MODULES.items()
            ),
            observed=tuple(sorted((*observed, *invalid))),
            remediation="Regenerate the missing or conflicting modules." if invalid else None,
        )

    def _check_layering(
        self,
        manifest: GenerationManifest,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        app = contents.get(APP_PATH, "")
        routes = contents.get(ROUTES_PATH, "")
        controller = contents.get(CONTROLLER_PATH, "")
        service = contents.get(SERVICE_PATH, "")
        repository = contents.get(REPOSITORY_PATH, "")
        violations: list[str] = []
        required_app_fragments = {
            "controller-import": "from './controllers/taskController.js'",
            "repository-import": "from './repositories/taskRepository.js'",
            "routes-import": "from './routes/taskRoutes.js'",
            "service-import": "from './services/taskService.js'",
            "repository-construction": "new InMemoryTaskRepository()",
            "repository-to-service": "createTaskService(repository)",
            "service-to-controller": "createTaskController(service)",
            "controller-to-routes": "createTaskRoutes(createTaskController(service))",
        }
        for label, fragment in required_app_fragments.items():
            if fragment not in app:
                violations.append(f"missing-wiring:{label}")
        if re.search(r"(?:from\s+['\"].*repositories/|\brepository\s*\.)", controller):
            violations.append("controller-direct-repository-access")
        if re.search(r"from\s+['\"].*services/", controller):
            violations.append("controller-bypasses-service-injection")
        if re.search(
            r"(?:from\s+['\"].*(?:services|repositories)/|\b(?:service|repository)\s*\.)",
            routes,
        ):
            violations.append("routes-bypass-controller")
        if re.search(r"(?:controllers/|routes/|repositories/)", service):
            violations.append("service-bypasses-injected-boundaries")
        if re.search(r"(?:controllers/|routes/|services/)", repository):
            violations.append("repository-depends-on-upper-layer")
        finding_status = (
            StructuralFindingStatus.FAIL if violations else StructuralFindingStatus.PASS
        )
        return self._finding(
            manifest,
            records,
            finding_id="C3SV-ARCH-001",
            rule_id="CONTROLLER_SERVICE_REPOSITORY_LAYERING_V1",
            category=StructuralFindingCategory.ARCHITECTURE,
            finding_status=finding_status,
            message=(
                "Controller -> Service -> Repository dependency direction is preserved."
                if not violations
                else "A required layer dependency is missing or bypassed."
            ),
            paths=(APP_PATH, ROUTES_PATH, CONTROLLER_PATH, SERVICE_PATH, REPOSITORY_PATH),
            expected=tuple(required_app_fragments),
            observed=tuple(sorted(violations)) or ("no-forbidden-dependency",),
            remediation="Restore injected layer boundaries and remove direct repository access."
            if violations
            else None,
        )

    def _check_express_flow(
        self,
        manifest: GenerationManifest,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        app = contents.get(APP_PATH, "")
        routes = contents.get(ROUTES_PATH, "")
        controller = contents.get(CONTROLLER_PATH, "")
        base_match = re.search(
            r"app\.use\(\s*['\"]([^'\"]+)['\"]\s*,\s*"
            r"createTaskRoutes\(createTaskController\(service\)\)\s*\)",
            app,
        )
        base_path = base_match.group(1) if base_match else ""
        route_matches = re.findall(
            r"router\.(get|post|patch|delete)\(\s*['\"]([^'\"]+)['\"]\s*,\s*"
            r"asyncHandler\(controller\.(\w+)\)\s*\)",
            routes,
            flags=re.IGNORECASE,
        )
        observed_routes = {
            (
                method.upper(),
                self._join_route(base_path, local_path),
                controller_method,
            )
            for method, local_path, controller_method in route_matches
        }
        expected_routes = {
            (method, path, controller_method)
            for method, path, _operation_name, controller_method in _API_POLICY.values()
        }
        controller_calls = set(re.findall(r"\bservice\.(list|create|update|remove)\s*\(", controller))
        expected_calls = {item[3] for item in _API_POLICY.values()}
        missing = expected_routes - observed_routes
        unexpected = observed_routes - expected_routes
        missing_calls = expected_calls - controller_calls
        finding_status = (
            StructuralFindingStatus.FAIL
            if missing or unexpected or missing_calls
            else StructuralFindingStatus.PASS
        )
        return self._finding(
            manifest,
            records,
            finding_id="C3SV-FLOW-001",
            rule_id="EXPRESS_ROUTE_CONTROLLER_SERVICE_FLOW_V1",
            category=StructuralFindingCategory.FLOW,
            finding_status=finding_status,
            message=(
                "Express routes call the expected controller and service operations."
                if finding_status is StructuralFindingStatus.PASS
                else "Express route, controller, or service call relationships conflict."
            ),
            paths=(APP_PATH, ROUTES_PATH, CONTROLLER_PATH, SERVICE_PATH),
            expected=tuple(sorted(self._format_route(item) for item in expected_routes)),
            observed=tuple(
                sorted(
                    [self._format_route(item) for item in observed_routes]
                    + [f"controller-call:{name}" for name in controller_calls]
                )
            ),
            remediation="Restore the declared route -> controller -> service operation mapping."
            if finding_status is StructuralFindingStatus.FAIL
            else None,
        )

    def _check_openapi(
        self,
        manifest: GenerationManifest,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        declared = {
            operation.operation_id: (
                operation.method,
                operation.route_path,
                operation.success_status,
                operation.request_schema,
                operation.success_response_schema,
            )
            for reference in manifest.api_references
            for operation in reference.operations
        }
        parsed = self._parse_openapi_operations(contents.get(OPENAPI_PATH, ""))
        problems: list[str] = []
        observed: list[str] = []
        for operation_id, (method, path, openapi_name, _controller) in _API_POLICY.items():
            declaration = declared.get(operation_id)
            operation = parsed.get((method, path))
            observed.append(
                f"{operation_id}:{method}:{path}:{operation[0] if operation else 'MISSING'}"
            )
            if declaration is None:
                problems.append(f"manifest-missing:{operation_id}")
                continue
            (
                declared_method,
                declared_path,
                success_status,
                request_schema,
                response_schema,
            ) = declaration
            if declared_method != method or declared_path != path:
                problems.append(f"manifest-conflict:{operation_id}")
            if (request_schema, response_schema) != _API_SHAPE_POLICY[operation_id]:
                problems.append(f"manifest-schema-conflict:{operation_id}")
            if operation is None or operation[0] != openapi_name:
                problems.append(f"openapi-missing-or-conflicting:{operation_id}")
            elif success_status not in operation[1]:
                problems.append(f"openapi-success-status-missing:{operation_id}:{success_status}")
        source = contents.get(OPENAPI_PATH, "")
        task_fields = self._schema_required_fields(source, "Task")
        if task_fields != {"id", "title", "completed"}:
            problems.append("openapi-task-schema-fields-conflict")
        if self._schema_required_fields(source, "CreateTaskRequest") != {"title"}:
            problems.append("openapi-create-request-fields-conflict")
        if self._schema_required_fields(source, "UpdateTaskRequest") != {"completed"}:
            problems.append("openapi-update-request-fields-conflict")
        finding_status = (
            StructuralFindingStatus.FAIL if problems else StructuralFindingStatus.PASS
        )
        return self._finding(
            manifest,
            records,
            finding_id="C3SV-API-001",
            rule_id="MANIFEST_OPENAPI_ALIGNMENT_V1",
            category=StructuralFindingCategory.API,
            finding_status=finding_status,
            message=(
                "Manifest API operations and OpenAPI paths, methods, IDs, and statuses align."
                if not problems
                else "Manifest API operations conflict with the OpenAPI definition."
            ),
            paths=(OPENAPI_PATH, ROUTES_PATH),
            expected=tuple(
                f"{operation_id}:{method}:{path}:{name}"
                for operation_id, (method, path, name, _controller) in _API_POLICY.items()
            ),
            observed=tuple(sorted((*observed, *problems))),
            remediation="Regenerate the OpenAPI contract and matching Express routes."
            if problems
            else None,
        )

    def _check_frontend_client(
        self,
        manifest: GenerationManifest,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        source = contents.get(FRONTEND_API_PATH, "")
        app_source = contents.get(FRONTEND_APP_PATH, "")
        list_source = contents.get(FRONTEND_LIST_PATH, "")
        patterns = {
            "base:/api/v1/tasks": re.compile(
                r"const\s+API_BASE\s*=\s*['\"]http://127\.0\.0\.1:3001/api/v1/tasks['\"]"
            ),
            "list:GET": re.compile(r"export\s+const\s+listTasks\s*=.*request\(API_BASE\)", re.DOTALL),
            "create:POST": re.compile(
                r"export\s+const\s+createTask\s*=.*?request\(API_BASE,\s*\{\s*method:\s*['\"]POST['\"]"
                r".*?JSON\.stringify\(task\)",
                re.DOTALL,
            ),
            "update:PATCH": re.compile(
                r"export\s+const\s+updateTask\s*=.*?request\(`\$\{API_BASE\}/\$\{id\}`"
                r".*?method:\s*['\"]PATCH['\"].*?JSON\.stringify\(task\)",
                re.DOTALL,
            ),
            "delete:DELETE": re.compile(
                r"export\s+const\s+deleteTask\s*=.*?request\(`\$\{API_BASE\}/\$\{id\}`"
                r".*?method:\s*['\"]DELETE['\"]",
                re.DOTALL,
            ),
            "response:204-null": re.compile(r"response\.status\s*===\s*204\s*\?\s*null"),
            "response:error-envelope": re.compile(r"payload\?\.error\?\.message"),
        }
        matched = [name for name, pattern in patterns.items() if pattern.search(source)]
        call_site_patterns = {
            "create-shape:title": re.compile(r"createTask\(\s*\{\s*title\s*\}\s*\)"),
            "update-shape:completed": re.compile(
                r"updateTask\(\s*task\.id\s*,\s*\{\s*completed\s*:"
            ),
            "delete-shape:id": re.compile(r"deleteTask\(\s*task\.id\s*\)"),
            "list-response:array": re.compile(r"listTasks\(\)\.then\(setTasks\)"),
        }
        matched.extend(
            name for name, pattern in call_site_patterns.items() if pattern.search(app_source)
        )
        response_fields = {name for name in ("id", "title", "completed") if f"task.{name}" in list_source}
        if response_fields == {"id", "title", "completed"}:
            matched.append("task-response-fields:id,title,completed")
        expected_checks = tuple((*patterns, *call_site_patterns, "task-response-fields:id,title,completed"))
        missing = tuple(name for name in expected_checks if name not in matched)
        finding_status = (
            StructuralFindingStatus.FAIL if missing else StructuralFindingStatus.PASS
        )
        return self._finding(
            manifest,
            records,
            finding_id="C3SV-UI-001",
            rule_id="REACT_API_CLIENT_ALIGNMENT_V1",
            category=StructuralFindingCategory.UI,
            finding_status=finding_status,
            message=(
                "The React API client uses the declared Task endpoints and HTTP methods."
                if not missing
                else "The React API client is missing or conflicts with declared API operations."
            ),
            paths=(FRONTEND_API_PATH, FRONTEND_APP_PATH, FRONTEND_LIST_PATH, OPENAPI_PATH),
            expected=expected_checks,
            observed=tuple(sorted((*matched, *(f"missing:{item}" for item in missing)))),
            remediation="Align the React client functions with the OpenAPI Task operations."
            if missing
            else None,
        )

    def _check_repository_contract(
        self,
        manifest: GenerationManifest,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        repository_source = contents.get(REPOSITORY_PATH, "")
        service_source = contents.get(SERVICE_PATH, "")
        repository_methods = self._parse_method_signatures(repository_source)
        service_methods = self._parse_method_signatures(service_source)
        problems: list[str] = []
        for name, parameters in _REPOSITORY_SIGNATURES.items():
            if repository_methods.get(name) != parameters:
                problems.append(f"repository-signature:{name}{parameters}")
        for name, parameters in _SERVICE_SIGNATURES.items():
            observed = service_methods.get(name)
            if observed is None or len(observed) != len(parameters):
                problems.append(f"service-signature:{name}/{len(parameters)}")
        usage = tuple(
            label
            for label, pattern in _REPOSITORY_USAGE_PATTERNS.items()
            if pattern.search(service_source)
        )
        missing_usage = tuple(
            label for label in _REPOSITORY_USAGE_PATTERNS if label not in usage
        )
        problems.extend(f"missing-usage:{item}" for item in missing_usage)
        finding_status = (
            StructuralFindingStatus.FAIL if problems else StructuralFindingStatus.PASS
        )
        observed = tuple(
            sorted(
                [
                    f"repository:{name}({','.join(parameters)})"
                    for name, parameters in repository_methods.items()
                ]
                + [
                    f"service:{name}({','.join(parameters)})"
                    for name, parameters in service_methods.items()
                    if name in _SERVICE_SIGNATURES
                ]
                + list(usage)
                + problems
            )
        )
        return self._finding(
            manifest,
            records,
            finding_id="C3SV-REPOSITORY-001",
            rule_id="TASK_REPOSITORY_INTERFACE_V1",
            category=StructuralFindingCategory.REPOSITORY,
            finding_status=finding_status,
            message=(
                "Repository signatures match the service's deterministic call contract."
                if not problems
                else "Repository signatures and service usage do not match."
            ),
            paths=(SERVICE_PATH, REPOSITORY_PATH),
            expected=tuple(
                f"repository:{name}({','.join(parameters)})"
                for name, parameters in _REPOSITORY_SIGNATURES.items()
            ),
            observed=observed,
            remediation="Restore the injected repository interface and matching service calls."
            if problems
            else None,
        )

    def _check_database_artifacts(
        self,
        manifest: GenerationManifest,
        design: DesignContext,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        source = contents.get(DATABASE_PATH, "")
        table_matches = set(
            re.findall(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)", source, re.IGNORECASE)
        )
        column_matches = {
            name: data_type.upper()
            for name, data_type in re.findall(
                r"^\s*(\w+)\s+(TEXT|INTEGER|REAL|BLOB)\b",
                source,
                flags=re.MULTILINE | re.IGNORECASE,
            )
        }
        expected_tables = {
            table.name
            for database in manifest.database_references
            for table in database.tables
        }
        expected_columns = {
            column.name: "INTEGER" if column.data_type == "INTEGER_BOOLEAN" else column.data_type
            for database in manifest.database_references
            for table in database.tables
            for column in table.columns
        }
        task = next((item for item in design.classes if item.name == "Task"), None)
        design_fields = {item.name for item in task.attributes} if task else set()
        problems: list[str] = []
        if table_matches != expected_tables:
            problems.append("database-table-conflict")
        if column_matches != expected_columns:
            problems.append("database-column-conflict")
        if design_fields != set(expected_columns):
            problems.append("design-database-field-conflict")
        finding_status = (
            StructuralFindingStatus.FAIL if problems else StructuralFindingStatus.PASS
        )
        return self._finding(
            manifest,
            records,
            finding_id="C3SV-DATABASE-001",
            rule_id="TASK_DATABASE_ARTIFACT_ALIGNMENT_V1",
            category=StructuralFindingCategory.DATABASE,
            finding_status=finding_status,
            message=(
                "Design fields, manifest database identities, and SQL script align."
                if not problems
                else "Database artifact identities conflict with design or SQL evidence."
            ),
            paths=(DATABASE_PATH, REPOSITORY_PATH, OPENAPI_PATH),
            expected=tuple(
                sorted(
                    [f"table:{name}" for name in expected_tables]
                    + [f"column:{name}:{kind}" for name, kind in expected_columns.items()]
                )
            ),
            observed=tuple(
                sorted(
                    [f"table:{name}" for name in table_matches]
                    + [f"column:{name}:{kind}" for name, kind in column_matches.items()]
                    + problems
                )
            ),
            remediation="Regenerate the SQL artifact from the accepted Task design."
            if problems
            else None,
        )

    def _review_required_limitations(
        self,
        manifest: GenerationManifest,
        records: dict[str, GeneratedFileRecord],
    ) -> StructuralVerificationFinding:
        return self._finding(
            manifest,
            records,
            finding_id="C3SV-LIMIT-001",
            rule_id="STATIC_VERIFICATION_LIMITS_V1",
            category=StructuralFindingCategory.LIMITATION,
            finding_status=StructuralFindingStatus.REVIEW_REQUIRED,
            message=(
                "Static structure cannot prove runtime behavior, semantic correctness, "
                "actual database persistence, test execution, or Component 4 readiness."
            ),
            paths=(SERVICE_PATH, REPOSITORY_PATH, DATABASE_PATH),
            expected=("independent-runtime-and-semantic-evidence",),
            observed=("static-source-and-manifest-evidence-only", "runtime-repository:IN_MEMORY"),
            remediation="Use independent Component 4 testing and approved isolated runtime validation.",
        )

    @staticmethod
    def _parse_method_signatures(source: str) -> dict[str, tuple[str, ...]]:
        methods: dict[str, tuple[str, ...]] = {}
        patterns = (
            re.compile(r"^\s*(?:async\s+)?([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\{", re.MULTILINE),
            re.compile(
                r"^\s*([A-Za-z_]\w*)\s*:\s*(?:async\s*)?\(([^)]*)\)\s*=>",
                re.MULTILINE,
            ),
        )
        for pattern in patterns:
            for name, parameters in pattern.findall(source):
                parsed = tuple(
                    parameter.strip().strip("{} ")
                    for parameter in parameters.split(",")
                    if parameter.strip()
                )
                methods[name] = parsed
        return methods

    @staticmethod
    def _parse_openapi_operations(
        source: str,
    ) -> dict[tuple[str, str], tuple[str, frozenset[int]]]:
        operations: dict[tuple[str, str], tuple[str, frozenset[int]]] = {}
        current_path: str | None = None
        current_method: str | None = None
        current_name: str | None = None
        statuses: set[int] = set()

        def store() -> None:
            if current_path and current_method and current_name:
                operations[(current_method, current_path)] = (
                    current_name,
                    frozenset(statuses),
                )

        for line in source.splitlines():
            if line == "components:":
                store()
                break
            path_match = re.match(r"^  (/.*):\s*$", line)
            if path_match:
                store()
                current_path = path_match.group(1)
                current_method = None
                current_name = None
                statuses = set()
                continue
            method_match = re.match(r"^    (get|post|patch|delete):\s*$", line)
            if method_match:
                store()
                current_method = method_match.group(1).upper()
                current_name = None
                statuses = set()
                continue
            name_match = re.match(r"^      operationId:\s*(\w+)\s*$", line)
            if name_match and current_method:
                current_name = name_match.group(1)
                continue
            status_match = re.match(r"^        ['\"]?(\d{3})['\"]?:", line)
            if status_match and current_method:
                statuses.add(int(status_match.group(1)))
        else:
            store()
        return operations

    @staticmethod
    def _schema_required_fields(openapi_source: str, schema_name: str) -> set[str]:
        required = re.search(
            rf"(?ms)^    {re.escape(schema_name)}:\s.*?^      required:\s*\[([^]]+)\]",
            openapi_source,
        )
        if not required:
            return set()
        return {item.strip() for item in required.group(1).split(",") if item.strip()}

    @staticmethod
    def _join_route(base_path: str, local_path: str) -> str:
        if local_path == "/":
            return base_path
        normalized = local_path.replace(":id", "{id}")
        return f"{base_path.rstrip('/')}/{normalized.lstrip('/')}"

    @staticmethod
    def _format_route(route: tuple[str, str, str]) -> str:
        return ":".join(route)

    @staticmethod
    def _finding(
        manifest: GenerationManifest,
        records: dict[str, GeneratedFileRecord],
        *,
        finding_id: str,
        rule_id: str,
        category: StructuralFindingCategory,
        finding_status: StructuralFindingStatus,
        message: str,
        paths: tuple[str, ...],
        expected: tuple[str, ...],
        observed: tuple[str, ...],
        remediation: str | None,
    ) -> StructuralVerificationFinding:
        return make_structural_finding(
            manifest,
            records,
            finding_id=finding_id,
            rule_id=rule_id,
            category=category,
            finding_status=finding_status,
            message=message,
            paths=paths,
            expected=expected,
            observed=observed,
            remediation=remediation,
        )

    @staticmethod
    def _fail(code: str, field: str, message: str) -> None:
        raise ApplicationError(
            [ErrorDetail(code=code, field=field, message=message)],
            status_code=status.HTTP_409_CONFLICT,
        )
