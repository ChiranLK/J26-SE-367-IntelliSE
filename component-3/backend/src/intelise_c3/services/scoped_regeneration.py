"""Defect-feedback-driven scoped regeneration (Research Novelty 2).

Pipeline: verify the source run and graph -> select an impact scope from typed
links -> patch only that scope with the local model -> write a NEW immutable
workspace -> verify hashes and structure -> append a new graph version -> hand a
PENDING re-test request to Component 4.

The source run is never modified. No generated JavaScript is executed. A
completed run is never reported as a successful repair: only independent C4
re-testing can establish that, and it is ``PENDING``.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from difflib import unified_diff
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import status

from intelise_c3.contracts.defect_report import DefectItem
from intelise_c3.contracts.scoped_regeneration import ScopedRegenerationRequest
from intelise_c3.contracts.structural_verification import StructuralVerificationRequest
from intelise_c3.contracts.traceability import GraphComparisonRequest, GraphUpdateRequest
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import (
    ArtifactOrigin,
    GeneratedFileRecord,
    GenerationManifest,
    RunEvidence,
)
from intelise_c3.domain.llm import LLMInferenceMetadata, LLMInferenceRequest
from intelise_c3.domain.scoped_regeneration import (
    ArtifactVersioning,
    C4RetestHandoff,
    EscalationRecord,
    FilePreservationEntry,
    GraphVersionEvidence,
    HashPreservationReport,
    ImpactSelectionReport,
    ImpactSelectionStatus,
    ModulePatchRecord,
    PatchAttemptRecord,
    PatchRejectionCode,
    RegenerationMetrics,
    RegenerationReasonCode,
    RegenerationStatus,
    ScopedRegenerationResult,
    SelectedModule,
)
from intelise_c3.domain.structural_verification import (
    StructuralFindingStatus,
    StructuralVerificationReport,
)
from intelise_c3.domain.traceability import (
    GraphLifecycleStatus,
    GraphNodeType,
    TraceGraphBuild,
    TraceGraphSnapshot,
)
from intelise_c3.generation.evidence import canonical_sha256, compute_evidence_digest
from intelise_c3.llm.client import LLMClient
from intelise_c3.prompts.scoped_repair import REPAIR_PROMPT_VERSION, build_repair_prompt
from intelise_c3.regeneration.patch_policy import (
    PATCHABLE_MODULES,
    PATCHABLE_PATHS,
    PatchRejection,
    validate_repair_output,
)
from intelise_c3.services.structural_verification import StructuralVerificationService
from intelise_c3.services.traceability import TraceabilityService
from intelise_c3.traceability.builder import TraceabilityGraphBuilder
from intelise_c3.traceability.graph_verification import GraphEvidenceVerifier
from intelise_c3.traceability.impact import ImpactSelector
from intelise_c3.traceability.verification import ManifestVerificationService

REGENERATOR_VERSION = "c3-scoped-regeneration-v1"
GENERATION_MODE = "SCOPED_REGENERATION"
DEFAULT_ATTEMPT_LIMIT = 2

ModelEvidenceClass = Literal["REAL_LOCAL_OLLAMA", "MOCKED_TEST_DOUBLE"]


class _Prepared:
    def __init__(
        self,
        workspace: Path,
        snapshot: TraceGraphSnapshot,
        impact: ImpactSelectionReport,
        report_sha256: str,
    ) -> None:
        self.workspace = workspace
        self.snapshot = snapshot
        self.impact = impact
        self.report_sha256 = report_sha256


class ScopedRegenerationService:
    """Verify, select, patch, version, and hand off without claiming repair."""

    def __init__(
        self,
        workspace_root: Path,
        traceability: TraceabilityService,
        llm_client: LLMClient | None,
        *,
        model_evidence_class: ModelEvidenceClass,
        attempt_limit: int = DEFAULT_ATTEMPT_LIMIT,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if attempt_limit < 1:
            raise ValueError("attempt_limit must be at least 1.")
        self._workspace_root = workspace_root.resolve()
        self._verifier = ManifestVerificationService(workspace_root)
        self._structural = StructuralVerificationService(self._verifier)
        self._traceability = traceability
        self._builder = TraceabilityGraphBuilder()
        self._graph_verifier = GraphEvidenceVerifier(self._builder)
        self._selector = ImpactSelector(PATCHABLE_PATHS)
        self._llm = llm_client
        self._model_evidence_class = model_evidence_class
        self._attempt_limit = attempt_limit
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    # ------------------------------------------------------------------ API

    def select_impact(self, request: ScopedRegenerationRequest) -> ImpactSelectionReport:
        """Verify inputs and select scope without a model call or any write."""
        return self._prepare(request).impact

    async def regenerate(self, request: ScopedRegenerationRequest) -> ScopedRegenerationResult:
        started = perf_counter()
        prepared = self._prepare(request)
        impact = prepared.impact
        if impact.status is ImpactSelectionStatus.REVIEW_REQUIRED:
            return self._terminal(
                RegenerationStatus.REVIEW_REQUIRED,
                (RegenerationReasonCode.IMPACT_SELECTION_REVIEW_REQUIRED,),
                impact,
                started,
            )

        source_structure = self._structural.verify(
            StructuralVerificationRequest(
                manifest=request.manifest,
                workspace_relative_path=request.workspace_relative_path,
                design_context=request.design_context,
            )
        )
        if source_structure.overall_status is StructuralFindingStatus.FAIL:
            return self._terminal(
                RegenerationStatus.REVIEW_REQUIRED,
                (RegenerationReasonCode.SOURCE_STRUCTURALLY_INVALID,),
                impact,
                started,
                escalation=EscalationRecord(
                    reason_code=RegenerationReasonCode.SOURCE_STRUCTURALLY_INVALID.value,
                    required_action=(
                        "The source run already violates deterministic structural rules; "
                        "a researcher must resolve that before defect-scoped patching."
                    ),
                    attempts_made=0,
                    attempt_limit=self._attempt_limit,
                ),
            )
        if self._llm is None:
            self._fail(
                "LOCAL_LLM_CLIENT_REQUIRED",
                "llm_client",
                "Scoped regeneration requires the configured local Ollama client.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        attempts, patches_content, accepted_metadata, prompts = await self._patch_modules(
            request, prepared
        )
        if len(patches_content) != len(impact.selected_modules):
            last = next((item for item in reversed(attempts) if not item.accepted), None)
            needs_syntax_review = (
                last is not None
                and last.rejection_code is PatchRejectionCode.UNINSPECTABLE_PATCH_SYNTAX
            )
            return self._terminal(
                (
                    RegenerationStatus.REVIEW_REQUIRED
                    if needs_syntax_review
                    else RegenerationStatus.FAILED
                ),
                (
                    (RegenerationReasonCode.PATCH_SYNTAX_REQUIRES_REVIEW,)
                    if needs_syntax_review
                    else (RegenerationReasonCode.PATCH_ATTEMPTS_EXHAUSTED,)
                ),
                impact,
                started,
                attempts=attempts,
                escalation=EscalationRecord(
                    reason_code=(
                        last.rejection_code.value
                        if last is not None and last.rejection_code is not None
                        else RegenerationReasonCode.PATCH_ATTEMPTS_EXHAUSTED.value
                    ),
                    required_action=(
                        "No valid in-scope patch was produced within the attempt limit. "
                        "A researcher must review the defect and selected module; C3 "
                        "will not rewrite additional files or the project."
                    ),
                    attempts_made=len(attempts),
                    attempt_limit=self._attempt_limit,
                ),
            )

        return self._materialize(
            request, prepared, attempts, patches_content, accepted_metadata, prompts, started
        )

    # -------------------------------------------------------- verified input

    def _prepare(self, request: ScopedRegenerationRequest) -> _Prepared:
        manifest = request.manifest
        report = request.defect_report
        workspace = self._verifier.verify(manifest, request.workspace_relative_path)
        if report.source_generation_run_id != manifest.generation_run_id:
            self._fail(
                "DEFECT_REPORT_RUN_MISMATCH",
                "defect_report.source_generation_run_id",
                "The defect report was produced for a different generation run.",
            )
        if report.source_artifact_digest_sha256 != manifest.artifact_digest_sha256:
            self._fail(
                "DEFECT_REPORT_DIGEST_MISMATCH",
                "defect_report.source_artifact_digest_sha256",
                "The defect report artifact digest does not match the verified run.",
            )
        build = self._builder.build(manifest)
        snapshot = self._traceability.latest(build.graph_id)
        if snapshot.generation_run_id != manifest.generation_run_id:
            self._fail(
                "STALE_DEFECT_REPORT",
                "defect_report",
                "The defect report or manifest is stale relative to the latest graph version.",
            )
        # The version is mandatory in the contract; it must equal the exact snapshot
        # used for impact selection (older or unknown/future versions are rejected).
        if report.source_graph_version != snapshot.graph_version:
            self._fail(
                "STALE_DEFECT_REPORT",
                "defect_report.source_graph_version",
                "The defect report names a graph version that is not the exact snapshot "
                "used for impact selection.",
            )
        self._verify_graph(snapshot, manifest, build)
        report_sha = canonical_sha256(report)
        impact = self._selector.select(
            snapshot=snapshot,
            manifest=manifest,
            report=report,
            report_sha256=report_sha,
        )
        return _Prepared(workspace, snapshot, impact, report_sha)

    def _verify_graph(
        self,
        snapshot: TraceGraphSnapshot,
        manifest: GenerationManifest,
        build: TraceGraphBuild,
    ) -> None:
        problems: list[str] = []
        if snapshot.manifest_sha256 != canonical_sha256(manifest):
            problems.append("manifest-hash")
        if snapshot.artifact_digest_sha256 != manifest.artifact_digest_sha256:
            problems.append("artifact-digest")
        if snapshot.evidence_digest_sha256 != manifest.run_evidence.evidence_digest_sha256:
            problems.append("evidence-digest")
        modules = {
            node.source_identity: node
            for node in snapshot.nodes
            if node.lifecycle_status is GraphLifecycleStatus.ACTIVE
            and node.node_type is GraphNodeType.CODE_MODULE
        }
        records = {record.file_id: record for record in manifest.files}
        if set(modules) != set(records):
            problems.append("code-module-set")
        else:
            for file_id, record in records.items():
                node = modules[file_id]
                if (
                    node.attributes.get("sha256") != record.sha256
                    or node.attributes.get("relative_path") != record.relative_path
                ):
                    problems.append(f"code-module-hash:{file_id}")
        # Full canonical comparison of every ACTIVE node and link (identity, endpoints,
        # relation, resolution, review, lifecycle, provenance, hashes) with the graph
        # rebuilt from the verified manifest, plus derived coverage and content digest.
        problems.extend(self._graph_verifier.problems(snapshot, build))
        if problems:
            self._fail(
                "UNVERIFIED_TRACEABILITY_GRAPH",
                "graph",
                "The stored graph does not match the verified manifest: "
                + ", ".join(sorted(problems))
                + ".",
            )

    # --------------------------------------------------------------- patching

    async def _patch_modules(
        self,
        request: ScopedRegenerationRequest,
        prepared: _Prepared,
    ) -> tuple[
        tuple[PatchAttemptRecord, ...],
        dict[str, tuple[str, str, int]],
        list[LLMInferenceMetadata],
        list[LLMInferenceRequest],
    ]:
        assert self._llm is not None
        attempts: list[PatchAttemptRecord] = []
        accepted: dict[str, tuple[str, str, int]] = {}
        accepted_metadata: list[LLMInferenceMetadata] = []
        prompts: list[LLMInferenceRequest] = []
        defects_by_id = {item.defect_id: item for item in request.defect_report.defects}
        for module in prepared.impact.selected_modules:
            policy = PATCHABLE_MODULES[module.relative_path]
            current = self._read_source(prepared.workspace, module.relative_path)
            module_defects: tuple[DefectItem, ...] = tuple(
                defects_by_id[defect_id] for defect_id in module.defect_ids
            )
            rejection: tuple[str, str] | None = None
            for attempt_number in range(1, self._attempt_limit + 1):
                prompt = build_repair_prompt(
                    module=policy,
                    current_source=current,
                    defects=module_defects,
                    previous_rejection=rejection,
                )
                prompts.append(prompt)
                response = await self._llm.generate(prompt)
                try:
                    content = validate_repair_output(
                        response.output_text,
                        authorized_path=module.relative_path,
                        current_source=current,
                    )
                except PatchRejection as exception:
                    attempts.append(
                        self._attempt(
                            module, attempt_number, False, exception.code, prompt, response
                        )
                    )
                    rejection = (exception.code.value, exception.message)
                    continue
                attempts.append(self._attempt(module, attempt_number, True, None, prompt, response))
                accepted[module.relative_path] = (content, current, attempt_number)
                accepted_metadata.append(response.metadata)
                break
            else:
                # Attempt limit reached for this module: stop; nothing is written.
                break
        return tuple(attempts), accepted, accepted_metadata, prompts

    @staticmethod
    def _attempt(
        module: SelectedModule,
        attempt_number: int,
        accepted: bool,
        rejection: PatchRejectionCode | None,
        prompt: LLMInferenceRequest,
        response,
    ) -> PatchAttemptRecord:
        return PatchAttemptRecord(
            relative_path=module.relative_path,
            attempt_number=attempt_number,
            accepted=accepted,
            rejection_code=rejection,
            prompt_template_version=prompt.prompt_template_version,
            prompt_request_sha256=canonical_sha256(prompt),
            response_sha256=sha256(response.output_text.encode("utf-8")).hexdigest(),
            model_identifier=response.metadata.response_model_identifier,
            client_inference_latency_ms=response.metadata.client_inference_latency_ms,
        )

    # ------------------------------------------------------ new immutable run

    def _materialize(
        self,
        request: ScopedRegenerationRequest,
        prepared: _Prepared,
        attempts: tuple[PatchAttemptRecord, ...],
        patched: dict[str, tuple[str, str, int]],
        accepted_metadata: list[LLMInferenceMetadata],
        prompts: list[LLMInferenceRequest],
        started: float,
    ) -> ScopedRegenerationResult:
        source = request.manifest
        impact = prepared.impact
        selected_paths = {item.relative_path for item in impact.selected_modules}
        new_run_id = self._id_factory()
        source_path = PurePosixPath(request.workspace_relative_path)
        new_relative = PurePosixPath(*source_path.parts[:-1], new_run_id)

        patch_bytes = {
            path: content.encode("utf-8") for path, (content, _old, _n) in patched.items()
        }
        new_records = tuple(
            record.model_copy(
                update={
                    "sha256": sha256(patch_bytes[record.relative_path]).hexdigest(),
                    "size_bytes": len(patch_bytes[record.relative_path]),
                    "origin": ArtifactOrigin.LOCAL_LLM,
                }
            )
            if record.relative_path in patch_bytes
            else record
            for record in source.files
        )
        new_manifest = self._new_manifest(
            source, new_run_id, new_records, accepted_metadata, prompts
        )

        new_dir = self._new_directory(new_relative)
        try:
            self._write_workspace(
                prepared.workspace, new_dir, source, patch_bytes, new_manifest, request, impact
            )
            self._verifier.verify(new_manifest, new_relative.as_posix())
            preservation = self._preservation(new_dir, source, selected_paths)
            if (
                not preservation.all_unselected_files_byte_identical
                or preservation.collateral_edit_count
            ):
                return self._discard(
                    new_dir,
                    new_relative,
                    RegenerationReasonCode.ARTIFACT_PRESERVATION_VIOLATION,
                    impact,
                    started,
                    attempts,
                    preservation=preservation,
                )
            structure = self._structural.verify(
                StructuralVerificationRequest(
                    manifest=new_manifest,
                    workspace_relative_path=new_relative.as_posix(),
                    design_context=request.design_context,
                )
            )
            if structure.overall_status is StructuralFindingStatus.FAIL:
                return self._discard(
                    new_dir,
                    new_relative,
                    RegenerationReasonCode.STRUCTURAL_VERIFICATION_FAILED,
                    impact,
                    started,
                    attempts,
                    preservation=preservation,
                    structure=structure,
                )
            change = self._traceability.compare(
                prepared.snapshot.graph_id,
                GraphComparisonRequest(
                    manifest=new_manifest,
                    workspace_relative_path=new_relative.as_posix(),
                    base_graph_version=prepared.snapshot.graph_version,
                ),
            )
            expected_changed = {item.file_id for item in impact.selected_modules}
            if (
                set(change.artifacts.changed) != expected_changed
                or change.artifacts.added
                or change.artifacts.removed
            ):
                return self._discard(
                    new_dir,
                    new_relative,
                    RegenerationReasonCode.GRAPH_CHANGE_SCOPE_VIOLATION,
                    impact,
                    started,
                    attempts,
                    preservation=preservation,
                    structure=structure,
                )
            update = self._traceability.update(
                prepared.snapshot.graph_id,
                GraphUpdateRequest(
                    manifest=new_manifest,
                    workspace_relative_path=new_relative.as_posix(),
                    base_graph_version=prepared.snapshot.graph_version,
                ),
            )
        except BaseException:
            self._remove_directory(new_dir)
            raise

        patch_records = tuple(
            self._patch_record(item, source, new_records, patched)
            for item in impact.selected_modules
        )
        failing_tests = tuple(
            sorted(
                {
                    test.test_case_id
                    for defect in request.defect_report.defects
                    for test in defect.failing_tests
                }
            )
        )
        requirement_ids = tuple(
            sorted(
                {
                    requirement_id
                    for defect in request.defect_report.defects
                    for requirement_id in defect.affected_requirement_ids
                }
            )
        )
        handoff = C4RetestHandoff(
            project_id=source.source.project_id,
            defect_report_id=request.defect_report.defect_report_id,
            defect_ids=tuple(item.defect_id for item in request.defect_report.defects),
            source_generation_run_id=source.generation_run_id,
            new_generation_run_id=new_manifest.generation_run_id,
            source_artifact_digest_sha256=source.artifact_digest_sha256,
            new_artifact_digest_sha256=new_manifest.artifact_digest_sha256,
            new_evidence_digest_sha256=new_manifest.run_evidence.evidence_digest_sha256,
            new_workspace_relative_path=new_relative.as_posix(),
            graph_id=update.snapshot.graph_id,
            new_graph_version=update.snapshot.graph_version,
            requirement_ids_to_retest=requirement_ids,
            failing_tests_to_rerun=failing_tests,
            changed_modules=tuple(sorted(selected_paths)),
            unchanged_module_count=preservation.unchanged_file_count,
            c3_structural_overall_status=structure.overall_status.value,
            required_c4_actions=(
                "RERUN_FAILING_TESTS",
                "RUN_REGRESSION_FOR_UNCHANGED_MODULES",
                "ASSESS_SEMANTIC_PRESERVATION",
                "PRODUCE_INDEPENDENT_READINESS_EVIDENCE",
            ),
            generated_at_utc=self._clock().astimezone(UTC).isoformat(),
        )
        return ScopedRegenerationResult(
            status=RegenerationStatus.PATCHED_PENDING_INDEPENDENT_RETEST,
            reason_codes=(RegenerationReasonCode.PATCH_APPLIED_STRUCTURALLY_VERIFIED,),
            model_evidence_class=self._model_evidence_class,
            impact_selection=impact,
            patch_attempts=attempts,
            patches=patch_records,
            artifact_versioning=ArtifactVersioning(
                source_generation_run_id=source.generation_run_id,
                new_generation_run_id=new_manifest.generation_run_id,
                source_workspace_relative_path=request.workspace_relative_path,
                new_workspace_relative_path=new_relative.as_posix(),
                source_artifact_digest_sha256=source.artifact_digest_sha256,
                new_artifact_digest_sha256=new_manifest.artifact_digest_sha256,
                source_evidence_digest_sha256=source.run_evidence.evidence_digest_sha256,
                new_evidence_digest_sha256=new_manifest.run_evidence.evidence_digest_sha256,
            ),
            preservation=preservation,
            structural_verification=structure,
            graph_versioning=GraphVersionEvidence(
                graph_id=update.snapshot.graph_id,
                base_graph_version=prepared.snapshot.graph_version,
                new_graph_version=update.snapshot.graph_version,
                base_graph_content_digest_sha256=prepared.snapshot.graph_content_digest_sha256,
                new_graph_content_digest_sha256=update.snapshot.graph_content_digest_sha256,
                new_snapshot_id=update.snapshot.snapshot_id,
                change_report=update.change_report,
            ),
            c4_retest_handoff=handoff,
            escalation=None,
            discarded_workspace_relative_path=None,
            metrics=self._metrics(started, attempts, patch_records, preservation),
        )

    def _new_manifest(
        self,
        source: GenerationManifest,
        new_run_id: str,
        records: tuple[GeneratedFileRecord, ...],
        accepted_metadata: list[LLMInferenceMetadata],
        prompts: list[LLMInferenceRequest],
    ) -> GenerationManifest:
        artifact_digest = self._artifact_digest(records)
        input_hashes = source.run_evidence.input_hashes.model_copy(
            update={
                "prompt_text_sha256": canonical_sha256(
                    [[message.model_dump(mode="json") for message in item.messages] for item in prompts]
                ),
                "prompt_request_sha256": canonical_sha256(
                    [item.model_dump(mode="json") for item in prompts]
                ),
            }
        )
        llm_inference = accepted_metadata[-1]
        evidence_digest = compute_evidence_digest(
            generation_run_id=new_run_id,
            input_hashes=input_hashes,
            prompt_template_version=REPAIR_PROMPT_VERSION,
            generator_version=REGENERATOR_VERSION,
            template_set_version=source.run_evidence.template_set_version,
            llm_inference=llm_inference,
            artifact_digest_sha256=artifact_digest,
        )
        return source.model_copy(
            update={
                "generation_run_id": new_run_id,
                "generated_at_utc": self._clock().astimezone(UTC).isoformat(),
                "generation_mode": GENERATION_MODE,
                "files": records,
                "llm_inference": llm_inference,
                "artifact_digest_sha256": artifact_digest,
                "run_evidence": RunEvidence(
                    input_hashes=input_hashes,
                    prompt_template_version=REPAIR_PROMPT_VERSION,
                    generator_version=REGENERATOR_VERSION,
                    template_set_version=source.run_evidence.template_set_version,
                    evidence_digest_sha256=evidence_digest,
                ),
                "trust_boundary": (
                    source.trust_boundary
                    + " This scoped-regeneration run changed only graph-selected modules "
                    "from simulated defect input; independent C4 re-testing is PENDING "
                    "and no repair is claimed."
                ),
            }
        )

    @staticmethod
    def _artifact_digest(records: tuple[GeneratedFileRecord, ...]) -> str:
        aggregate = sha256()
        for record in sorted(records, key=lambda item: item.relative_path):
            aggregate.update(record.relative_path.encode("utf-8"))
            aggregate.update(b"\0")
            aggregate.update(record.sha256.encode("ascii"))
            aggregate.update(b"\n")
        return aggregate.hexdigest()

    def _new_directory(self, new_relative: PurePosixPath) -> Path:
        new_dir = self._workspace_root.joinpath(*new_relative.parts)
        if not new_dir.resolve().is_relative_to(self._workspace_root):
            self._fail(
                "UNSAFE_WORKSPACE_PATH",
                "workspace_relative_path",
                "The new workspace escapes the configured root.",
            )
        if new_dir.exists():
            self._fail(
                "WORKSPACE_ALREADY_EXISTS",
                "workspace_relative_path",
                "A run workspace is never overwritten.",
            )
        return new_dir

    def _write_workspace(
        self,
        source_workspace: Path,
        new_dir: Path,
        source: GenerationManifest,
        patch_bytes: dict[str, bytes],
        new_manifest: GenerationManifest,
        request: ScopedRegenerationRequest,
        impact: ImpactSelectionReport,
    ) -> None:
        try:
            new_dir.mkdir(parents=False, exist_ok=False)
            for record in source.files:
                target = new_dir.joinpath(*PurePosixPath(record.relative_path).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                content = patch_bytes.get(record.relative_path)
                if content is None:
                    content = source_workspace.joinpath(
                        *PurePosixPath(record.relative_path).parts
                    ).read_bytes()
                target.write_bytes(content)
            lineage = {
                "record_version": "1.0",
                "classification": "C3_SCOPED_REGENERATION_LINEAGE_RECORD",
                "parent_generation_run_id": source.generation_run_id,
                "parent_artifact_digest_sha256": source.artifact_digest_sha256,
                "defect_report_id": request.defect_report.defect_report_id,
                "defect_report_sha256": impact.defect_report_sha256,
                "defect_source_classification": request.defect_report.source_classification,
                "selected_module_paths": sorted(patch_bytes),
                "model_evidence_class": self._model_evidence_class,
                "c4_retest_status": "PENDING",
                "impact_selection": impact.model_dump(mode="json"),
            }
            for name, payload in (
                ("regeneration-record.json", lineage),
                ("artifact-manifest.json", new_manifest.model_dump(mode="json")),
            ):
                pending = new_dir / f"{name}.pending"
                pending.write_text(
                    json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
                )
                pending.replace(new_dir / name)
        except OSError as exception:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="WORKSPACE_WRITE_FAILED",
                        field="generated_workspace_root",
                        message="The new regeneration workspace could not be written.",
                    )
                ],
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exception

    def _preservation(
        self,
        new_dir: Path,
        source: GenerationManifest,
        selected_paths: set[str],
    ) -> HashPreservationReport:
        entries: list[FilePreservationEntry] = []
        for record in sorted(source.files, key=lambda item: item.relative_path):
            data = new_dir.joinpath(*PurePosixPath(record.relative_path).parts).read_bytes()
            new_hash = sha256(data).hexdigest()
            entries.append(
                FilePreservationEntry(
                    relative_path=record.relative_path,
                    file_id=record.file_id,
                    source_sha256=record.sha256,
                    new_sha256=new_hash,
                    selected=record.relative_path in selected_paths,
                    byte_identical=new_hash == record.sha256,
                )
            )
        unselected = [item for item in entries if not item.selected]
        collateral = sum(not item.byte_identical for item in unselected)
        return HashPreservationReport(
            unchanged_file_count=sum(item.byte_identical for item in entries),
            changed_file_count=sum(not item.byte_identical for item in entries),
            collateral_edit_count=collateral,
            all_unselected_files_byte_identical=collateral == 0,
            entries=tuple(entries),
        )

    @staticmethod
    def _patch_record(
        module: SelectedModule,
        source: GenerationManifest,
        new_records: tuple[GeneratedFileRecord, ...],
        patched: dict[str, tuple[str, str, int]],
    ) -> ModulePatchRecord:
        old = next(item for item in source.files if item.relative_path == module.relative_path)
        new = next(item for item in new_records if item.relative_path == module.relative_path)
        content, previous, attempts_used = patched[module.relative_path]
        added = removed = 0
        for line in unified_diff(
            previous.rstrip().splitlines(), content.rstrip().splitlines(), lineterm="", n=0
        ):
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        return ModulePatchRecord(
            node_id=module.node_id,
            file_id=module.file_id,
            relative_path=module.relative_path,
            source_sha256=old.sha256,
            new_sha256=new.sha256,
            source_size_bytes=old.size_bytes,
            new_size_bytes=new.size_bytes,
            lines_added=added,
            lines_removed=removed,
            attempts_used=attempts_used,
        )

    # ----------------------------------------------------------- terminal data

    def _discard(
        self,
        new_dir: Path,
        new_relative: PurePosixPath,
        reason: RegenerationReasonCode,
        impact: ImpactSelectionReport,
        started: float,
        attempts: tuple[PatchAttemptRecord, ...],
        *,
        preservation: HashPreservationReport | None = None,
        structure: StructuralVerificationReport | None = None,
    ) -> ScopedRegenerationResult:
        self._remove_directory(new_dir)
        return self._terminal(
            RegenerationStatus.FAILED,
            (reason,),
            impact,
            started,
            attempts=attempts,
            preservation=preservation,
            structure=structure,
            discarded=new_relative.as_posix(),
            escalation=EscalationRecord(
                reason_code=reason.value,
                required_action=(
                    "The candidate workspace failed C3 verification and was discarded; "
                    "the source run and graph are unchanged. A researcher must review."
                ),
                attempts_made=len(attempts),
                attempt_limit=self._attempt_limit,
            ),
        )

    def _terminal(
        self,
        run_status: RegenerationStatus,
        reasons: tuple[RegenerationReasonCode, ...],
        impact: ImpactSelectionReport,
        started: float,
        *,
        attempts: tuple[PatchAttemptRecord, ...] = (),
        preservation: HashPreservationReport | None = None,
        structure: StructuralVerificationReport | None = None,
        discarded: str | None = None,
        escalation: EscalationRecord | None = None,
    ) -> ScopedRegenerationResult:
        return ScopedRegenerationResult(
            status=run_status,
            reason_codes=reasons,
            model_evidence_class=self._model_evidence_class,
            impact_selection=impact,
            patch_attempts=attempts,
            patches=(),
            artifact_versioning=None,
            preservation=preservation,
            structural_verification=structure,
            graph_versioning=None,
            c4_retest_handoff=None,
            escalation=escalation,
            discarded_workspace_relative_path=discarded,
            metrics=self._metrics(started, attempts, (), preservation),
        )

    @staticmethod
    def _metrics(
        started: float,
        attempts: tuple[PatchAttemptRecord, ...],
        patches: tuple[ModulePatchRecord, ...],
        preservation: HashPreservationReport | None,
    ) -> RegenerationMetrics:
        accepted = sum(item.accepted for item in attempts)
        return RegenerationMetrics(
            total_latency_ms=round((perf_counter() - started) * 1000, 3),
            llm_call_count=len(attempts),
            llm_inference_latency_ms_total=round(
                sum(item.client_inference_latency_ms for item in attempts), 3
            ),
            accepted_patch_count=len(patches),
            rejected_attempt_count=len(attempts) - accepted,
            patch_validity_rate=(accepted / len(attempts)) if attempts else None,
            collateral_edit_count=(
                preservation.collateral_edit_count if preservation is not None else None
            ),
            unchanged_files_byte_identical=(
                preservation.all_unselected_files_byte_identical
                if preservation is not None
                else None
            ),
        )

    # ------------------------------------------------------------- utilities

    def _remove_directory(self, directory: Path) -> None:
        """Remove only a candidate run directory created by this call."""
        resolved = directory.resolve()
        if resolved != self._workspace_root and resolved.is_relative_to(self._workspace_root):
            shutil.rmtree(resolved, ignore_errors=True)

    @staticmethod
    def _read_source(workspace: Path, relative_path: str) -> str:
        try:
            return workspace.joinpath(*PurePosixPath(relative_path).parts).read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeError) as exception:
            raise ApplicationError(
                [
                    ErrorDetail(
                        code="UNREADABLE_GENERATED_SOURCE",
                        field=relative_path,
                        message="A verified source module is not valid UTF-8 text.",
                    )
                ],
                status_code=status.HTTP_409_CONFLICT,
            ) from None

    @staticmethod
    def _fail(
        code: str,
        field: str,
        message: str,
        status_code: int = status.HTTP_409_CONFLICT,
    ) -> None:
        raise ApplicationError(
            [ErrorDetail(code=code, field=field, message=message)],
            status_code=status_code,
        )
