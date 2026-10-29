"""Deterministic impact selection over a verified living traceability graph.

Algorithm ``C3_IMPACT_SELECTION_V1`` (documented in
``docs/defect-feedback-scoped-regeneration.md``) selects a module only when typed,
active, resolved, non-review links support it. It never uses file-name
similarity, C4 free text, or broad ``affected_module_ids`` lists as authority.
"""

from collections import defaultdict

from fastapi import status

from intelise_c3.contracts.defect_report import (
    DefectCategory,
    DefectItem,
    DefectReport,
    FailingTestHookType,
)
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.generation import (
    GeneratedArtifactType,
    GeneratedFileRecord,
    GenerationManifest,
    TraceRelationType,
    TraceResolutionStatus,
    TraceReviewStatus,
)
from intelise_c3.domain.scoped_regeneration import (
    DefectImpactResult,
    EvidenceChannel,
    ExcludedLink,
    ImpactPath,
    ImpactPathStep,
    ImpactReasonCode,
    ImpactSelectionReport,
    ImpactSelectionStatus,
    ModuleExclusion,
    SelectedModule,
)
from intelise_c3.domain.traceability import (
    GraphLifecycleStatus,
    GraphNodeType,
    ImpactSet,
    TraceGraphLink,
    TraceGraphSnapshot,
)
from intelise_c3.traceability.builder import graph_node_id

MAX_AUTOMATIC_SCOPE = 2

CATEGORY_ARTIFACT_POLICY: dict[DefectCategory, frozenset[GeneratedArtifactType]] = {
    DefectCategory.BUSINESS_LOGIC: frozenset({GeneratedArtifactType.BUSINESS_LOGIC}),
    DefectCategory.API_CONTRACT: frozenset(
        {GeneratedArtifactType.API, GeneratedArtifactType.CONTROLLER}
    ),
    DefectCategory.DATA_ACCESS: frozenset({GeneratedArtifactType.REPOSITORY}),
    DefectCategory.UI_BEHAVIOR: frozenset({GeneratedArtifactType.FRONTEND}),
}


def requirement_impact_set(
    snapshot: TraceGraphSnapshot,
    manifest: GenerationManifest,
    requirement_id: str,
) -> ImpactSet:
    """Return resolved downstream impact using the scoped-repair graph policy."""
    normalized_id = requirement_id.removeprefix("REQUIREMENT:")
    requirement_node_id = graph_node_id(GraphNodeType.REQUIREMENT, normalized_id)
    context = _GraphContext(snapshot, manifest)
    if requirement_node_id not in context.nodes:
        raise ApplicationError(
            [
                ErrorDetail(
                    code="UNKNOWN_REQUIREMENT_ID",
                    field="requirement_id",
                    message=f"Requirement '{normalized_id}' is not an active graph node.",
                )
            ],
            status_code=status.HTTP_404_NOT_FOUND,
        )

    code_node_ids = {
        link.source_node_id
        for link in context.usable_links
        if link.relation_type is TraceRelationType.IMPLEMENTS
        and link.target_node_id == requirement_node_id
        and link.source_node_id in context.record_by_node
    }
    api_node_ids: set[str] = set()
    database_node_ids: set[str] = set()
    test_hook_node_ids: set[str] = set()
    for link in context.usable_links:
        if link.source_node_id not in code_node_ids:
            continue
        target = context.nodes[link.target_node_id]
        if target.node_type is GraphNodeType.API_OPERATION:
            api_node_ids.add(target.node_id)
        elif target.node_type is GraphNodeType.DATABASE_ARTIFACT:
            database_node_ids.add(target.node_id)
        elif target.node_type is GraphNodeType.TEST_HOOK or (
            target.node_type is GraphNodeType.CODE_MODULE
            and link.relation_type is TraceRelationType.VERIFIED_BY
        ):
            test_hook_node_ids.add(target.node_id)

    sorted_code_ids = tuple(sorted(code_node_ids))
    sorted_api_ids = tuple(sorted(api_node_ids))
    sorted_database_ids = tuple(sorted(database_node_ids))
    sorted_test_ids = tuple(sorted(test_hook_node_ids))
    return ImpactSet(
        requirement_id=normalized_id,
        affected_node_ids=tuple(
            sorted(
                {
                    *sorted_code_ids,
                    *sorted_api_ids,
                    *sorted_database_ids,
                    *sorted_test_ids,
                }
            )
        ),
        code_node_ids=sorted_code_ids,
        api_node_ids=sorted_api_ids,
        database_node_ids=sorted_database_ids,
        test_hook_node_ids=sorted_test_ids,
        module_paths=tuple(
            sorted(
                context.record_by_node[node_id].relative_path
                for node_id in sorted_code_ids
            )
        ),
    )


class ImpactSelector:
    """Select a minimal justified patch scope or return REVIEW_REQUIRED."""

    def __init__(
        self,
        patchable_paths: frozenset[str],
        scope_limit: int = MAX_AUTOMATIC_SCOPE,
    ) -> None:
        self._patchable_paths = patchable_paths
        self._scope_limit = scope_limit

    def select(
        self,
        *,
        snapshot: TraceGraphSnapshot,
        manifest: GenerationManifest,
        report: DefectReport,
        report_sha256: str,
    ) -> ImpactSelectionReport:
        context = _GraphContext(snapshot, manifest)
        self._validate_references(report, context)
        results = tuple(self._select_defect(item, context) for item in report.defects)

        merged: dict[str, SelectedModule] = {}
        for result in results:
            for module in result.selected_modules:
                existing = merged.get(module.node_id)
                merged[module.node_id] = module if existing is None else _merge(existing, module)
        union = tuple(sorted(merged.values(), key=lambda item: item.relative_path))

        all_selected = all(item.status is ImpactSelectionStatus.SELECTED for item in results)
        reasons: list[ImpactReasonCode]
        if all_selected and len(union) > self._scope_limit:
            overall = ImpactSelectionStatus.REVIEW_REQUIRED
            reasons = [ImpactReasonCode.SCOPE_TOO_BROAD]
            union = ()
        elif all_selected and union:
            overall = ImpactSelectionStatus.SELECTED
            reasons = sorted(
                {code for module in union for code in module.reason_codes},
                key=lambda item: item.value,
            )
        else:
            overall = ImpactSelectionStatus.REVIEW_REQUIRED
            reasons = sorted(
                {
                    code
                    for result in results
                    if result.status is ImpactSelectionStatus.REVIEW_REQUIRED
                    for code in result.reason_codes
                },
                key=lambda item: item.value,
            )
            union = ()
        return ImpactSelectionReport(
            defect_report_id=report.defect_report_id,
            defect_report_sha256=report_sha256,
            defect_source_classification=report.source_classification,
            graph_id=snapshot.graph_id,
            graph_version=snapshot.graph_version,
            graph_content_digest_sha256=snapshot.graph_content_digest_sha256,
            source_generation_run_id=manifest.generation_run_id,
            source_artifact_digest_sha256=manifest.artifact_digest_sha256,
            status=overall,
            reason_codes=tuple(reasons),
            selected_modules=union,
            defects=results,
            automatic_scope_limit=self._scope_limit,
        )

    @staticmethod
    def _validate_references(report: DefectReport, context: "_GraphContext") -> None:
        errors: list[ErrorDetail] = []
        for defect in report.defects:
            for requirement_id in defect.affected_requirement_ids:
                if graph_node_id(GraphNodeType.REQUIREMENT, requirement_id) not in context.nodes:
                    errors.append(
                        ErrorDetail(
                            code="UNKNOWN_REQUIREMENT_ID",
                            field=f"defects.{defect.defect_id}.affected_requirement_ids",
                            message=f"Requirement '{requirement_id}' is not an active graph node.",
                        )
                    )
            for test in defect.failing_tests:
                if context.test_hook_node(test.hook_type, test.hook_ref) is None:
                    errors.append(
                        ErrorDetail(
                            code="UNKNOWN_TEST_HOOK",
                            field=f"defects.{defect.defect_id}.failing_tests",
                            message=(
                                f"Test hook '{test.hook_ref}' is not an active test file "
                                "or test seam in the verified graph."
                            ),
                        )
                    )
            for operation_id in defect.api_operation_ids:
                if graph_node_id(GraphNodeType.API_OPERATION, operation_id) not in context.nodes:
                    errors.append(
                        ErrorDetail(
                            code="UNKNOWN_API_OPERATION",
                            field=f"defects.{defect.defect_id}.api_operation_ids",
                            message=f"API operation '{operation_id}' is not an active graph node.",
                        )
                    )
        if errors:
            raise ApplicationError(errors, status_code=status.HTTP_409_CONFLICT)

    def _select_defect(self, defect: DefectItem, context: "_GraphContext") -> DefectImpactResult:
        if defect.category not in CATEGORY_ARTIFACT_POLICY:
            return DefectImpactResult(
                defect_id=defect.defect_id,
                category=defect.category.value,
                status=ImpactSelectionStatus.REVIEW_REQUIRED,
                reason_codes=(ImpactReasonCode.UNSUPPORTED_DEFECT_CATEGORY,),
                selected_modules=(),
                review_candidate_paths=(),
                exclusions=(),
                excluded_links=(),
                notes=(
                    f"Category {defect.category.value} has no deterministic C3 module "
                    "scope policy; a researcher must review it.",
                ),
            )
        allowed_types = CATEGORY_ARTIFACT_POLICY[defect.category]

        requirement_paths = self._requirement_paths(defect, context)
        test_paths = self._test_paths(defect, context)
        api_paths = self._api_paths(defect, context)
        channel_paths: dict[str, dict[EvidenceChannel, list[ImpactPath]]] = defaultdict(dict)
        for channel, paths in (
            (EvidenceChannel.REQUIREMENT_IMPLEMENTS, requirement_paths),
            (EvidenceChannel.FAILING_TEST_PATH, test_paths),
            (EvidenceChannel.API_EXPOSES, api_paths),
        ):
            for node_id, items in paths.items():
                channel_paths[node_id][channel] = items

        notes: list[str] = []
        info_codes: list[ImpactReasonCode] = []
        exclusion_reasons: dict[str, list[ImpactReasonCode]] = defaultdict(list)
        candidates: list[str] = []
        for node_id, record in sorted(
            context.record_by_node.items(), key=lambda item: item[1].relative_path
        ):
            channels = channel_paths.get(node_id)
            if not channels:
                exclusion_reasons[node_id].append(ImpactReasonCode.NOT_REACHED_BY_ANY_TYPED_PATH)
            elif EvidenceChannel.REQUIREMENT_IMPLEMENTS not in channels:
                exclusion_reasons[node_id].append(
                    ImpactReasonCode.NOT_LINKED_TO_AFFECTED_REQUIREMENT
                )
            elif not (
                EvidenceChannel.FAILING_TEST_PATH in channels
                or EvidenceChannel.API_EXPOSES in channels
            ):
                exclusion_reasons[node_id].append(
                    ImpactReasonCode.NOT_ON_FAILING_TEST_OR_API_PATH
                )
            elif record.artifact_type not in allowed_types:
                exclusion_reasons[node_id].append(ImpactReasonCode.CATEGORY_INCOMPATIBLE)
            else:
                candidates.append(node_id)

        location_module = self._resolve_location(defect, context, notes, info_codes)
        corroborated: set[str] = set()
        if location_module is not None:
            location_node = context.module_node_id(location_module)
            if location_node in candidates:
                corroborated.add(location_node)
            else:
                exclusion_reasons[location_node].append(
                    ImpactReasonCode.LOCATION_CLAIM_NOT_SUPPORTED_BY_GRAPH
                )
                notes.append(
                    f"C4 location '{location_module.relative_path}' has no sufficient "
                    "typed graph support, so it was not added to the patch scope."
                )
        if len(candidates) > 1 and corroborated:
            for node_id in candidates:
                if node_id not in corroborated:
                    exclusion_reasons[node_id].append(
                        ImpactReasonCode.NOT_CORROBORATED_BY_DEFECT_LOCATION
                    )
            candidates = [node_id for node_id in candidates if node_id in corroborated]

        excluded_links = self._excluded_links(context, channel_paths, defect)
        exclusions = tuple(
            ModuleExclusion(
                node_id=node_id,
                relative_path=context.record_by_node[node_id].relative_path,
                reason_codes=tuple(dict.fromkeys(reasons)),
            )
            for node_id, reasons in sorted(
                exclusion_reasons.items(),
                key=lambda item: context.record_by_node[item[0]].relative_path,
            )
            if node_id not in candidates
        )

        def review(
            codes: tuple[ImpactReasonCode, ...],
            *,
            candidate_ids: list[str] | None = None,
        ) -> DefectImpactResult:
            return DefectImpactResult(
                defect_id=defect.defect_id,
                category=defect.category.value,
                status=ImpactSelectionStatus.REVIEW_REQUIRED,
                reason_codes=(*codes, *info_codes),
                selected_modules=(),
                review_candidate_paths=tuple(
                    sorted(context.record_by_node[item].relative_path for item in candidate_ids or [])
                ),
                exclusions=exclusions,
                excluded_links=excluded_links,
                notes=tuple(notes),
            )

        if not requirement_paths:
            return review(
                (ImpactReasonCode.MISSING_TRACE_LINKS, ImpactReasonCode.INSUFFICIENT_EVIDENCE)
            )
        if not candidates:
            return review((ImpactReasonCode.INSUFFICIENT_EVIDENCE,))
        if len(candidates) > self._scope_limit:
            return review((ImpactReasonCode.SCOPE_TOO_BROAD,), candidate_ids=candidates)
        not_patchable = [
            node_id
            for node_id in candidates
            if context.record_by_node[node_id].relative_path not in self._patchable_paths
        ]
        if not_patchable:
            return review(
                (ImpactReasonCode.SELECTED_MODULE_NOT_PATCHABLE,),
                candidate_ids=candidates,
            )

        selected: list[SelectedModule] = []
        for node_id in sorted(candidates, key=lambda item: context.record_by_node[item].relative_path):
            record = context.record_by_node[node_id]
            channels = channel_paths[node_id]
            codes: list[ImpactReasonCode] = []
            if EvidenceChannel.FAILING_TEST_PATH in channels:
                codes.append(ImpactReasonCode.SELECTED_BY_REQUIREMENT_AND_TEST_PATH)
            if EvidenceChannel.API_EXPOSES in channels:
                codes.append(ImpactReasonCode.SELECTED_BY_REQUIREMENT_AND_API_PATH)
            selected.append(
                SelectedModule(
                    node_id=node_id,
                    file_id=record.file_id,
                    relative_path=record.relative_path,
                    module_identity=record.module_identity,
                    artifact_type=record.artifact_type,
                    defect_ids=(defect.defect_id,),
                    evidence_channels=tuple(sorted(channels, key=lambda item: item.value)),
                    location_corroborated=node_id in corroborated,
                    reason_codes=tuple(codes),
                    paths=tuple(path for channel in sorted(channels, key=lambda i: i.value) for path in channels[channel]),
                )
            )
        return DefectImpactResult(
            defect_id=defect.defect_id,
            category=defect.category.value,
            status=ImpactSelectionStatus.SELECTED,
            reason_codes=tuple(
                dict.fromkeys(
                    (*(code for module in selected for code in module.reason_codes), *info_codes)
                )
            ),
            selected_modules=tuple(selected),
            review_candidate_paths=(),
            exclusions=exclusions,
            excluded_links=excluded_links,
            notes=tuple(notes),
        )

    @staticmethod
    def _resolve_location(
        defect: DefectItem,
        context: "_GraphContext",
        notes: list[str],
        info_codes: list[ImpactReasonCode],
    ) -> GeneratedFileRecord | None:
        if defect.location is None or defect.location.relative_path is None:
            return None
        record = context.record_by_path.get(defect.location.relative_path)
        if record is not None and context.module_node_id(record) not in context.record_by_node:
            record = None
        if record is None:
            info_codes.append(ImpactReasonCode.LOCATION_NOT_IN_MANIFEST)
            notes.append("The C4 location path is not in the verified manifest and was ignored.")
        return record

    @staticmethod
    def _requirement_paths(
        defect: DefectItem,
        context: "_GraphContext",
    ) -> dict[str, list[ImpactPath]]:
        paths: dict[str, list[ImpactPath]] = defaultdict(list)
        for requirement_id in defect.affected_requirement_ids:
            requirement_node = graph_node_id(GraphNodeType.REQUIREMENT, requirement_id)
            for link in context.usable_links:
                if (
                    link.relation_type is TraceRelationType.IMPLEMENTS
                    and link.target_node_id == requirement_node
                    and link.source_node_id in context.record_by_node
                ):
                    paths[link.source_node_id].append(
                        ImpactPath(
                            channel=EvidenceChannel.REQUIREMENT_IMPLEMENTS,
                            anchor_node_id=requirement_node,
                            steps=(_step(link),),
                        )
                    )
        return paths

    @staticmethod
    def _test_paths(
        defect: DefectItem,
        context: "_GraphContext",
    ) -> dict[str, list[ImpactPath]]:
        paths: dict[str, list[ImpactPath]] = defaultdict(list)
        for test in defect.failing_tests:
            hook_node = context.test_hook_node(test.hook_type, test.hook_ref)
            if hook_node is None:
                continue
            is_file_hook = test.hook_type is FailingTestHookType.TEST_FILE
            relations = (
                {TraceRelationType.VERIFIED_BY}
                if is_file_hook
                else {TraceRelationType.IMPLEMENTS, TraceRelationType.VERIFIED_BY}
            )
            for link in context.usable_links:
                if (
                    link.relation_type in relations
                    and link.target_node_id == hook_node
                    and link.source_node_id in context.record_by_node
                ):
                    paths[link.source_node_id].append(
                        ImpactPath(
                            channel=EvidenceChannel.FAILING_TEST_PATH,
                            anchor_node_id=hook_node,
                            steps=(_step(link),),
                        )
                    )
        return paths

    @staticmethod
    def _api_paths(
        defect: DefectItem,
        context: "_GraphContext",
    ) -> dict[str, list[ImpactPath]]:
        paths: dict[str, list[ImpactPath]] = defaultdict(list)
        for operation_id in defect.api_operation_ids:
            operation_node = graph_node_id(GraphNodeType.API_OPERATION, operation_id)
            for link in context.usable_links:
                if (
                    link.relation_type is TraceRelationType.EXPOSES
                    and link.target_node_id == operation_node
                    and link.source_node_id in context.record_by_node
                ):
                    paths[link.source_node_id].append(
                        ImpactPath(
                            channel=EvidenceChannel.API_EXPOSES,
                            anchor_node_id=operation_node,
                            steps=(_step(link),),
                        )
                    )
        return paths

    @staticmethod
    def _excluded_links(
        context: "_GraphContext",
        channel_paths: dict[str, dict[EvidenceChannel, list[ImpactPath]]],
        defect: DefectItem,
    ) -> tuple[ExcludedLink, ...]:
        considered = set(channel_paths)
        considered.update(
            graph_node_id(GraphNodeType.REQUIREMENT, item)
            for item in defect.affected_requirement_ids
        )
        considered.update(
            graph_node_id(GraphNodeType.API_OPERATION, item) for item in defect.api_operation_ids
        )
        for test in defect.failing_tests:
            hook_node = context.test_hook_node(test.hook_type, test.hook_ref)
            if hook_node is not None:
                considered.add(hook_node)
        excluded = [
            link
            for link in context.active_links
            if (
                link.resolution_status is TraceResolutionStatus.UNRESOLVED
                or link.review_status is TraceReviewStatus.REVIEW_REQUIRED
            )
            and (link.source_node_id in considered or link.target_node_id in considered)
        ]
        return tuple(
            ExcludedLink(
                link_id=link.link_id,
                source_node_id=link.source_node_id,
                relation_type=link.relation_type,
                target_node_id=link.target_node_id,
                details=(
                    f"{link.resolution_status.value}/{link.review_status.value} link "
                    f"from rule {link.provenance.mapping_rule_id} cannot authorize "
                    "an automatic patch scope."
                ),
            )
            for link in sorted(excluded, key=lambda item: item.link_id)
        )


class _GraphContext:
    """Read-only indices over one verified snapshot and its accepted manifest."""

    def __init__(self, snapshot: TraceGraphSnapshot, manifest: GenerationManifest) -> None:
        self.manifest = manifest
        self.nodes = {
            node.node_id: node
            for node in snapshot.nodes
            if node.lifecycle_status is GraphLifecycleStatus.ACTIVE
        }
        self.active_links: tuple[TraceGraphLink, ...] = tuple(
            link for link in snapshot.links if link.lifecycle_status is GraphLifecycleStatus.ACTIVE
        )
        self.usable_links = tuple(
            link
            for link in self.active_links
            if link.resolution_status is TraceResolutionStatus.RESOLVED
            and link.review_status is TraceReviewStatus.NOT_REQUIRED
            and link.source_node_id in self.nodes
            and link.target_node_id in self.nodes
        )
        self.record_by_path = {record.relative_path: record for record in manifest.files}
        self.record_by_node = {
            self.module_node_id(record): record
            for record in manifest.files
            if self.module_node_id(record) in self.nodes
        }

    @staticmethod
    def module_node_id(record: GeneratedFileRecord) -> str:
        return graph_node_id(GraphNodeType.CODE_MODULE, record.file_id)

    def test_hook_node(self, hook_type: FailingTestHookType, hook_ref: str) -> str | None:
        if hook_type is FailingTestHookType.TEST_FILE:
            record = self.record_by_path.get(hook_ref)
            if record is None or record.artifact_type is not GeneratedArtifactType.TEST:
                return None
            node_id = self.module_node_id(record)
            return node_id if node_id in self.nodes else None
        node_id = graph_node_id(GraphNodeType.TEST_HOOK, hook_ref)
        return node_id if node_id in self.nodes else None


def _step(link: TraceGraphLink) -> ImpactPathStep:
    return ImpactPathStep(
        source_node_id=link.source_node_id,
        relation_type=link.relation_type,
        target_node_id=link.target_node_id,
        link_id=link.link_id,
        mapping_rule_id=link.provenance.mapping_rule_id,
        evidence_refs=link.provenance.evidence_refs,
    )


def _merge(left: SelectedModule, right: SelectedModule) -> SelectedModule:
    return left.model_copy(
        update={
            "defect_ids": tuple(dict.fromkeys((*left.defect_ids, *right.defect_ids))),
            "evidence_channels": tuple(
                sorted({*left.evidence_channels, *right.evidence_channels}, key=lambda i: i.value)
            ),
            "location_corroborated": left.location_corroborated or right.location_corroborated,
            "reason_codes": tuple(dict.fromkeys((*left.reason_codes, *right.reason_codes))),
            "paths": (*left.paths, *right.paths),
        }
    )
