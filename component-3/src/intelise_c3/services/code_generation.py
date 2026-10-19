"""Controlled React + Node.js generation for FR-C3-03 and FR-C3-04."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from intelise_c3.contracts.generation import (
    CodeGenerationRequest,
    GenerationMode,
    ProvisionalApprovalStatus,
)
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.crud_spec import CrudApplicationSpec
from intelise_c3.domain.generation import (
    ApiArtifactReference,
    ApiOperationIdentity,
    ArtifactOrigin,
    DatabaseColumnIdentity,
    DatabaseArtifactReference,
    DatabaseTableIdentity,
    GeneratedArtifactType,
    GeneratedFileRecord,
    GenerationManifest,
    GenerationRunResult,
    RagRetrievalEvidence,
    RunEvidence,
    SourceIdentitySnapshot,
    StackApprovalEvidence,
    TestSeamReference,
    TraceEntityType,
    TraceLinkProvenance,
    TraceRelationType,
    TraceResolutionStatus,
    TraceReviewStatus,
    TraceabilityEvidence,
    TraceabilityLink,
)
from intelise_c3.domain.llm import LLMInferenceMetadata, LLMInferenceRequest
from intelise_c3.domain.stack_selection import GeneratorAvailability
from intelise_c3.generation.evidence import (
    build_input_hashes,
    compute_evidence_digest,
)
from intelise_c3.generation.crud_templates import (
    DYNAMIC_GENERATOR_VERSION,
    DYNAMIC_TEMPLATE_SET_VERSION,
    DYNAMIC_TRACEABILITY_MAPPING_POLICY_VERSION,
    render_crud_application,
)
from intelise_c3.generation.js_safety import (
    SAFETY_CHECKED_MODULES,
    allows_secure_uuid,
    inspect_javascript_safety,
)
from intelise_c3.generation.templates import (
    API_TASK_CREATE,
    API_TASK_DELETE,
    API_TASK_LIST,
    API_TASK_UPDATE,
    CAPABILITY_CREATE_LIST,
    CAPABILITY_REPOSITORY_BOUNDARY,
    CAPABILITY_UPDATE_DELETE,
    DB_TASK_COMPLETED_COLUMN,
    DB_TASK_ID_COLUMN,
    DB_TASK_TITLE_COLUMN,
    DB_TASKS_TABLE,
    GENERATOR_VERSION,
    TASK_REPOSITORY_SEAM,
    TEMPLATE_SET_VERSION,
    TRACEABILITY_MAPPING_POLICY_VERSION,
    TemplateArtifact,
    task_management_templates,
    template_task_service,
)
from intelise_c3.llm.client import LLMClient
from intelise_c3.prompts.code_generation import (
    MODEL_GENERATED_PATH,
    build_task_service_prompt,
)
from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder
from intelise_c3.rag.runtime import RagRuntime

_REQUIRED_SERVICE_PATTERNS = {
    "export function createTaskService(repository)": re.compile(
        r"^\s*export\s+function\s+createTaskService\s*\(\s*repository\s*\)",
    ),
    "repository.list()": re.compile(r"repository\.list\s*\("),
    "repository.create(task)": re.compile(
        r"repository\.create\s*\(\s*task\s*\)"
    ),
    "repository.findById(id)": re.compile(
        r"repository\.findById\s*\(\s*id\s*\)"
    ),
    "repository.update(id, safeChanges)": re.compile(
        r"repository\.update\s*\(\s*id\s*,\s*\{\s*"
        r"completed\s*:\s*changes\.completed\s*\}\s*\)"
    ),
    "repository.remove(id)": re.compile(
        r"repository\.remove\s*\(\s*id\s*\)"
    ),
    "title.trim()": re.compile(r"title\??\.trim\s*\(\s*\)"),
    "task creation fields": re.compile(
        r"const\s+task\s*=\s*\{"
        r"(?=[^}]*\bid\s*(?::|,))"
        r"(?=[^}]*\btitle\s*:\s*title\??\.trim\s*\(\s*\))"
        r"(?=[^}]*\bcompleted\s*:\s*false)"
        r"[^}]*\}",
        re.DOTALL,
    ),
    "secure local task identifier": re.compile(
        r"globalThis\.crypto\.randomUUID\s*\(\s*\)"
    ),
    "title type validation": re.compile(
        r"typeof\s+title\s*!==?\s*['\"]string['\"]"
    ),
    "id type validation": re.compile(
        r"typeof\s+id\s*!==?\s*['\"]string['\"]"
    ),
    "completed type validation": re.compile(
        r"typeof\s+changes\.completed\s*!==?\s*['\"]boolean['\"]"
    ),
    "HTTP 400 service error": re.compile(
        r"400\s*,\s*['\"]INVALID_TASK_INPUT['\"]"
    ),
    "HTTP 404 service error": re.compile(
        r"404\s*,\s*['\"]TASK_NOT_FOUND['\"]"
    ),
    "service error status metadata": re.compile(
        r"error\.statusCode\s*=\s*statusCode"
    ),
    "service error code metadata": re.compile(r"error\.code\s*=\s*code"),
}


# Public alias reused by scoped regeneration so that a patched module must pass
# the same interface rules as a freshly generated one. The host-access safety
# policy is shared through ``intelise_c3.generation.js_safety``.
REQUIRED_SERVICE_PATTERNS = _REQUIRED_SERVICE_PATTERNS


class _ModelGeneratedArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Annotated[str, Field(min_length=1, max_length=240)]
    content: Annotated[str, Field(min_length=1, max_length=30000)]

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Generated file content must not be blank.")
        return value


class CodeGenerationService:
    """Authorize, generate, validate, and write without executing artifacts."""

    def __init__(
        self,
        workspace_root: Path,
        llm_client: LLMClient | None,
        rag_runtime: RagRuntime | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._llm_client = llm_client
        self._rag_runtime = rag_runtime or RagRuntime.disabled()

    async def generate(self, request: CodeGenerationRequest) -> GenerationRunResult:
        """Create one isolated workspace or fail without template fallback."""
        self._validate_authorization(request)
        rag = self._rag_runtime.new_run()
        legacy_task = self._is_legacy_task_design(request.design_context)
        crud_spec = (
            None
            if legacy_task
            else CrudApplicationSpecBuilder().build(request.design_context)
        )
        llm_metadata: LLMInferenceMetadata | None = None
        prompt_request: LLMInferenceRequest | None = None

        if legacy_task:
            scaffold = list(task_management_templates())
            if request.mode is GenerationMode.LOCAL_LLM:
                if self._llm_client is None:
                    self._fail(
                        "LOCAL_LLM_CLIENT_REQUIRED",
                        "mode",
                        "LOCAL_LLM mode requires the configured local Ollama client.",
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                best_practices = rag.retrieve(
                    module_path=MODEL_GENERATED_PATH,
                    task=(
                        "Generate a Node.js service with injected repository dependencies, "
                        "validated input, consistent errors, and mockable test seams. "
                        "Accepted requirements: "
                        + "; ".join(
                            requirement.title
                            for requirement in request.design_context.requirements
                        )
                    ),
                    stack="node",
                    layer="service",
                    applied_to_prompt=True,
                )
                prompt_request = build_task_service_prompt(
                    request.design_context,
                    best_practice_block=best_practices,
                )
                llm_result = await self._llm_client.generate(prompt_request)
                service_artifact = self._parse_model_artifact(llm_result.output_text)
                llm_metadata = llm_result.metadata
                service_origin = ArtifactOrigin.LOCAL_LLM
            else:
                service_artifact = template_task_service()
                service_origin = ArtifactOrigin.TEMPLATE
            artifacts = tuple(scaffold + [service_artifact])
            api_references = self._api_references()
            database_references = self._database_references()
            test_seams = self._test_seams()
            generator_version = GENERATOR_VERSION
            template_set_version = TEMPLATE_SET_VERSION
            mapping_policy_version = TRACEABILITY_MAPPING_POLICY_VERSION
            manifest_spec: CrudApplicationSpec | None = None
        else:
            assert crud_spec is not None
            if request.mode is GenerationMode.LOCAL_LLM:
                self._fail(
                    "DYNAMIC_LOCAL_LLM_NOT_IMPLEMENTED",
                    "mode",
                    (
                        "Stage 1 dynamic CRUD generation is deterministic-only. "
                        "Local Ollama remains available for the legacy Task profile; "
                        "no template fallback was applied."
                    ),
                    status.HTTP_409_CONFLICT,
                )
            rendered = render_crud_application(crud_spec)
            artifacts = rendered.artifacts
            api_references = rendered.api_references
            database_references = rendered.database_references
            test_seams = rendered.test_seams
            service_origin = ArtifactOrigin.TEMPLATE
            generator_version = DYNAMIC_GENERATOR_VERSION
            template_set_version = DYNAMIC_TEMPLATE_SET_VERSION
            mapping_policy_version = DYNAMIC_TRACEABILITY_MAPPING_POLICY_VERSION
            manifest_spec = crud_spec

        self._record_template_retrievals(
            rag,
            artifacts,
            skip_paths={MODEL_GENERATED_PATH} if prompt_request is not None else set(),
        )

        self._validate_artifact_set(
            artifacts,
            allowed_paths={artifact.relative_path for artifact in artifacts},
        )
        run_id = str(uuid4())
        generated_at = datetime.now(UTC).isoformat()
        manifest = self._build_manifest(
            request=request,
            run_id=run_id,
            generated_at=generated_at,
            artifacts=artifacts,
            service_origin=service_origin,
            llm_metadata=llm_metadata,
            prompt_request=prompt_request,
            api_references=api_references,
            database_references=database_references,
            test_seams=test_seams,
            generator_version=generator_version,
            template_set_version=template_set_version,
            mapping_policy_version=mapping_policy_version,
            crud_spec=manifest_spec,
            rag_evidence=rag.evidence(),
        )
        relative_workspace = PurePosixPath(request.workspace_name) / run_id
        self._write_workspace(relative_workspace, artifacts, manifest)
        return GenerationRunResult(
            workspace_relative_path=relative_workspace.as_posix(),
            manifest_relative_path=(
                relative_workspace / "artifact-manifest.json"
            ).as_posix(),
            manifest=manifest,
        )

    @staticmethod
    def _is_legacy_task_design(design: object) -> bool:
        """Route the historical Task profile without changing its acceptance rules."""
        classes = getattr(design, "classes", ())
        by_name = {item.name: item for item in classes}
        task = by_name.get("Task")
        return (
            set(by_name) == {"Task", "TaskService", "TaskRepository"}
            and task is not None
            and tuple(attribute.name for attribute in task.attributes)
            == ("id", "title", "completed")
        )

    @staticmethod
    def _record_template_retrievals(
        rag: RagRuntime,
        artifacts: tuple[TemplateArtifact, ...],
        *,
        skip_paths: set[str],
    ) -> None:
        """Audit retrieval for deterministic modules without claiming prompt use."""
        mapping = {
            GeneratedArtifactType.FRONTEND: ("react", "ui"),
            GeneratedArtifactType.API: ("node", "api"),
            GeneratedArtifactType.CONTROLLER: ("node", "controller"),
            GeneratedArtifactType.BUSINESS_LOGIC: ("node", "service"),
            GeneratedArtifactType.REPOSITORY: ("node", "repository"),
            GeneratedArtifactType.DATABASE: ("node", "database"),
            GeneratedArtifactType.TEST: ("node", "test_seam"),
        }
        for artifact in sorted(artifacts, key=lambda item: item.relative_path):
            if artifact.relative_path in skip_paths or artifact.artifact_type not in mapping:
                continue
            stack, layer = mapping[artifact.artifact_type]
            rag.retrieve(
                module_path=artifact.relative_path,
                task=(
                    f"Generate {artifact.module_identity} as the {layer} module at "
                    f"{artifact.relative_path}."
                ),
                stack=stack,
                layer=layer,
                applied_to_prompt=False,
            )

    def _validate_authorization(self, request: CodeGenerationRequest) -> None:
        generation = request.generation_context
        design = request.design_context
        report = request.stack_selection_report
        errors: list[ErrorDetail] = []

        for field, left, right in (
            ("project_id", generation.project_id, design.project_id),
            ("srs_version", generation.srs_version, design.srs_version),
            ("uml_version", generation.uml_version, design.uml_version),
            (
                "generation_context_version",
                generation.context_version,
                design.generation_context_version,
            ),
        ):
            if left != right:
                errors.append(
                    ErrorDetail(
                        code="GENERATION_CONTEXT_MISMATCH",
                        field=f"design_context.{field}",
                        message=f"Generation and design {field} values must match.",
                    )
                )

        if design.requirements != generation.requirements:
            errors.append(
                ErrorDetail(
                    code="GENERATION_CONTEXT_MISMATCH",
                    field="design_context.requirements",
                    message="Design requirements must exactly preserve the accepted context.",
                )
            )
        if design.source_uml_elements != generation.uml_elements:
            errors.append(
                ErrorDetail(
                    code="GENERATION_CONTEXT_MISMATCH",
                    field="design_context.source_uml_elements",
                    message="Design UML identities must exactly preserve the accepted context.",
                )
            )
        if design.requirement_uml_anchors != generation.requirement_uml_anchors:
            errors.append(
                ErrorDetail(
                    code="GENERATION_CONTEXT_MISMATCH",
                    field="design_context.requirement_uml_anchors",
                    message="Design anchors must exactly preserve the accepted context.",
                )
            )
        if design.ui_artifacts != generation.ui_artifacts:
            errors.append(
                ErrorDetail(
                    code="GENERATION_CONTEXT_MISMATCH",
                    field="design_context.ui_artifacts",
                    message="Design UI references must exactly preserve the accepted context.",
                )
            )
        if (
            design.source_contract_versions != generation.source_contract_versions
            or design.upstream_provenance != generation.upstream_provenance
        ):
            errors.append(
                ErrorDetail(
                    code="GENERATION_CONTEXT_MISMATCH",
                    field="design_context.upstream_provenance",
                    message=(
                        "Design contract versions and provenance must exactly "
                        "preserve the accepted context."
                    ),
                )
            )

        requirement_ids = {item.requirement_id for item in design.requirements}
        anchored_ids = {
            anchor.requirement_id for anchor in design.requirement_uml_anchors
        }
        if not design.requirement_uml_anchors or requirement_ids - anchored_ids:
            errors.append(
                ErrorDetail(
                    code="MISSING_GENERATION_DESIGN_REFERENCE",
                    field="design_context.requirement_uml_anchors",
                    message=(
                        "Every generation requirement must retain at least one "
                        "C2 requirement-to-UML anchor."
                    ),
                )
            )
        known_uml_ids = {item.uml_id for item in design.source_uml_elements}
        if any(
            anchor.uml_id not in known_uml_ids
            for anchor in design.requirement_uml_anchors
        ):
            errors.append(
                ErrorDetail(
                    code="MISSING_GENERATION_DESIGN_REFERENCE",
                    field="design_context.requirement_uml_anchors",
                    message="Every design anchor must reference a preserved C2 UML ID.",
                )
            )
        if not design.ui_artifacts:
            errors.append(
                ErrorDetail(
                    code="MISSING_GENERATION_DESIGN_REFERENCE",
                    field="design_context.ui_artifacts",
                    message="At least one structured C2 UI or wireframe reference is required.",
                )
            )

        if (
            report.project_id != design.project_id
            or report.design_context_version != design.design_context_version
        ):
            errors.append(
                ErrorDetail(
                    code="STACK_REPORT_CONTEXT_MISMATCH",
                    field="stack_selection_report",
                    message="The stack report does not belong to this design context.",
                )
            )

        selected = report.selected_stack
        if selected.candidate.frontend != "REACT" or selected.candidate.backend != "NODE_JS":
            errors.append(
                ErrorDetail(
                    code="GENERATOR_NOT_IMPLEMENTED",
                    field="stack_selection_report.selected_stack",
                    message=(
                        "Only the explicitly selected React + Node.js generator "
                        "is implemented; no substitution is allowed."
                    ),
                )
            )
        elif (
            not selected.eligible
            or selected.generator_availability is not GeneratorAvailability.IMPLEMENTED
        ):
            errors.append(
                ErrorDetail(
                    code="GENERATOR_NOT_AVAILABLE",
                    field="stack_selection_report.selected_stack",
                    message="The selected React + Node.js generator is not available.",
                )
            )

        approval = request.stack_approval
        if (
            approval.status
            is not ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION
            or not approval.acknowledges_provisional_policy
        ):
            errors.append(
                ErrorDetail(
                    code="STACK_APPROVAL_REQUIRED",
                    field="stack_approval",
                    message=(
                        "Explicit provisional researcher approval and policy "
                        "acknowledgment are required before generation."
                    ),
                )
            )

        if errors:
            raise ApplicationError(errors, status_code=status.HTTP_409_CONFLICT)

    def _parse_model_artifact(self, output_text: str) -> TemplateArtifact:
        try:
            payload = json.loads(output_text)
            parsed = _ModelGeneratedArtifact.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as exception:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="INVALID_GENERATED_MODEL_OUTPUT",
                        field="ollama.response",
                        message=(
                            "Local Ollama output must be one non-empty structured "
                            "business-logic artifact."
                        ),
                    )
                ],
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exception

        self._validate_relative_path(parsed.path)
        if parsed.path != MODEL_GENERATED_PATH:
            self._fail(
                "GENERATED_PATH_NOT_ALLOWED",
                "ollama.response.path",
                f"The model may generate only '{MODEL_GENERATED_PATH}'.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        safety = inspect_javascript_safety(
            parsed.content, allow_secure_uuid=allows_secure_uuid(parsed.path)
        )
        if not safety.accepted:
            self._fail(
                "UNSAFE_GENERATED_CONTENT",
                "ollama.response.content",
                (
                    "The generated module is rejected by the conservative lexical "
                    f"safety policy ({safety.describe()}). This is not a JavaScript "
                    "sandbox."
                ),
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        missing_interfaces = tuple(
            label
            for label, pattern in _REQUIRED_SERVICE_PATTERNS.items()
            if pattern.search(parsed.content) is None
        )
        if missing_interfaces:
            self._fail(
                "INVALID_GENERATED_MODULE",
                "ollama.response.content",
                (
                    "The generated module does not implement the exact injected "
                    "repository service interface. Missing: "
                    + ", ".join(missing_interfaces)
                    + "."
                ),
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        template_metadata = template_task_service()
        return TemplateArtifact(
            relative_path=parsed.path,
            module_identity=template_metadata.module_identity,
            artifact_type=template_metadata.artifact_type,
            content=parsed.content,
            requirement_capabilities=template_metadata.requirement_capabilities,
            uml_class_names=template_metadata.uml_class_names,
            ui_related=template_metadata.ui_related,
            api_operation_ids=template_metadata.api_operation_ids,
            database_entity_ids=template_metadata.database_entity_ids,
            test_seam_ids=template_metadata.test_seam_ids,
        )

    def _validate_artifact_set(
        self,
        artifacts: tuple[TemplateArtifact, ...],
        *,
        allowed_paths: set[str] | None = None,
    ) -> None:
        if allowed_paths is None:
            allowed_paths = {
                artifact.relative_path for artifact in task_management_templates()
            } | {MODEL_GENERATED_PATH}
        seen: set[str] = set()
        for artifact in artifacts:
            self._validate_relative_path(artifact.relative_path)
            folded = artifact.relative_path.casefold()
            if folded in seen:
                self._fail(
                    "CONFLICTING_GENERATED_PATH",
                    "artifacts",
                    f"Generated path '{artifact.relative_path}' is duplicated.",
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                )
            seen.add(folded)
            if artifact.relative_path not in allowed_paths:
                self._fail(
                    "GENERATED_PATH_NOT_ALLOWED",
                    "artifacts",
                    f"Generated path '{artifact.relative_path}' is not allowlisted.",
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                )
            if not artifact.content.strip():
                self._fail(
                    "EMPTY_GENERATED_ARTIFACT",
                    "artifacts",
                    f"Generated artifact '{artifact.relative_path}' is empty.",
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                )
            if artifact.relative_path in SAFETY_CHECKED_MODULES or artifact.safety_checked:
                template_safety = inspect_javascript_safety(
                    artifact.content,
                    allow_secure_uuid=(
                        allows_secure_uuid(artifact.relative_path)
                        or artifact.allow_secure_uuid
                    ),
                )
                if not template_safety.accepted:
                    self._fail(
                        "UNSAFE_GENERATED_CONTENT",
                        "artifacts",
                        f"Generated artifact '{artifact.relative_path}' is rejected by "
                        f"the conservative lexical safety policy "
                        f"({template_safety.describe()}).",
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                    )

    @staticmethod
    def _validate_relative_path(relative_path: str) -> None:
        path = PurePosixPath(relative_path)
        if (
            not relative_path
            or "\\" in relative_path
            or path.is_absolute()
            or ".." in path.parts
            or ":" in path.parts[0]
            or path.as_posix() != relative_path
        ):
            CodeGenerationService._fail(
                "UNSAFE_GENERATED_PATH",
                "artifacts.relative_path",
                f"Generated path '{relative_path}' is not a safe relative path.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    def _build_manifest(
        self,
        *,
        request: CodeGenerationRequest,
        run_id: str,
        generated_at: str,
        artifacts: tuple[TemplateArtifact, ...],
        service_origin: ArtifactOrigin,
        llm_metadata: LLMInferenceMetadata | None,
        prompt_request: LLMInferenceRequest | None,
        api_references: tuple[ApiArtifactReference, ...],
        database_references: tuple[DatabaseArtifactReference, ...],
        test_seams: tuple[TestSeamReference, ...],
        generator_version: str,
        template_set_version: str,
        mapping_policy_version: str,
        crud_spec: CrudApplicationSpec | None,
        rag_evidence: RagRetrievalEvidence,
    ) -> GenerationManifest:
        source = request.design_context
        requirement_ids = tuple(item.requirement_id for item in source.requirements)
        uml_ids = tuple(item.uml_id for item in source.source_uml_elements)
        anchor_ids = tuple(item.anchor_id for item in source.requirement_uml_anchors)
        requirement_capabilities = self._classify_requirements(request)
        uml_ids_by_class = {
            parsed.name.casefold(): parsed.source_uml_id for parsed in source.classes
        }
        records: list[GeneratedFileRecord] = []
        for artifact in sorted(artifacts, key=lambda item: item.relative_path):
            content = self._normalized_content(artifact.content)
            encoded = content.encode("utf-8")
            origin = (
                service_origin
                if artifact.relative_path == MODEL_GENERATED_PATH
                else ArtifactOrigin.TEMPLATE
            )
            if artifact.explicit_trace_bindings:
                explicit_requirements = set(artifact.requirement_ids)
                explicit_uml = set(artifact.uml_ids)
                explicit_anchors = set(artifact.design_anchor_ids)
                file_requirement_ids = tuple(
                    requirement.requirement_id
                    for requirement in source.requirements
                    if requirement.requirement_id in explicit_requirements
                )
                file_anchors = tuple(
                    anchor
                    for anchor in source.requirement_uml_anchors
                    if anchor.anchor_id in explicit_anchors
                )
                file_uml_ids = tuple(
                    uml_id for uml_id in uml_ids if uml_id in explicit_uml
                )
                file_ui_ids = tuple(
                    ui.ui_id
                    for ui in source.ui_artifacts
                    if ui.ui_id in set(artifact.ui_artifact_ids)
                )
            else:
                file_requirement_ids = tuple(
                    requirement.requirement_id
                    for requirement in source.requirements
                    if requirement_capabilities.get(requirement.requirement_id)
                    in artifact.requirement_capabilities
                )
                file_anchors = tuple(
                    anchor
                    for anchor in source.requirement_uml_anchors
                    if anchor.requirement_id in file_requirement_ids
                )
                file_uml_candidates = {
                    *(anchor.uml_id for anchor in file_anchors),
                    *(
                        uml_ids_by_class[name.casefold()]
                        for name in artifact.uml_class_names
                        if name.casefold() in uml_ids_by_class
                    ),
                }
                file_uml_ids = tuple(
                    uml_id for uml_id in uml_ids if uml_id in file_uml_candidates
                )
                file_ui_ids = (
                    tuple(item.ui_id for item in source.ui_artifacts)
                    if artifact.ui_related
                    else ()
                )
            records.append(
                GeneratedFileRecord(
                    file_id=(
                        "FILE-"
                        + sha256(artifact.relative_path.encode("utf-8"))
                        .hexdigest()[:12]
                        .upper()
                    ),
                    relative_path=artifact.relative_path,
                    module_identity=artifact.module_identity,
                    artifact_type=artifact.artifact_type,
                    origin=origin,
                    sha256=sha256(encoded).hexdigest(),
                    size_bytes=len(encoded),
                    requirement_ids=file_requirement_ids,
                    uml_ids=file_uml_ids,
                    design_anchor_ids=tuple(
                        anchor.anchor_id for anchor in file_anchors
                    ),
                    ui_artifact_ids=file_ui_ids,
                    api_operation_ids=artifact.api_operation_ids,
                    database_entity_ids=artifact.database_entity_ids,
                    test_seam_ids=artifact.test_seam_ids,
                )
            )

        digest = sha256()
        for record in records:
            digest.update(record.relative_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(record.sha256.encode("ascii"))
            digest.update(b"\n")

        generation = request.generation_context
        approval = request.stack_approval
        selected = request.stack_selection_report.selected_stack.candidate
        traceability = self._build_traceability(
            request=request,
            run_id=run_id,
            records=tuple(records),
            requirement_capabilities=requirement_capabilities,
            api_references=api_references,
            database_references=database_references,
            mapping_policy_version=mapping_policy_version,
            crud_spec=crud_spec,
        )
        input_hashes = build_input_hashes(
            generation_context=generation,
            design_context=source,
            stack_selection_report=request.stack_selection_report,
            approval_input=approval,
            prompt_request=prompt_request,
        )
        prompt_template_version = (
            prompt_request.prompt_template_version
            if prompt_request is not None
            else None
        )
        evidence_digest = compute_evidence_digest(
            generation_run_id=run_id,
            input_hashes=input_hashes,
            prompt_template_version=prompt_template_version,
            generator_version=generator_version,
            template_set_version=template_set_version,
            llm_inference=llm_metadata,
            artifact_digest_sha256=digest.hexdigest(),
            rag_evidence=rag_evidence,
        )
        return GenerationManifest(
            generation_run_id=run_id,
            generated_at_utc=generated_at,
            generation_mode=request.mode.value,
            source=SourceIdentitySnapshot(
                project_id=generation.project_id,
                srs_version=generation.srs_version,
                uml_version=generation.uml_version,
                generation_context_version=generation.context_version,
                design_context_version=source.design_context_version,
                source_contract_versions=generation.source_contract_versions,
                requirement_ids=requirement_ids,
                uml_ids=uml_ids,
                design_anchor_ids=anchor_ids,
                requirement_uml_anchors=source.requirement_uml_anchors,
                ui_artifacts=source.ui_artifacts,
                c1_approval_provenance_ref=(
                    generation.upstream_provenance.c1_approval_provenance_ref
                ),
                c1_validation_report_ref=(
                    generation.upstream_provenance.c1_validation_report_ref
                ),
                c2_validation_report_ref=(
                    generation.upstream_provenance.c2_validation_report_ref
                ),
            ),
            selected_stack_id=selected.candidate_id,
            selected_frontend=selected.frontend,
            selected_backend=selected.backend,
            stack_approval=StackApprovalEvidence(
                status=approval.status.value,
                approval_reference=approval.approval_reference,
                approved_by=approval.approved_by,
                acknowledged_provisional_policy=(
                    approval.acknowledges_provisional_policy
                ),
            ),
            files=tuple(records),
            api_references=api_references,
            database_references=database_references,
            test_seams=test_seams,
            traceability=traceability,
            llm_inference=llm_metadata,
            artifact_digest_sha256=digest.hexdigest(),
            run_evidence=RunEvidence(
                input_hashes=input_hashes,
                prompt_template_version=prompt_template_version,
                generator_version=generator_version,
                template_set_version=template_set_version,
                rag=rag_evidence,
                evidence_digest_sha256=evidence_digest,
            ),
            trust_boundary=(
                "C3 preserved upstream references and a caller-asserted provisional "
                "stack approval, but did not authenticate the approving identity or "
                "prove authoritative C1/C2 approval."
            ),
        )

    @staticmethod
    def _classify_requirements(
        request: CodeGenerationRequest,
    ) -> dict[str, str | None]:
        """Apply narrow, documented MVP mappings; ambiguity stays unresolved."""
        classified: dict[str, str | None] = {}
        for requirement in request.design_context.requirements:
            title = requirement.title.casefold()
            if "create" in title and "list" in title:
                capability = CAPABILITY_CREATE_LIST
            elif "update" in title and "delete" in title:
                capability = CAPABILITY_UPDATE_DELETE
            elif "repository" in title:
                capability = CAPABILITY_REPOSITORY_BOUNDARY
            else:
                capability = None
            classified[requirement.requirement_id] = capability
        return classified

    @staticmethod
    def _api_references() -> tuple[ApiArtifactReference, ...]:
        return (
            ApiArtifactReference(
                reference_id="API-TASKS-V1",
                definition_path="api/openapi.yaml",
                operations=(
                    ApiOperationIdentity(
                        operation_id=API_TASK_LIST,
                        method="GET",
                        route_path="/api/v1/tasks",
                        success_response_schema="Task[]",
                        success_status=200,
                    ),
                    ApiOperationIdentity(
                        operation_id=API_TASK_CREATE,
                        method="POST",
                        route_path="/api/v1/tasks",
                        request_schema="CreateTaskRequest",
                        success_response_schema="Task",
                        success_status=201,
                    ),
                    ApiOperationIdentity(
                        operation_id=API_TASK_UPDATE,
                        method="PATCH",
                        route_path="/api/v1/tasks/{id}",
                        request_schema="UpdateTaskRequest",
                        success_response_schema="Task",
                        success_status=200,
                    ),
                    ApiOperationIdentity(
                        operation_id=API_TASK_DELETE,
                        method="DELETE",
                        route_path="/api/v1/tasks/{id}",
                        success_status=204,
                    ),
                ),
            ),
        )

    @staticmethod
    def _database_references() -> tuple[DatabaseArtifactReference, ...]:
        return (
            DatabaseArtifactReference(
                reference_id="DB-TASKS-V1",
                script_path="backend/src/db/schema.sql",
                tables=(
                    DatabaseTableIdentity(
                        table_id=DB_TASKS_TABLE,
                        name="tasks",
                        columns=(
                            DatabaseColumnIdentity(
                                column_id=DB_TASK_ID_COLUMN,
                                name="id",
                                data_type="TEXT",
                                nullable=False,
                                primary_key=True,
                            ),
                            DatabaseColumnIdentity(
                                column_id=DB_TASK_TITLE_COLUMN,
                                name="title",
                                data_type="TEXT",
                                nullable=False,
                            ),
                            DatabaseColumnIdentity(
                                column_id=DB_TASK_COMPLETED_COLUMN,
                                name="completed",
                                data_type="INTEGER_BOOLEAN",
                                nullable=False,
                            ),
                        ),
                    ),
                ),
            ),
        )

    @staticmethod
    def _test_seams() -> tuple[TestSeamReference, ...]:
        return (
            TestSeamReference(
                reference_id=TASK_REPOSITORY_SEAM,
                module_path="backend/src/repositories/taskRepository.js",
                description=(
                    "createTaskService receives a repository implementing list, "
                    "findById, create, update, and remove; tests can inject a mock."
                ),
            ),
        )

    def _build_traceability(
        self,
        *,
        request: CodeGenerationRequest,
        run_id: str,
        records: tuple[GeneratedFileRecord, ...],
        requirement_capabilities: dict[str, str | None],
        api_references: tuple[ApiArtifactReference, ...],
        database_references: tuple[DatabaseArtifactReference, ...],
        mapping_policy_version: str,
        crud_spec: CrudApplicationSpec | None,
    ) -> TraceabilityEvidence:
        source = request.design_context
        links: list[TraceabilityLink] = []

        def add_link(
            source_type: TraceEntityType,
            source_id: str,
            relation: TraceRelationType,
            target_type: TraceEntityType,
            target_id: str,
            *,
            evidence_kind: Literal[
                "SOURCE_C2_ANCHOR",
                "DETERMINISTIC_MAPPING_RULE",
                "UNRESOLVED_SOURCE_REFERENCE",
            ],
            rule: str,
            refs: tuple[str, ...],
            details: str,
            resolved: bool = True,
        ) -> None:
            identity = "|".join(
                (
                    source_type.value,
                    source_id,
                    relation.value,
                    target_type.value,
                    target_id,
                    rule,
                )
            )
            links.append(
                TraceabilityLink(
                    link_id="LINK-" + sha256(identity.encode("utf-8")).hexdigest()[:16].upper(),
                    source_entity_type=source_type,
                    source_id=source_id,
                    relation_type=relation,
                    target_entity_type=target_type,
                    target_id=target_id,
                    resolution_status=(
                        TraceResolutionStatus.RESOLVED
                        if resolved
                        else TraceResolutionStatus.UNRESOLVED
                    ),
                    review_status=(
                        TraceReviewStatus.NOT_REQUIRED
                        if resolved
                        else TraceReviewStatus.REVIEW_REQUIRED
                    ),
                    provenance=TraceLinkProvenance(
                        evidence_kind=evidence_kind,
                        mapping_rule_id=rule,
                        evidence_refs=refs,
                        details=details,
                    ),
                )
            )

        for anchor in source.requirement_uml_anchors:
            add_link(
                TraceEntityType.UML_ELEMENT,
                anchor.uml_id,
                TraceRelationType.DERIVED_FROM,
                TraceEntityType.REQUIREMENT,
                anchor.requirement_id,
                evidence_kind="SOURCE_C2_ANCHOR",
                rule="C2_UML_DERIVED_FROM_REQUIREMENT_V2",
                refs=(anchor.anchor_id,),
                details=(
                    "The C2 UML element is downstream of the accepted C1 "
                    "requirement according to the exact C2 anchor."
                ),
            )

        for record in records:
            for requirement_id in record.requirement_ids:
                related_anchors = tuple(
                    anchor.anchor_id
                    for anchor in source.requirement_uml_anchors
                    if anchor.requirement_id == requirement_id
                    and anchor.anchor_id in record.design_anchor_ids
                )
                add_link(
                    TraceEntityType.FILE,
                    record.file_id,
                    TraceRelationType.IMPLEMENTS,
                    TraceEntityType.REQUIREMENT,
                    requirement_id,
                    evidence_kind="DETERMINISTIC_MAPPING_RULE",
                    rule=mapping_policy_version,
                    refs=related_anchors,
                    details=(
                        "The generated module binding matched the requirement, "
                        "parsed entity, and retained anchors under the versioned "
                        "generation policy."
                    ),
                )
            for uml_id in record.uml_ids:
                add_link(
                    TraceEntityType.FILE,
                    record.file_id,
                    TraceRelationType.DERIVED_FROM,
                    TraceEntityType.UML_ELEMENT,
                    uml_id,
                    evidence_kind="DETERMINISTIC_MAPPING_RULE",
                    rule=mapping_policy_version,
                    refs=record.design_anchor_ids,
                    details="File metadata names a parsed class or anchored UML element.",
                )
            for anchor_id in record.design_anchor_ids:
                add_link(
                    TraceEntityType.FILE,
                    record.file_id,
                    TraceRelationType.DERIVED_FROM,
                    TraceEntityType.UML_ANCHOR,
                    anchor_id,
                    evidence_kind="SOURCE_C2_ANCHOR",
                    rule="C2_REQUIREMENT_UML_ANCHOR_V1",
                    refs=(anchor_id,),
                    details="File mapping retained this exact accepted C2 anchor.",
                )
            for ui_id in record.ui_artifact_ids:
                ui = next(item for item in source.ui_artifacts if item.ui_id == ui_id)
                add_link(
                    TraceEntityType.FILE,
                    record.file_id,
                    TraceRelationType.DERIVED_FROM,
                    TraceEntityType.UI_ARTIFACT,
                    ui_id,
                    evidence_kind="UNRESOLVED_SOURCE_REFERENCE",
                    rule="UI_REFERENCE_REVIEW_V1",
                    refs=(ui.source_ref,),
                    details=(
                        "The file is UI-related, but the provisional input has no "
                        "authoritative UI-to-file mapping. Research review is required."
                    ),
                    resolved=False,
                )
            for operation_id in record.api_operation_ids:
                add_link(
                    TraceEntityType.FILE,
                    record.file_id,
                    TraceRelationType.EXPOSES,
                    TraceEntityType.API_OPERATION,
                    operation_id,
                    evidence_kind="DETERMINISTIC_MAPPING_RULE",
                    rule=(
                        "TASK_API_OPERATION_MAPPING_V1"
                        if crud_spec is None
                        else "CRUD_SPEC_API_OPERATION_MAPPING_V1"
                    ),
                    refs=(record.relative_path,),
                    details="Static template metadata identifies the exact API operation.",
                )
            for entity_id in record.database_entity_ids:
                table_ids = {
                    table.table_id
                    for reference in database_references
                    for table in reference.tables
                }
                entity_type = (
                    TraceEntityType.DATABASE_TABLE
                    if entity_id in table_ids
                    else TraceEntityType.DATABASE_COLUMN
                )
                add_link(
                    TraceEntityType.FILE,
                    record.file_id,
                    TraceRelationType.DEFINES,
                    entity_type,
                    entity_id,
                    evidence_kind="DETERMINISTIC_MAPPING_RULE",
                    rule=(
                        "TASK_SQL_SCHEMA_MAPPING_V1"
                        if crud_spec is None
                        else "CRUD_SPEC_SQL_SCHEMA_MAPPING_V1"
                    ),
                    refs=(record.relative_path,),
                    details="The reviewed SQL template defines this exact schema identity.",
                )
            for seam_id in record.test_seam_ids:
                relation = (
                    TraceRelationType.VERIFIED_BY
                    if record.artifact_type.value == "TEST"
                    else TraceRelationType.IMPLEMENTS
                )
                add_link(
                    TraceEntityType.FILE,
                    record.file_id,
                    relation,
                    TraceEntityType.TEST_SEAM,
                    seam_id,
                    evidence_kind="DETERMINISTIC_MAPPING_RULE",
                    rule="INJECTED_REPOSITORY_SEAM_V1",
                    refs=(record.relative_path,),
                    details="The module implements or tests the injected repository seam.",
                )

        if crud_spec is None:
            repository_record = next(
                record
                for record in records
                if record.relative_path == "backend/src/repositories/taskRepository.js"
            )
            add_link(
                TraceEntityType.FILE,
                repository_record.file_id,
                TraceRelationType.PERSISTS_TO,
                TraceEntityType.DATABASE_TABLE,
                DB_TASKS_TABLE,
                evidence_kind="UNRESOLVED_SOURCE_REFERENCE",
                rule="RUNTIME_SQL_PERSISTENCE_REVIEW_V1",
                refs=(repository_record.relative_path, "backend/src/db/schema.sql"),
                details=(
                    "Runtime persistence is IN_MEMORY; the SQL script is design-only "
                    "and is not wired to this repository."
                ),
                resolved=False,
            )

            service_record = next(
                record
                for record in records
                if record.relative_path == MODEL_GENERATED_PATH
            )
            test_record = next(
                record
                for record in records
                if record.relative_path == "backend/tests/taskService.test.js"
            )
            add_link(
                TraceEntityType.FILE,
                service_record.file_id,
                TraceRelationType.VERIFIED_BY,
                TraceEntityType.FILE,
                test_record.file_id,
                evidence_kind="DETERMINISTIC_MAPPING_RULE",
                rule="TASK_SERVICE_TEST_FILE_V1",
                refs=(test_record.relative_path,),
                details="The generated test targets createTaskService through its seam.",
            )
        else:
            database_tables = {
                table.name: table.table_id
                for reference in database_references
                for table in reference.tables
            }
            records_by_path = {record.relative_path: record for record in records}
            for entity in crud_spec.entities:
                repository_path = (
                    f"backend/src/repositories/{entity.variable_name}Repository.js"
                )
                service_path = f"backend/src/services/{entity.variable_name}Service.js"
                test_path = f"backend/tests/{entity.variable_name}Service.test.js"
                repository_record = records_by_path[repository_path]
                service_record = records_by_path[service_path]
                test_record = records_by_path[test_path]
                add_link(
                    TraceEntityType.FILE,
                    repository_record.file_id,
                    TraceRelationType.PERSISTS_TO,
                    TraceEntityType.DATABASE_TABLE,
                    database_tables[entity.table_name],
                    evidence_kind="UNRESOLVED_SOURCE_REFERENCE",
                    rule="CRUD_SPEC_RUNTIME_SQL_REVIEW_V1",
                    refs=(repository_path, "backend/src/db/schema.sql"),
                    details=(
                        "Runtime persistence is IN_MEMORY; the generated SQL schema "
                        "is design-only and requires review before database integration."
                    ),
                    resolved=False,
                )
                add_link(
                    TraceEntityType.FILE,
                    service_record.file_id,
                    TraceRelationType.VERIFIED_BY,
                    TraceEntityType.FILE,
                    test_record.file_id,
                    evidence_kind="DETERMINISTIC_MAPPING_RULE",
                    rule="CRUD_SPEC_SERVICE_TEST_FILE_V1",
                    refs=(test_path,),
                    details=(
                        f"The generated test targets create{entity.class_name}Service "
                        "through its injected repository seam."
                    ),
                )

        for requirement_id, capability in requirement_capabilities.items():
            if capability is None:
                add_link(
                    TraceEntityType.REQUIREMENT,
                    requirement_id,
                    TraceRelationType.IMPLEMENTS,
                    TraceEntityType.GENERATION_RUN,
                    run_id,
                    evidence_kind="UNRESOLVED_SOURCE_REFERENCE",
                    rule=mapping_policy_version,
                    refs=(requirement_id,),
                    details=(
                        "No narrow Task MVP capability mapping was justified from "
                        "the requirement title; researcher review is required."
                    ),
                    resolved=False,
                )

        return TraceabilityEvidence(
            mapping_policy_version=mapping_policy_version,
            requirement_uml_anchors=source.requirement_uml_anchors,
            ui_artifacts=source.ui_artifacts,
            links=tuple(links),
        )

    def _write_workspace(
        self,
        relative_workspace: PurePosixPath,
        artifacts: tuple[TemplateArtifact, ...],
        manifest: GenerationManifest,
    ) -> None:
        root = self._workspace_root
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            self._fail(
                "UNSAFE_WORKSPACE_ROOT",
                "generated_workspace_root",
                "The generated workspace root must not be a symbolic link.",
                status.HTTP_409_CONFLICT,
            )
        resolved_root = root.resolve()
        run_directory = resolved_root.joinpath(*relative_workspace.parts)
        resolved_run = run_directory.resolve()
        if not resolved_run.is_relative_to(resolved_root):
            self._fail(
                "UNSAFE_WORKSPACE_PATH",
                "workspace_name",
                "The generation workspace escapes its configured root.",
                status.HTTP_409_CONFLICT,
            )
        try:
            run_directory.mkdir(parents=True, exist_ok=False)
            for artifact in artifacts:
                candidate = run_directory.joinpath(
                    *PurePosixPath(artifact.relative_path).parts
                )
                resolved_candidate = candidate.resolve()
                if not resolved_candidate.is_relative_to(resolved_run):
                    self._fail(
                        "UNSAFE_WORKSPACE_PATH",
                        "artifacts.relative_path",
                        "A generated artifact escapes its run workspace.",
                        status.HTTP_409_CONFLICT,
                    )
                candidate.parent.mkdir(parents=True, exist_ok=True)
                if any(
                    parent.is_symlink()
                    for parent in candidate.parents
                    if parent.is_relative_to(resolved_run)
                ):
                    self._fail(
                        "UNSAFE_WORKSPACE_SYMLINK",
                        "artifacts.relative_path",
                        "A generated artifact path traverses a symbolic link.",
                        status.HTTP_409_CONFLICT,
                    )
                candidate.write_text(
                    self._normalized_content(artifact.content),
                    encoding="utf-8",
                    newline="\n",
                )
            manifest_path = run_directory / "artifact-manifest.json"
            pending_manifest_path = run_directory / "artifact-manifest.json.pending"
            pending_manifest_path.write_text(
                json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            pending_manifest_path.replace(manifest_path)
        except ApplicationError:
            raise
        except OSError as exception:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="WORKSPACE_WRITE_FAILED",
                        field="generated_workspace_root",
                        message="The controlled generation workspace could not be written.",
                    )
                ],
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exception

    @staticmethod
    def _normalized_content(content: str) -> str:
        return content.rstrip() + "\n"

    @staticmethod
    def _fail(code: str, field: str, message: str, status_code: int) -> None:
        raise ApplicationError(
            [ErrorDetail(code=code, field=field, message=message)],
            status_code=status_code,
        )
