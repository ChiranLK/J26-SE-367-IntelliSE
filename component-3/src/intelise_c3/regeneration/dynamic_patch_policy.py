"""Patch allowlist derived from a verified CrudApplicationSpec (not filename heuristics)."""

from __future__ import annotations

import re

from intelise_c3.domain.crud_spec import CrudApplicationSpec, CrudEntitySpec
from intelise_c3.regeneration.patch_policy import PatchableModule, _method


def build_patchable_modules(spec: CrudApplicationSpec) -> dict[str, PatchableModule]:
    modules: dict[str, PatchableModule] = {}
    for entity in spec.entities:
        modules.update(_entity_patch_modules(entity))
    return modules


def _entity_patch_modules(entity: CrudEntitySpec) -> dict[str, PatchableModule]:
    stem = entity.variable_name
    name = entity.class_name
    service_path = f"backend/src/services/{stem}Service.js"
    controller_path = f"backend/src/controllers/{stem}Controller.js"
    repository_path = f"backend/src/repositories/{stem}Repository.js"
    return {
        service_path: PatchableModule(
            service_path,
            f"{entity.class_name} business-logic service",
            {
                f"export function create{name}Service": re.compile(
                    rf"^\s*export\s+function\s+create{name}Service\s*\(\s*repository\s*\)",
                    re.MULTILINE,
                ),
                "list": re.compile(r"\blist\s*:\s*"),
                "create": re.compile(r"\bcreate\s*:\s*"),
                "update": re.compile(r"\bupdate\s*:\s*"),
                "remove": re.compile(r"\bremove\s*:\s*"),
                "repository.list()": re.compile(r"repository\.list\s*\("),
                "repository.create": re.compile(r"repository\.create\s*\("),
                "repository.update": re.compile(r"repository\.update\s*\("),
                "repository.remove": re.compile(r"repository\.remove\s*\("),
            },
            {},
        ),
        controller_path: PatchableModule(
            controller_path,
            f"{entity.class_name} HTTP controller",
            {
                f"export function create{name}Controller": re.compile(
                    rf"^\s*export\s+function\s+create{name}Controller\s*\(\s*service\s*\)",
                    re.MULTILINE,
                ),
                "handler list": re.compile(r"\blist\s*:"),
                "handler create": re.compile(r"\bcreate\s*:"),
                "handler update": re.compile(r"\bupdate\s*:"),
                "handler remove": re.compile(r"\bremove\s*:"),
                "service.list()": re.compile(r"service\.list\s*\("),
                "service.create": re.compile(r"service\.create\s*\("),
                "service.update": re.compile(r"service\.update\s*\("),
                "service.remove": re.compile(r"service\.remove\s*\("),
            },
            {"direct repository access": re.compile(r"\brepository\b", re.IGNORECASE)},
        ),
        repository_path: PatchableModule(
            repository_path,
            f"in-memory {entity.class_name} repository seam",
            {
                f"export class InMemory{name}Repository": re.compile(
                    rf"^\s*export\s+class\s+InMemory{name}Repository\b",
                    re.MULTILINE,
                ),
                "list()": _method("list", ""),
                "findById(id)": _method("findById", "id"),
                "create(value)": _method("create", "value"),
                "update(id, changes)": _method("update", r"id\s*,\s*changes"),
                "remove(id)": _method("remove", "id"),
            },
            {
                "upper-layer dependency": re.compile(
                    r"(?:controllers/|routes/|services/)", re.IGNORECASE
                )
            },
        ),
    }
