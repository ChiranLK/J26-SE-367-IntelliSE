"""Preflight and command policy for isolated generated-CRUD validation.

This module does not invoke Docker. It validates the generated workspace before
any generated source is sent to a Docker build and constructs auditable command
arguments for the manual validation orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from intelise_c3.domain.crud_spec import CrudApplicationSpec, CrudScalarType
from intelise_c3.domain.generation import GenerationManifest
from intelise_c3.generation.crud_templates import is_dynamic_crud_manifest

_EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_LIFECYCLE_SCRIPTS = {
    "preinstall",
    "install",
    "postinstall",
    "prepare",
    "prepublish",
    "prepublishOnly",
}

_EXPECTED_PACKAGES = {
    "frontend": {
        "dependencies": {"react": "18.3.1", "react-dom": "18.3.1"},
        "devDependencies": {"@vitejs/plugin-react": "5.2.0", "vite": "8.3.4"},
        "scripts": {"dev": "vite", "build": "vite build"},
        "engines": {"node": ">=24.0.0 <25"},
    },
    "backend": {
        "dependencies": {"cors": "2.8.5", "express": "4.22.3"},
        "devDependencies": {"vitest": "4.1.12"},
        "scripts": {"start": "node src/app.js", "test": "vitest run"},
        "engines": {"node": ">=24.0.0 <25"},
    },
}


class DockerPreflightError(ValueError):
    """Generated input is not safe or consistent enough for container validation."""


@dataclass(frozen=True)
class DockerPreflightReport:
    policy_version: str
    inspected_file_count: int
    package_manifests: tuple[str, ...]
    api_operation_count: int
    database_table_count: int


def inspect_generated_workspace(
    workspace: Path,
    manifest: GenerationManifest,
    spec: CrudApplicationSpec,
) -> DockerPreflightReport:
    """Inspect dependencies, paths, source and API evidence without executing it."""
    resolved_workspace = workspace.resolve()
    if not is_dynamic_crud_manifest(manifest):
        raise DockerPreflightError("Only dynamic CRUD generator manifests are supported.")
    if manifest.execution_status != "NOT_EXECUTED":
        raise DockerPreflightError("Input manifest must describe an unexecuted generation run.")

    manifest_paths = {record.relative_path for record in manifest.files}
    for record in manifest.files:
        path = (resolved_workspace / record.relative_path).resolve()
        if resolved_workspace not in path.parents or path.is_symlink():
            raise DockerPreflightError(f"Unsafe generated path: {record.relative_path}")

    package_paths = []
    for area, expected in _EXPECTED_PACKAGES.items():
        relative = f"{area}/package.json"
        package_paths.append(relative)
        if relative not in manifest_paths:
            raise DockerPreflightError(f"Manifest is missing {relative}.")
        package = _read_json(resolved_workspace / relative)
        scripts = package.get("scripts", {})
        if not isinstance(scripts, dict):
            raise DockerPreflightError(f"{relative} scripts must be an object.")
        forbidden = sorted(_LIFECYCLE_SCRIPTS.intersection(scripts))
        if forbidden:
            raise DockerPreflightError(
                f"{relative} contains forbidden lifecycle scripts: {', '.join(forbidden)}."
            )
        for section in ("dependencies", "devDependencies"):
            actual = package.get(section, {})
            if actual != expected[section]:
                raise DockerPreflightError(
                    f"{relative} {section} differs from the reviewed allowlist."
                )
            if any(
                not isinstance(version, str) or not _EXACT_VERSION.fullmatch(version)
                for version in actual.values()
            ):
                raise DockerPreflightError(f"{relative} has an unpinned direct dependency.")
        if scripts != expected["scripts"]:
            raise DockerPreflightError(
                f"{relative} scripts differ from the reviewed command allowlist."
            )
        if package.get("engines") != expected["engines"]:
            raise DockerPreflightError(
                f"{relative} Node engine differs from the reviewed runtime range."
            )

    _validate_openapi(resolved_workspace, manifest, spec)
    _validate_sql(resolved_workspace, manifest, spec)
    return DockerPreflightReport(
        policy_version="C3_DOCKER_PREFLIGHT_V1",
        inspected_file_count=len(manifest.files),
        package_manifests=tuple(package_paths),
        api_operation_count=sum(
            len(reference.operations) for reference in manifest.api_references
        ),
        database_table_count=sum(
            len(reference.tables) for reference in manifest.database_references
        ),
    )


def restricted_runtime_command(image: str, container_name: str) -> tuple[str, ...]:
    """Return the fixed backend command used by the validation harness."""
    return (
        "docker",
        "run",
        "--detach",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=32m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "128",
        "--memory",
        "256m",
        "--cpus",
        "0.50",
        "--user",
        "1000:1000",
        "--restart",
        "no",
        image,
    )


def smoke_plan(spec: CrudApplicationSpec) -> dict[str, object]:
    """Create non-secret request data for the in-container CRUD smoke runner."""
    entities = []
    for entity in spec.entities:
        mutable = tuple(field for field in entity.fields if not field.generated)
        create_payload = {field.name: _sample_value(field.scalar_type) for field in mutable}
        patch_field = mutable[0]
        patch_payload = {patch_field.name: _updated_value(patch_field.scalar_type)}
        entities.append(
            {
                "name": entity.class_name,
                "collectionPath": f"/api/v1/{entity.route_segment}",
                "createPayload": create_payload,
                "patchPayload": patch_payload,
                "expectedFields": [field.name for field in entity.fields],
            }
        )
    return {"port": 3001, "entities": entities}


def _validate_openapi(
    workspace: Path,
    manifest: GenerationManifest,
    spec: CrudApplicationSpec,
) -> None:
    document = _read_json(workspace / "api/openapi.yaml")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise DockerPreflightError("OpenAPI paths are missing or malformed.")
    for reference in manifest.api_references:
        for operation in reference.operations:
            route = paths.get(operation.route_path)
            operation_doc = route.get(operation.method.casefold()) if isinstance(route, dict) else None
            if not isinstance(operation_doc, dict):
                raise DockerPreflightError(
                    f"OpenAPI is missing {operation.method} {operation.route_path}."
                )
            if operation_doc.get("operationId") != operation.operation_id:
                raise DockerPreflightError(
                    f"OpenAPI operationId mismatch for {operation.operation_id}."
                )
            responses = operation_doc.get("responses", {})
            if str(operation.success_status) not in responses:
                raise DockerPreflightError(
                    f"OpenAPI success response mismatch for {operation.operation_id}."
                )

    schemas = document.get("components", {}).get("schemas", {})
    for entity in spec.entities:
        schema = schemas.get(entity.class_name)
        if not isinstance(schema, dict):
            raise DockerPreflightError(f"OpenAPI schema missing for {entity.class_name}.")
        properties = schema.get("properties", {})
        expected = {field.name: _openapi_type(field.scalar_type) for field in entity.fields}
        observed = {
            name: value.get("type")
            for name, value in properties.items()
            if isinstance(value, dict)
        }
        if observed != expected:
            raise DockerPreflightError(
                f"OpenAPI field types differ from the CRUD spec for {entity.class_name}."
            )


def _validate_sql(
    workspace: Path,
    manifest: GenerationManifest,
    spec: CrudApplicationSpec,
) -> None:
    sql = (workspace / "backend/src/db/schema.sql").read_text(encoding="utf-8")
    if "Runtime repository mode is IN_MEMORY" not in sql:
        raise DockerPreflightError("SQL artifact does not state the IN_MEMORY boundary.")
    referenced_tables = {
        table.name
        for reference in manifest.database_references
        for table in reference.tables
    }
    expected_tables = {entity.table_name for entity in spec.entities}
    if referenced_tables != expected_tables:
        raise DockerPreflightError("Manifest database identities differ from the CRUD spec.")
    for table in expected_tables:
        if f"CREATE TABLE IF NOT EXISTS {table}" not in sql:
            raise DockerPreflightError(f"SQL definition missing for {table}.")


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exception:
        raise DockerPreflightError(f"Cannot inspect JSON file {path.name}.") from exception
    if not isinstance(value, dict):
        raise DockerPreflightError(f"JSON file {path.name} must contain an object.")
    return value


def _sample_value(scalar: CrudScalarType) -> str | int | float | bool:
    return {
        CrudScalarType.STRING: "Stage 2 sample",
        CrudScalarType.INTEGER: 7,
        CrudScalarType.NUMBER: 12.5,
        CrudScalarType.BOOLEAN: True,
        CrudScalarType.DATE: "2026-10-19",
    }[scalar]


def _updated_value(scalar: CrudScalarType) -> str | int | float | bool:
    return {
        CrudScalarType.STRING: "Stage 2 updated",
        CrudScalarType.INTEGER: 8,
        CrudScalarType.NUMBER: 13.5,
        CrudScalarType.BOOLEAN: False,
        CrudScalarType.DATE: "2026-10-20",
    }[scalar]


def _openapi_type(scalar: CrudScalarType) -> str:
    return {
        CrudScalarType.STRING: "string",
        CrudScalarType.INTEGER: "integer",
        CrudScalarType.NUMBER: "number",
        CrudScalarType.BOOLEAN: "boolean",
        CrudScalarType.DATE: "string",
    }[scalar]
