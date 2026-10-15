"""Allowlist and output validation for model-proposed module patches.

The model may propose exactly one complete module for exactly one authorized
path. Nothing here executes the proposed JavaScript; validation is textual and
structural. Rejection never falls back to rewriting the project.
"""

from dataclasses import dataclass
import json
import re
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from intelise_c3.domain.scoped_regeneration import PatchRejectionCode
from intelise_c3.generation.js_safety import allows_secure_uuid, inspect_javascript_safety
from intelise_c3.services.code_generation import REQUIRED_SERVICE_PATTERNS

SERVICE_PATH = "backend/src/services/taskService.js"
CONTROLLER_PATH = "backend/src/controllers/taskController.js"
REPOSITORY_PATH = "backend/src/repositories/taskRepository.js"

MAX_PATCH_CHARACTERS = 30000


@dataclass(frozen=True)
class PatchableModule:
    relative_path: str
    label: str
    required_interface: dict[str, re.Pattern[str]]
    forbidden: dict[str, re.Pattern[str]]


def _method(name: str, parameters: str) -> re.Pattern[str]:
    return re.compile(rf"\b{name}\s*\(\s*{parameters}\s*\)\s*\{{")


PATCHABLE_MODULES: dict[str, PatchableModule] = {
    SERVICE_PATH: PatchableModule(
        SERVICE_PATH,
        "task business-logic service",
        dict(REQUIRED_SERVICE_PATTERNS),
        {},
    ),
    CONTROLLER_PATH: PatchableModule(
        CONTROLLER_PATH,
        "task HTTP controller",
        {
            "export function createTaskController(service)": re.compile(
                r"^\s*export\s+function\s+createTaskController\s*\(\s*service\s*\)",
                re.MULTILINE,
            ),
            "handler list": re.compile(r"\blist\s*:"),
            "handler create": re.compile(r"\bcreate\s*:"),
            "handler update": re.compile(r"\bupdate\s*:"),
            "handler remove": re.compile(r"\bremove\s*:"),
            "service.list()": re.compile(r"service\.list\s*\("),
            "service.create(...)": re.compile(r"service\.create\s*\("),
            "service.update(...)": re.compile(r"service\.update\s*\("),
            "service.remove(...)": re.compile(r"service\.remove\s*\("),
        },
        {"direct repository access": re.compile(r"\brepository\b", re.IGNORECASE)},
    ),
    REPOSITORY_PATH: PatchableModule(
        REPOSITORY_PATH,
        "in-memory task repository seam",
        {
            "export class InMemoryTaskRepository": re.compile(
                r"^\s*export\s+class\s+InMemoryTaskRepository\b", re.MULTILINE
            ),
            "list()": _method("list", ""),
            "findById(id)": _method("findById", "id"),
            "create(task)": _method("create", "task"),
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

PATCHABLE_PATHS = frozenset(PATCHABLE_MODULES)


class PatchRejection(Exception):
    """A model proposal was rejected without changing any file."""

    def __init__(self, code: PatchRejectionCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _RepairArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Annotated[str, Field(min_length=1, max_length=240)]
    content: Annotated[str, Field(min_length=1, max_length=MAX_PATCH_CHARACTERS)]


def validate_repair_output(
    output_text: str,
    *,
    authorized_path: str,
    current_source: str,
) -> str:
    """Return the normalized replacement module or raise ``PatchRejection``."""
    module = PATCHABLE_MODULES.get(authorized_path)
    if module is None:
        raise PatchRejection(
            PatchRejectionCode.PATCH_PATH_NOT_AUTHORIZED,
            "The authorized module is not in the patch allowlist.",
        )
    try:
        parsed = _RepairArtifact.model_validate(json.loads(output_text))
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exception:
        raise PatchRejection(
            PatchRejectionCode.INVALID_MODEL_OUTPUT,
            "Model output must be one JSON object with only non-empty path and content.",
        ) from exception
    if not parsed.content.strip():
        raise PatchRejection(
            PatchRejectionCode.INVALID_MODEL_OUTPUT, "Model content must not be blank."
        )

    path = PurePosixPath(parsed.path)
    if (
        "\\" in parsed.path
        or path.is_absolute()
        or ".." in path.parts
        or ":" in path.parts[0]
        or path.as_posix() != parsed.path
    ):
        raise PatchRejection(
            PatchRejectionCode.UNSAFE_PATCH_PATH,
            "The proposed path is not a safe relative POSIX path.",
        )
    if parsed.path != authorized_path:
        raise PatchRejection(
            PatchRejectionCode.PATCH_PATH_NOT_AUTHORIZED,
            "The proposed path is not the single module authorized for this patch.",
        )
    safety = inspect_javascript_safety(
        parsed.content, allow_secure_uuid=allows_secure_uuid(authorized_path)
    )
    if not safety.accepted:
        # Conservative lexical policy (not a JavaScript sandbox). The message names
        # only static policy labels, never model-provided text.
        if safety.has_unsafe:
            raise PatchRejection(
                PatchRejectionCode.UNSAFE_PATCH_CONTENT,
                "The proposed module uses a forbidden capability (" + safety.describe() + ").",
            )
        raise PatchRejection(
            PatchRejectionCode.UNINSPECTABLE_PATCH_SYNTAX,
            "The proposed module uses syntax that cannot be safely inspected ("
            + safety.describe()
            + ").",
        )
    forbidden = tuple(
        label for label, pattern in module.forbidden.items() if pattern.search(parsed.content)
    )
    missing = tuple(
        label
        for label, pattern in module.required_interface.items()
        if pattern.search(parsed.content) is None
    )
    if forbidden or missing:
        raise PatchRejection(
            PatchRejectionCode.PATCH_INTERFACE_VIOLATION,
            "The proposed module breaks its required interface. "
            + (f"Forbidden: {', '.join(forbidden)}. " if forbidden else "")
            + (f"Missing: {', '.join(missing)}." if missing else ""),
        )
    normalized = parsed.content.rstrip() + "\n"
    if normalized == current_source.rstrip() + "\n":
        raise PatchRejection(
            PatchRejectionCode.PATCH_NO_OP,
            "The proposed module is identical to the current module.",
        )
    return normalized


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_PROMPT_MARKER = re.compile(
    r"(UNTRUSTED_DEFECT_DATA_JSON|CURRENT_SOURCE_(?:BEGIN|END)|TARGET_MODULE_|"
    r"REQUIRED_INTERFACE|PREVIOUS_ATTEMPT_REJECTED)",
    re.IGNORECASE,
)


def sanitize_untrusted_text(value: str | None, limit: int) -> str | None:
    """Reduce untrusted C4 text to bounded single-line data; it stays untrusted."""
    if value is None:
        return None
    collapsed = " ".join(_CONTROL.sub(" ", value).split())
    return _PROMPT_MARKER.sub("[PROMPT_MARKER_REMOVED]", collapsed)[:limit]
