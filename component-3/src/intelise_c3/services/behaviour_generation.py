"""Behaviour-driven (non-CRUD) generation, Stage 0.

Explicit path for accepted designs the entity-CRUD generator refuses (abstract
classes, enums, inheritance, behaviour methods). It reuses the same authorization
gate as /generation-runs, derives structure deterministically from the C2 class
diagram, and asks the local model to implement one class per call (supporting
classes first, the facade last). Every class is validated before it is kept;
the assembled module is smoke-probed in a permission-restricted Node process.
No template fallback: if a class cannot be accepted, nothing is written.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
import json
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import status

from intelise_c3.contracts.behaviour import BehaviourGenerationRequest
from intelise_c3.contracts.generation import GenerationMode
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.behaviour import (
    BehaviourAttempt,
    BehaviourFileRecord,
    BehaviourFinding,
    BehaviourGenerationResult,
    BehaviourManifest,
    BehaviourProbeEvidence,
)
from intelise_c3.domain.generation import ArtifactOrigin
from intelise_c3.generation.behaviour_spec import (
    BEHAVIOUR_SPEC_POLICY_VERSION,
    BehaviourSpec,
    api_summary,
    assemble_module,
    build_behaviour_spec,
)
from intelise_c3.generation.behaviour_templates import (
    BEHAVIOUR_TEMPLATE_SET_VERSION,
    FRONTEND_FILES,
    RUNTIME_MJS,
    SERVER_MJS,
    readme,
)
from intelise_c3.generation.behaviour_validation import (
    BEHAVIOUR_VALIDATOR_VERSION,
    BehaviourValidation,
    extract_class_block,
    run_behaviour_probe,
    validate_class_block,
    validate_domain_module,
)
from intelise_c3.generation.behaviour_validation import BehaviourFinding as StaticFinding
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.llm.client import LLMClient
from intelise_c3.prompts.behaviour_generation import (
    BEHAVIOUR_BATCH_PROMPT_VERSION,
    BEHAVIOUR_DOMAIN_PATH,
    BEHAVIOUR_PROMPT_VERSION,
    build_class_prompt,
    build_module_prompt,
)
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.services.code_generation import CodeGenerationService

BEHAVIOUR_GENERATOR_VERSION = "c3-behaviour-generator-v0"
BEHAVIOUR_WORKSPACE_DIR = "behaviour"
# Provider answers without usable text (see llm/openrouter.py) are retried through the repair loop.
RETRYABLE_PROVIDER_CODES = frozenset({"OPENROUTER_EMPTY_CONTENT", "OPENROUTER_OUTPUT_TRUNCATED"})
TEMPERATURES = (0.0, 0.3, 0.6, 0.8, 0.9)
FACADE_EXTRA_ATTEMPTS = 2  # the facade coordinates everything and is the hardest unit
_ACCEPTABLE_PROBE = {"PASSED", "SKIPPED_NODE_NOT_FOUND"}
#: Engines the behaviour generator accepts and the origin recorded for the model-written module.
BEHAVIOUR_MODE_ORIGINS = {
    GenerationMode.LOCAL_LLM: ArtifactOrigin.LOCAL_LLM,
    GenerationMode.EXPERIMENTAL_CLAUDE: ArtifactOrigin.EXPERIMENTAL_CLAUDE,
    GenerationMode.EXPERIMENTAL_OPENROUTER: ArtifactOrigin.EXPERIMENTAL_OPENROUTER,
}


def _fail(code: str, field: str, message: str, status_code: int) -> None:
    raise ApplicationError([ErrorDetail(code=code, field=field, message=message)], status_code=status_code)


def _rag_layer(class_name: str) -> str:
    """Map a UML class to the rule-card layer its best practices live under."""
    lowered = class_name.casefold()
    if "repository" in lowered:
        return "repository"
    if "service" in lowered:
        return "service"
    if "controller" in lowered:
        return "controller"
    return "model"


def _trace(spec: BehaviourSpec, steps: tuple[dict, ...]) -> str:
    """Facade field values after each probe call (top-level primitives only)."""
    lines = []
    for step in steps:
        state = step.get("state") or {}
        fields = []
        for key, value in state.items():
            if key == "$class":
                continue
            if isinstance(value, dict) and value.get("$undefined"):
                fields.append(f"{key}=undefined")
            elif isinstance(value, dict) and value.get("$nonFinite"):
                fields.append(f"{key}={value['$nonFinite']}")
            elif not isinstance(value, (dict, list)):
                fields.append(f"{key}={json.dumps(value)}")
        outcome = ", ".join(fields) if step.get("ok") else f"threw: {step.get('error', '')}"
        lines.append(f"  {step['call']} -> {outcome}")
    return "\n".join(lines)


class BehaviourGenerationService:
    def __init__(
        self,
        workspace_root: Path,
        client_factory: Callable[[float], LLMClient],
        *,
        temperatures: tuple[float, ...] = TEMPERATURES,
        configured_model: str = "unknown",
        batch_mode: bool = False,
        rag_runtime: RagRuntime | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._client_factory = client_factory
        self._temperatures = temperatures
        self._configured_model = configured_model
        self._batch_mode = batch_mode
        self._rag_runtime = rag_runtime or RagRuntime.disabled()

    async def generate(self, request: BehaviourGenerationRequest) -> BehaviourGenerationResult:
        if request.mode not in BEHAVIOUR_MODE_ORIGINS:
            _fail(
                "BEHAVIOUR_MODE_UNSUPPORTED",
                "mode",
                "The behaviour generator runs with LOCAL_LLM, TeamSocLo, or the explicitly supported external engine.",
                status.HTTP_400_BAD_REQUEST,
            )
        # Same researcher-approval, context and stack gate as the CRUD generator.
        CodeGenerationService(self._workspace_root, None)._validate_authorization(request)
        spec = build_behaviour_spec(request.design_context, request.facade_class)
        spec_json = json.dumps(spec.as_json(), indent=2, sort_keys=True)

        units = [
            item
            for item in spec.classes
            if item.kind == "CLASS" and item.methods and item.name != spec.facade
        ] + [spec.by_name()[spec.facade]]
        blocks: dict[str, str] = {}
        attempts: list[BehaviourAttempt] = []
        probe_evidence: BehaviourProbeEvidence | None = None
        rag = self._rag_runtime.new_run()

        if self._batch_mode and request.mode is GenerationMode.EXPERIMENTAL_OPENROUTER:
            domain_module, batch_attempts, probe_evidence = await self._generate_batch(
                request, spec, spec_json, units
            )
            return self._write(
                request,
                spec,
                spec_json,
                domain_module,
                batch_attempts,
                probe_evidence,
                units,
            )

        for unit in units:
            best_practices = rag.retrieve(
                module_path=f"{BEHAVIOUR_DOMAIN_PATH}#{unit.name}",
                task=f"{unit.name} implement behaviour",
                stack="node",
                layer=_rag_layer(unit.name),
                applied_to_prompt=True,
                k=3,
            )
            feedback: str | None = None
            previous: str | None = None
            accepted: str | None = None
            last_findings: tuple[StaticFinding, ...] = ()
            max_attempts = request.max_attempts_per_class + (FACADE_EXTRA_ATTEMPTS if unit.name == spec.facade else 0)
            for attempt in range(1, max_attempts + 1):
                temperature = self._temperatures[min(attempt, len(self._temperatures)) - 1]
                prompt = build_class_prompt(
                    spec,
                    unit,
                    assemble_module(spec, blocks),
                    feedback=feedback,
                    previous_block=previous,
                    best_practices=best_practices,
                )
                call_started = perf_counter()
                try:
                    response = await self._client_factory(temperature).generate(prompt)
                except ApplicationError as error:
                    detail = error.errors[0] if error.errors else None
                    if detail is None or detail.code not in RETRYABLE_PROVIDER_CODES:
                        raise  # auth, credits, rate limit, timeout...: stop instead of spending more quota
                    # An empty or truncated provider answer is a failed attempt, not a failed run.
                    attempts.append(
                        BehaviourAttempt(
                            unit=unit.name,
                            attempt=attempt,
                            temperature=temperature,
                            configured_model_identifier=self._configured_model,
                            response_model_identifier="(no usable answer)",
                            prompt_template_version=prompt.prompt_template_version,
                            prompt_text_sha256=canonical_sha256([m.model_dump(mode="json") for m in prompt.messages]),
                            prompt_request_sha256=canonical_sha256(prompt),
                            client_inference_latency_ms=round((perf_counter() - call_started) * 1000, 3),
                            verdict="REJECTED",
                            syntax_check="NOT_RUN",
                            findings=(BehaviourFinding(code=detail.code, message=detail.message),),
                        )
                    )
                    last_findings = (StaticFinding(detail.code, detail.message),)
                    feedback = (
                        f"- {detail.code}: the previous reply had no usable answer text. Answer with ONLY the "
                        "class code, and keep any hidden reasoning short so the code fits in the output limit."
                    )
                    previous = None
                    continue
                block = extract_class_block(response.output_text, unit.name)
                assembled = assemble_module(spec, {**blocks, unit.name: block} if block else blocks)
                validation = validate_class_block(block, unit, assembled)
                findings = list(validation.findings)
                probe = None
                if validation.accepted and unit.name == spec.facade:
                    probe = run_behaviour_probe(assembled, spec_json)
                    final_attempt = attempt == max_attempts
                    probe_status = probe.status
                    if probe.status == "WARNINGS":
                        # Heuristic (metamorphic) findings drive retries; on the last attempt they are
                        # kept as recorded warnings instead of blocking the run.
                        if final_attempt:
                            probe_status = "PASSED_WITH_WARNINGS"
                        else:
                            findings.extend(probe.warnings)
                    elif probe.status not in _ACCEPTABLE_PROBE:
                        findings.extend(probe.findings)
                    probe_evidence = BehaviourProbeEvidence(
                        status=probe_status,
                        plan=spec.probe_plan(),
                        steps=probe.steps,
                        findings=tuple(BehaviourFinding(code=f.code, message=f.message) for f in probe.findings),
                        warnings=tuple(BehaviourFinding(code=f.code, message=f.message) for f in probe.warnings),
                    )
                metadata = response.metadata
                attempts.append(
                    BehaviourAttempt(
                        unit=unit.name,
                        attempt=attempt,
                        temperature=temperature,
                        configured_model_identifier=metadata.configured_model_identifier,
                        response_model_identifier=metadata.response_model_identifier,
                        prompt_template_version=prompt.prompt_template_version,
                        prompt_text_sha256=canonical_sha256([m.model_dump(mode="json") for m in prompt.messages]),
                        prompt_request_sha256=canonical_sha256(prompt),
                        eval_count=getattr(metadata.response, "eval_count", None)
                        or getattr(metadata.response, "completion_tokens", None),
                        prompt_eval_count=getattr(metadata.response, "prompt_eval_count", None)
                        or getattr(metadata.response, "prompt_tokens", None),
                        client_inference_latency_ms=metadata.client_inference_latency_ms,
                        verdict="ACCEPTED" if not findings else "REJECTED",
                        syntax_check=validation.syntax_check,
                        findings=tuple(BehaviourFinding(code=f.code, message=f.message) for f in findings),
                    )
                )
                if not findings:
                    accepted = block
                    break
                last_findings = tuple(findings)
                feedback = BehaviourValidation(tuple(findings), validation.syntax_check).feedback()
                if probe is not None and probe.steps:
                    feedback += "\nObserved session (fields after each call):\n" + _trace(spec, probe.steps)
                if any("is not a function" in f.message or "Cannot read" in f.message for f in findings):
                    feedback += "\nOnly these members exist:\n" + api_summary(spec)
                previous = block if block else None
            if accepted is None:
                raise ApplicationError(
                    [
                        ErrorDetail(
                            code="BEHAVIOUR_CLASS_REJECTED",
                            field=f"behaviour.{unit.name}",
                            message=(
                                f"The local model's '{unit.name}' was rejected in all "
                                f"{max_attempts} attempt(s); nothing was written and "
                                "no template fallback was applied."
                            ),
                        ),
                        *(
                            ErrorDetail(code=f.code, field=f"behaviour.{unit.name}", message=f.message)
                            for f in last_findings
                        ),
                    ],
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                )
            blocks[unit.name] = accepted

        domain_module = assemble_module(spec, blocks)
        final = validate_domain_module(domain_module, spec)  # whole-module safety net
        if not final.accepted:
            raise ApplicationError(
                [ErrorDetail(code=f.code, field="behaviour.module", message=f.message) for f in final.findings],
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        assert probe_evidence is not None
        return self._write(
            request, spec, spec_json, domain_module, tuple(attempts), probe_evidence, units, rag.evidence()
        )

    async def _generate_batch(self, request, spec, spec_json, units):
        """Generate and validate the complete module with one call per repair attempt."""
        skeleton = assemble_module(spec, {})
        attempts: list[BehaviourAttempt] = []
        feedback: str | None = None
        previous: str | None = None
        last_findings: tuple[StaticFinding, ...] = ()
        max_attempts = request.max_attempts_per_class + FACADE_EXTRA_ATTEMPTS

        for attempt in range(1, max_attempts + 1):
            temperature = self._temperatures[min(attempt, len(self._temperatures)) - 1]
            prompt = build_module_prompt(spec, skeleton, feedback=feedback, previous_module=previous)
            call_started = perf_counter()
            try:
                response = await self._client_factory(temperature).generate(prompt)
            except ApplicationError as error:
                detail = error.errors[0] if error.errors else None
                if detail is None or detail.code not in RETRYABLE_PROVIDER_CODES:
                    raise
                findings = (StaticFinding(detail.code, detail.message),)
                attempts.append(
                    BehaviourAttempt(
                        unit="COMPLETE_MODULE",
                        attempt=attempt,
                        temperature=temperature,
                        configured_model_identifier=self._configured_model,
                        response_model_identifier="(no usable answer)",
                        prompt_template_version=prompt.prompt_template_version,
                        prompt_text_sha256=canonical_sha256([m.model_dump(mode="json") for m in prompt.messages]),
                        prompt_request_sha256=canonical_sha256(prompt),
                        client_inference_latency_ms=round((perf_counter() - call_started) * 1000, 3),
                        verdict="REJECTED",
                        syntax_check="NOT_RUN",
                        findings=(BehaviourFinding(code=detail.code, message=detail.message),),
                    )
                )
                last_findings = findings
                feedback = f"- {detail.code}: return the complete module as code only."
                previous = None
                continue

            blocks = {
                unit.name: extract_class_block(response.output_text, unit.name)
                for unit in spec.classes
                if unit.kind != "ENUM"
            }
            module = assemble_module(spec, {name: block for name, block in blocks.items() if block})
            validation = validate_domain_module(module, spec)
            findings = list(validation.findings)
            probe = None
            probe_status = "NOT_RUN"
            if validation.accepted:
                probe = run_behaviour_probe(module, spec_json)
                probe_status = probe.status
                if probe.status == "WARNINGS" and attempt < max_attempts:
                    findings.extend(probe.warnings)
                elif probe.status == "WARNINGS":
                    probe_status = "PASSED_WITH_WARNINGS"
                elif probe.status not in _ACCEPTABLE_PROBE:
                    findings.extend(probe.findings)

            metadata = response.metadata
            attempts.append(
                BehaviourAttempt(
                    unit="COMPLETE_MODULE",
                    attempt=attempt,
                    temperature=temperature,
                    configured_model_identifier=metadata.configured_model_identifier,
                    response_model_identifier=metadata.response_model_identifier,
                    prompt_template_version=prompt.prompt_template_version,
                    prompt_text_sha256=canonical_sha256([m.model_dump(mode="json") for m in prompt.messages]),
                    prompt_request_sha256=canonical_sha256(prompt),
                    eval_count=getattr(metadata.response, "eval_count", None)
                    or getattr(metadata.response, "completion_tokens", None),
                    prompt_eval_count=getattr(metadata.response, "prompt_eval_count", None)
                    or getattr(metadata.response, "prompt_tokens", None),
                    client_inference_latency_ms=metadata.client_inference_latency_ms,
                    verdict="ACCEPTED" if not findings else "REJECTED",
                    syntax_check=validation.syntax_check,
                    findings=tuple(BehaviourFinding(code=f.code, message=f.message) for f in findings),
                )
            )
            if not findings and probe is not None:
                return (
                    module,
                    tuple(attempts),
                    BehaviourProbeEvidence(
                        status=probe_status,
                        plan=spec.probe_plan(),
                        steps=probe.steps,
                        findings=tuple(BehaviourFinding(code=f.code, message=f.message) for f in probe.findings),
                        warnings=tuple(BehaviourFinding(code=f.code, message=f.message) for f in probe.warnings),
                    ),
                )
            last_findings = tuple(findings)
            feedback = BehaviourValidation(tuple(findings), validation.syntax_check).feedback()
            if probe is not None and probe.steps:
                feedback += "\nObserved session:\n" + _trace(spec, probe.steps)
            previous = module

        raise ApplicationError(
            [
                ErrorDetail(
                    code="BEHAVIOUR_MODULE_REJECTED",
                    field="behaviour.module",
                    message=(
                        f"The OpenRouter module was rejected in all {max_attempts} attempt(s); "
                        "nothing was written and no template fallback was applied."
                    ),
                ),
                *(ErrorDetail(code=f.code, field="behaviour.module", message=f.message) for f in last_findings),
            ],
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    def _write(
        self, request, spec, spec_json, domain_module, attempts, probe_evidence, units, rag_evidence=None
    ) -> BehaviourGenerationResult:
        run_id = str(uuid4())
        relative = PurePosixPath(BEHAVIOUR_WORKSPACE_DIR) / request.workspace_name / run_id
        model = attempts[-1].configured_model_identifier
        provider = {
            GenerationMode.LOCAL_LLM: "ollama-local",
            GenerationMode.EXPERIMENTAL_CLAUDE: "teamsoclo-claude",
            GenerationMode.EXPERIMENTAL_OPENROUTER: "openrouter",
        }[request.mode]
        model_origin = BEHAVIOUR_MODE_ORIGINS[request.mode]
        files: list[tuple[str, str, ArtifactOrigin, tuple[str, ...]]] = [
            ("README.md", readme(spec.project_id, spec.facade, model, provider), ArtifactOrigin.TEMPLATE, ()),
            ("backend/behaviour-spec.json", spec_json + "\n", ArtifactOrigin.TEMPLATE, ()),
            ("backend/server.mjs", SERVER_MJS, ArtifactOrigin.TEMPLATE, ()),
            ("backend/runtime.mjs", RUNTIME_MJS, ArtifactOrigin.TEMPLATE, ()),
            *((path, content, ArtifactOrigin.TEMPLATE, ()) for path, content in FRONTEND_FILES.items()),
            (BEHAVIOUR_DOMAIN_PATH, domain_module, model_origin, tuple(u.name for u in units)),
        ]
        root = self._workspace_root.resolve()
        run_dir = root.joinpath(*relative.parts)
        if not run_dir.resolve().is_relative_to(root):
            _fail("UNSAFE_WORKSPACE_PATH", "workspace_name", "The workspace escapes its root.", status.HTTP_409_CONFLICT)
        records = []
        digest = sha256()
        run_dir.mkdir(parents=True, exist_ok=False)
        for path, content, origin, by_units in sorted(files, key=lambda item: item[0]):
            encoded = content.encode("utf-8")
            target = run_dir.joinpath(*PurePosixPath(path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encoded)
            file_hash = sha256(encoded).hexdigest()
            records.append(
                BehaviourFileRecord(
                    relative_path=path, origin=origin, sha256=file_hash, size_bytes=len(encoded), generated_by_unit=by_units
                )
            )
            digest.update(path.encode("utf-8") + b"\0" + file_hash.encode("ascii") + b"\n")
        design = request.design_context
        manifest = BehaviourManifest(
            generation_run_id=run_id,
            generated_at_utc=datetime.now(UTC).isoformat(),
            generation_mode=request.mode.value,
            llm_provider=provider,
            generator_version=BEHAVIOUR_GENERATOR_VERSION,
            template_set_version=BEHAVIOUR_TEMPLATE_SET_VERSION,
            spec_policy_version=BEHAVIOUR_SPEC_POLICY_VERSION,
            validator_version=BEHAVIOUR_VALIDATOR_VERSION,
            prompt_template_version=attempts[-1].prompt_template_version,
            project_id=design.project_id,
            srs_version=design.srs_version,
            uml_version=design.uml_version,
            requirement_ids=tuple(r.requirement_id for r in design.requirements),
            uml_ids=tuple(u.uml_id for u in design.source_uml_elements),
            design_anchor_ids=tuple(a.anchor_id for a in design.requirement_uml_anchors),
            facade_class=spec.facade,
            facade_rule=spec.facade_rule,
            selected_stack_id=request.stack_selection_report.selected_stack.candidate.candidate_id,
            implemented_stack="REACT (Vite) frontend + NODE_JS backend (no runtime dependencies); the behaviour generator implements only this stack",
            stack_approval_reference=request.stack_approval.approval_reference,
            attempts=attempts,
            probe=probe_evidence,
            files=tuple(records),
            artifact_digest_sha256=digest.hexdigest(),
            spec_diagnostics=spec.diagnostics,
            rag_evidence=rag_evidence,
        )
        (run_dir / "behaviour-manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        return BehaviourGenerationResult(
            workspace_relative_path=relative.as_posix(),
            manifest_relative_path=(relative / "behaviour-manifest.json").as_posix(),
            manifest=manifest,
        )
