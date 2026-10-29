"""Schema-driven structural verification for dynamic CRUD manifests."""

from __future__ import annotations

from pathlib import Path
import re

from intelise_c3.docker_validation import DockerPreflightError, inspect_generated_workspace
from intelise_c3.domain.crud_spec import CrudApplicationSpec, CrudEntitySpec
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation import GeneratedFileRecord, GenerationManifest
from intelise_c3.domain.structural_verification import (
    StructuralFindingCategory,
    StructuralFindingStatus,
    StructuralVerificationFinding,
)
from intelise_c3.generation.crud_paths import expected_module_map
from intelise_c3.services.structural_finding import make_structural_finding

DYNAMIC_RULE_SET_VERSION = "C3_DYNAMIC_CRUD_STRUCTURAL_RULES_V1"


class DynamicStructuralVerificationService:
    """Verify generated CRUD workspaces using CrudApplicationSpec + manifest evidence."""

    def verify(
        self,
        *,
        manifest: GenerationManifest,
        design: DesignContext,
        spec: CrudApplicationSpec,
        workspace: Path,
        records: dict[str, GeneratedFileRecord],
    ) -> tuple[StructuralVerificationFinding, ...]:
        contents = self._read_sources(workspace, records, spec)
        return (
            self._check_design_boundary(manifest, design, spec, records),
            self._check_module_boundary(manifest, spec, records),
            self._check_layering(manifest, spec, records, contents),
            self._check_api_contract(manifest, spec, records, contents),
            self._check_openapi_sql(manifest, spec, workspace, records),
            self._check_frontend_clients(manifest, spec, records, contents),
            self._check_repository_contract(manifest, spec, records, contents),
            self._review_required_limitations(manifest, spec, records),
        )

    @staticmethod
    def _read_sources(
        workspace: Path,
        records: dict[str, GeneratedFileRecord],
        spec: CrudApplicationSpec,
    ) -> dict[str, str]:
        expected = expected_module_map(spec)
        contents: dict[str, str] = {}
        for path in expected:
            if path not in records:
                continue
            contents[path] = (workspace / path).read_text(encoding="utf-8")
        return contents

    def _check_design_boundary(
        self,
        manifest: GenerationManifest,
        design: DesignContext,
        spec: CrudApplicationSpec,
        records: dict[str, GeneratedFileRecord],
    ) -> StructuralVerificationFinding:
        expected_entities = {entity.class_name for entity in spec.entities}
        design_entities = {
            item.name
            for item in design.classes
            if not item.name.endswith("Service") and not item.name.endswith("Repository")
        }
        missing = expected_entities - design_entities
        extra = design_entities - expected_entities
        if missing:
            status = StructuralFindingStatus.FAIL
            message = "DesignContext is missing entity classes required by the CRUD spec."
        elif extra:
            status = StructuralFindingStatus.REVIEW_REQUIRED
            message = "DesignContext includes classes outside the normalized CRUD spec."
        else:
            status = StructuralFindingStatus.PASS
            message = "Entity classes in the design align with the CRUD application spec."
        return make_structural_finding(
            manifest,
            records,
            finding_id="C3SV-DYN-DESIGN-001",
            rule_id="CRUD_DESIGN_BOUNDARY_V1",
            category=StructuralFindingCategory.DESIGN,
            finding_status=status,
            message=message,
            paths=tuple(f"entity:{name}" for name in sorted(expected_entities)),
            expected=tuple(sorted(f"class:{name}" for name in expected_entities)),
            observed=tuple(sorted(f"class:{name}" for name in design_entities)),
            remediation="Regenerate from a design that matches the verified CRUD spec."
            if status is not StructuralFindingStatus.PASS
            else None,
        )

    def _check_module_boundary(
        self,
        manifest: GenerationManifest,
        spec: CrudApplicationSpec,
        records: dict[str, GeneratedFileRecord],
    ) -> StructuralVerificationFinding:
        expected = expected_module_map(spec)
        invalid: list[str] = []
        observed: list[str] = []
        for path, (module_identity, artifact_type) in expected.items():
            record = records.get(path)
            if record is None:
                invalid.append(f"missing:{path}")
                continue
            observed.append(f"{path}:{record.module_identity}:{record.artifact_type.value}")
            if record.module_identity != module_identity or record.artifact_type is not artifact_type:
                invalid.append(f"conflict:{path}")
        status = StructuralFindingStatus.FAIL if invalid else StructuralFindingStatus.PASS
        return make_structural_finding(
            manifest,
            records,
            finding_id="C3SV-DYN-MODULE-001",
            rule_id="CRUD_REQUIRED_MODULES_V1",
            category=StructuralFindingCategory.MODULE,
            finding_status=status,
            message=(
                "Required CRUD modules are present and match manifest identities."
                if not invalid
                else "Required CRUD modules are missing or conflict with the manifest."
            ),
            paths=tuple(expected),
            expected=tuple(
                f"{path}:{identity}:{artifact_type.value}"
                for path, (identity, artifact_type) in expected.items()
            ),
            observed=tuple(sorted((*observed, *invalid))),
            remediation="Regenerate missing or conflicting modules from the shared renderer."
            if invalid
            else None,
        )

    def _check_layering(
        self,
        manifest: GenerationManifest,
        spec: CrudApplicationSpec,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        app = contents.get("backend/src/app.js", "")
        violations: list[str] = []
        for entity in spec.entities:
            stem = entity.variable_name
            name = entity.class_name
            fragments = (
                f"from './services/{stem}Service.js'",
                f"from './controllers/{stem}Controller.js'",
                f"from './routes/{stem}Routes.js'",
                f"create{name}Service(",
                f"create{name}Controller(",
                f"create{name}Routes(",
                f"app.use('/api/v1/{entity.route_segment}'",
            )
            for fragment in fragments:
                if fragment not in app:
                    violations.append(f"missing-wiring:{entity.class_name}:{fragment}")
            controller = contents.get(f"backend/src/controllers/{stem}Controller.js", "")
            if re.search(r"\brepository\b", controller, re.IGNORECASE):
                violations.append(f"controller-repository-access:{entity.class_name}")
        status = StructuralFindingStatus.FAIL if violations else StructuralFindingStatus.PASS
        return make_structural_finding(
            manifest,
            records,
            finding_id="C3SV-DYN-ARCH-001",
            rule_id="CRUD_LAYERING_V1",
            category=StructuralFindingCategory.ARCHITECTURE,
            finding_status=status,
            message=(
                "Per-entity controller/service/repository wiring is present in app.js."
                if not violations
                else "Layer wiring or isolation rules failed for one or more entities."
            ),
            paths=("backend/src/app.js",),
            expected=tuple(f"entity:{entity.class_name}" for entity in spec.entities),
            observed=tuple(sorted(violations)) or ("layering-ok",),
            remediation="Restore injected boundaries for each entity module set."
            if violations
            else None,
        )

    def _check_api_contract(
        self,
        manifest: GenerationManifest,
        spec: CrudApplicationSpec,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        problems: list[str] = []
        manifest_ops = {
            (operation.method, operation.route_path, operation.operation_id)
            for reference in manifest.api_references
            for operation in reference.operations
        }
        for entity in spec.entities:
            stem = entity.variable_name
            routes = contents.get(f"backend/src/routes/{stem}Routes.js", "")
            for method, route_path, operation_id in manifest_ops:
                if f"/api/v1/{entity.route_segment}" not in route_path:
                    continue
                if method == "GET" and entity.route_segment not in route_path:
                    continue
                token = method.casefold()
                if f"router.{token}" not in routes:
                    problems.append(f"missing-route-handler:{operation_id}")
        if len(manifest_ops) != sum(
            len(reference.operations) for reference in manifest.api_references
        ):
            problems.append("manifest-api-reference-count")
        status = StructuralFindingStatus.FAIL if problems else StructuralFindingStatus.PASS
        return make_structural_finding(
            manifest,
            records,
            finding_id="C3SV-DYN-API-001",
            rule_id="CRUD_API_CONTRACT_V1",
            category=StructuralFindingCategory.API,
            finding_status=status,
            message=(
                "Manifest API operations are reflected in generated route modules."
                if not problems
                else "Generated routes do not cover one or more manifest API operations."
            ),
            paths=tuple(
                f"backend/src/routes/{entity.variable_name}Routes.js" for entity in spec.entities
            ),
            expected=tuple(
                f"{method}:{path}:{operation_id}"
                for method, path, operation_id in sorted(manifest_ops)
            ),
            observed=tuple(sorted(problems)) or ("routes-match-manifest",),
            remediation="Align route modules with manifest api_references from the CRUD spec."
            if problems
            else None,
        )

    def _check_openapi_sql(
        self,
        manifest: GenerationManifest,
        spec: CrudApplicationSpec,
        workspace: Path,
        records: dict[str, GeneratedFileRecord],
    ) -> StructuralVerificationFinding:
        try:
            inspect_generated_workspace(workspace, manifest, spec)
            status = StructuralFindingStatus.PASS
            message = "OpenAPI paths, operation IDs, schemas, and SQL tables match the CRUD spec."
            observed = ("openapi-and-sql-consistent",)
        except DockerPreflightError as error:
            status = StructuralFindingStatus.FAIL
            message = str(error)
            observed = (f"preflight-error:{error}",)
        return make_structural_finding(
            manifest,
            records,
            finding_id="C3SV-DYN-OPENAPI-001",
            rule_id="CRUD_OPENAPI_SQL_V1",
            category=StructuralFindingCategory.API,
            finding_status=status,
            message=message,
            paths=("api/openapi.yaml", "backend/src/db/schema.sql"),
            expected=tuple(entity.table_name for entity in spec.entities),
            observed=observed,
            remediation="Regenerate OpenAPI and SQL artifacts from the shared CRUD renderer."
            if status is StructuralFindingStatus.FAIL
            else None,
        )

    def _check_frontend_clients(
        self,
        manifest: GenerationManifest,
        spec: CrudApplicationSpec,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        problems: list[str] = []
        for entity in spec.entities:
            path = f"frontend/src/api/{entity.variable_name}.js"
            source = contents.get(path, "")
            expected_base = f"/api/v1/{entity.route_segment}"
            if expected_base not in source:
                problems.append(f"missing-api-base:{entity.class_name}")
            plural = entity.plural_class_name
            name = entity.class_name
            for token in (f"list{plural}", f"create{name}", f"update{name}", f"delete{name}"):
                if token not in source:
                    problems.append(f"missing-client-fn:{entity.class_name}:{token}")
        status = StructuralFindingStatus.FAIL if problems else StructuralFindingStatus.PASS
        return make_structural_finding(
            manifest,
            records,
            finding_id="C3SV-DYN-UI-001",
            rule_id="CRUD_FRONTEND_CLIENT_V1",
            category=StructuralFindingCategory.UI,
            finding_status=status,
            message=(
                "Frontend API clients target the spec-derived collection paths."
                if not problems
                else "One or more frontend API clients are incomplete."
            ),
            paths=tuple(f"frontend/src/api/{entity.variable_name}.js" for entity in spec.entities),
            expected=tuple(f"/api/v1/{entity.route_segment}" for entity in spec.entities),
            observed=tuple(sorted(problems)) or ("frontend-clients-ok",),
            remediation="Align frontend clients with manifest API paths."
            if problems
            else None,
        )

    def _check_repository_contract(
        self,
        manifest: GenerationManifest,
        spec: CrudApplicationSpec,
        records: dict[str, GeneratedFileRecord],
        contents: dict[str, str],
    ) -> StructuralVerificationFinding:
        problems: list[str] = []
        for entity in spec.entities:
            path = f"backend/src/repositories/{entity.variable_name}Repository.js"
            source = contents.get(path, "")
            if "IN_MEMORY" not in source:
                problems.append(f"missing-in-memory-boundary:{entity.class_name}")
            for method in ("list", "findById", "create", "update", "remove"):
                if method not in source:
                    problems.append(f"missing-repo-method:{entity.class_name}:{method}")
            test_path = f"backend/tests/{entity.variable_name}Service.test.js"
            if test_path not in records:
                problems.append(f"missing-test-seam:{entity.class_name}")
        status = StructuralFindingStatus.FAIL if problems else StructuralFindingStatus.PASS
        return make_structural_finding(
            manifest,
            records,
            finding_id="C3SV-DYN-REPO-001",
            rule_id="CRUD_REPOSITORY_TEST_SEAM_V1",
            category=StructuralFindingCategory.REPOSITORY,
            finding_status=status,
            message=(
                "Repository seams and service unit-test hooks exist for each entity."
                if not problems
                else "Repository or test-seam evidence is incomplete."
            ),
            paths=tuple(
                f"backend/src/repositories/{entity.variable_name}Repository.js"
                for entity in spec.entities
            ),
            expected=("list", "findById", "create", "update", "remove", "IN_MEMORY"),
            observed=tuple(sorted(problems)) or ("repository-seams-ok",),
            remediation="Regenerate repository and test modules from the CRUD renderer."
            if problems
            else None,
        )

    def _review_required_limitations(
        self,
        manifest: GenerationManifest,
        spec: CrudApplicationSpec,
        records: dict[str, GeneratedFileRecord],
    ) -> StructuralVerificationFinding:
        return make_structural_finding(
            manifest,
            records,
            finding_id="C3SV-DYN-LIMIT-001",
            rule_id="CRUD_STATIC_LIMITS_V1",
            category=StructuralFindingCategory.LIMITATION,
            finding_status=StructuralFindingStatus.REVIEW_REQUIRED,
            message=(
                "Static CRUD verification cannot prove browser UI behavior, real database "
                "persistence, or independent Component 4 retesting."
            ),
            paths=("backend/src/db/schema.sql", "frontend/src/App.jsx"),
            expected=("runtime:IN_MEMORY", "ui:manual-or-isolated-preview"),
            observed=("static-manifest-and-source-evidence-only",),
            remediation="Use Docker validation and SIMULATED C4 workflows; UI remains REVIEW_REQUIRED.",
        )
