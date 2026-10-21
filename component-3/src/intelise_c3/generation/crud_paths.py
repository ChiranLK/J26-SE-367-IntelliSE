"""Expected generated paths and identities derived from a CrudApplicationSpec."""

from __future__ import annotations

from intelise_c3.domain.crud_spec import CrudApplicationSpec, CrudEntitySpec
from intelise_c3.domain.generation import GeneratedArtifactType

SHARED_MODULES: dict[str, tuple[str, GeneratedArtifactType]] = {
    "backend/src/app.js": ("express-application", GeneratedArtifactType.API),
    "backend/src/db/schema.sql": ("crud-database-schema", GeneratedArtifactType.DATABASE),
    "backend/package.json": ("backend-package", GeneratedArtifactType.CONFIGURATION),
    "frontend/package.json": ("frontend-package", GeneratedArtifactType.CONFIGURATION),
    "frontend/index.html": ("frontend-entry-document", GeneratedArtifactType.FRONTEND),
    "frontend/src/main.jsx": ("frontend-bootstrap", GeneratedArtifactType.FRONTEND),
    "frontend/src/App.jsx": ("crud-application-shell", GeneratedArtifactType.FRONTEND),
    "api/openapi.yaml": ("crud-openapi-definition", GeneratedArtifactType.API),
}


def entity_backend_paths(entity: CrudEntitySpec) -> dict[str, tuple[str, GeneratedArtifactType]]:
    stem = entity.variable_name
    name = entity.class_name
    return {
        f"backend/src/routes/{stem}Routes.js": (f"{stem}-routes", GeneratedArtifactType.API),
        f"backend/src/controllers/{stem}Controller.js": (
            f"{stem}-controller",
            GeneratedArtifactType.CONTROLLER,
        ),
        f"backend/src/services/{stem}Service.js": (
            f"{stem}-service",
            GeneratedArtifactType.BUSINESS_LOGIC,
        ),
        f"backend/src/repositories/{stem}Repository.js": (
            f"{stem}-repository-seam",
            GeneratedArtifactType.REPOSITORY,
        ),
        f"backend/tests/{stem}Service.test.js": (
            f"{stem}-service-unit-test",
            GeneratedArtifactType.TEST,
        ),
    }


def entity_frontend_paths(entity: CrudEntitySpec) -> dict[str, tuple[str, GeneratedArtifactType]]:
    stem = entity.variable_name
    name = entity.class_name
    return {
        f"frontend/src/pages/{name}Page.jsx": (f"{stem}-page", GeneratedArtifactType.FRONTEND),
        f"frontend/src/components/{name}Form.jsx": (
            f"{stem}-form-component",
            GeneratedArtifactType.FRONTEND,
        ),
        f"frontend/src/components/{name}List.jsx": (
            f"{stem}-list-component",
            GeneratedArtifactType.FRONTEND,
        ),
        f"frontend/src/api/{stem}.js": (f"{stem}-api-client", GeneratedArtifactType.API),
    }


def expected_module_map(spec: CrudApplicationSpec) -> dict[str, tuple[str, GeneratedArtifactType]]:
    """Manifest-relative paths that must exist for this spec (source of truth)."""
    modules = dict(SHARED_MODULES)
    for entity in spec.entities:
        modules.update(entity_backend_paths(entity))
        modules.update(entity_frontend_paths(entity))
    return modules
