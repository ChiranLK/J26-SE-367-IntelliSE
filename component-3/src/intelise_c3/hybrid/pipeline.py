"""Central orchestrator of the rule-governed hybrid generation pipeline.

Validated C1 + released C2 -> contract validation -> normalized context ->
KB + rule engine -> bounded stack selection -> deterministic templates (+ RAG
audit, + bounded OpenRouter only for rule-unsupported custom modules) ->
design/architecture verification -> living traceability -> immutable run.

The same service performs scoped regeneration (approved requirement change,
C4 defect feedback) and the exact-artifact deployment gate. Verification
agents only report; every code change goes through this workflow.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
from typing import Any
from uuid import uuid4

from fastapi import status

from intelise_c3.contracts.hybrid import (
    C4DefectSubmission,
    C4ReadinessSignal,
    ConvergenceState,
    DeploymentGateRequest,
    EvidenceClass,
    HybridGenerationRequest,
    HybridInputPackage,
    InputClassification,
    ModuleDigest,
    PolicyAcceptance,
    ReadinessStatus,
    RequirementChangeRequest,
    SemanticPreservation,
    C4DefectFeedback,
    C4DefectCategory,
    C4Severity,
)
from intelise_c3.contracts.stack_selection import StackSelectionCriteria, StackSelectionRequest
from intelise_c3.core.config import Settings
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.generation.evidence import canonical_sha256
from intelise_c3.hybrid.gpa_spec import GpaSpec, GpaSpecError, build_gpa_spec
from intelise_c3.hybrid.gpa_templates import (
    DATABASE_ENTITIES,
    MODULES,
    TEMPLATE_SET_REF,
    TEST_SEAMS,
    operations_for,
    render_modules,
    seam_applies,
    seam_module_id,
)
from intelise_c3.hybrid.input_contracts import HybridContractValidator, ValidatedInput
from intelise_c3.hybrid.knowledge_base import KnowledgeBase, load_knowledge_base
from intelise_c3.hybrid.trace_precision import requirement_links
from intelise_c3.hybrid.living_trace import (
    DIRECT,
    HOSTING,
    LivingTraceGraph,
    LivingTraceStore,
    evolve,
    graph_id_for,
    node_id,
)
from intelise_c3.hybrid.llm_gateway import (
    PROMPT_VERSION,
    BoundedModuleContext,
    InterfaceMethod,
    OpenRouterModuleGateway,
)
from intelise_c3.hybrid.llm_frontend import (
    FRONTEND_GATE_VERSION,
    TRUSTED_PATHS,
    ensure_gate_image,
    generate_frontend,
    group_files,
    shared_contract,
)
from intelise_c3.hybrid.llm_modules import (
    LLM_BACKEND_MODULES,
    attribute_slice,
    module_context,
    service_contract_notes,
    validation_contract_notes,
)
from intelise_c3.hybrid.llm_sandbox import (
    BENCHMARK_VERSION,
    docker_available,
    failures_as_findings,
    run_sandbox,
    service_spec,
    validation_spec,
)
from intelise_c3.hybrid.rule_engine import (
    GenerationTarget,
    RuleEngine,
    RuleOutcome,
    RuleSet,
    TargetDecision,
    load_rule_set,
)
from intelise_c3.hybrid.verification import extract_symbols, verify_architecture, verify_design_to_code
from intelise_c3.llm.client import LLMClient
from intelise_c3.rag.best_practices import BestPracticeStore, RetrievalQuery, format_rules_for_prompt
from intelise_c3.rag.runtime import RagRuntime
from intelise_c3.scripts.generate_task_mvp import build_simulated_stack_criteria
from intelise_c3.services.stack_selection import StackSelectionService

HYBRID_GENERATOR_VERSION = "c3-hybrid-generator-1.0.0"
MANIFEST_SCHEMA = "C3_HYBRID_MANIFEST_V1"
PROJECT_DIR = "generated-project"
EVIDENCE_DIR = "evidence"
_EVIDENCE_PREFIXES = ("generation-manifest.json", "traceability/")
_CROSS_CUTTING = ("API", "DATABASE", "TEST_SEAM", "ARCHITECTURE", "TRACEABILITY", "DEPLOYMENT", "DEPLOYMENT_GATE")
_DEFECT_INJECTION = (
    "const scaled = Math.floor((2 * numerator * scale + denominator) / (2 * denominator));",
    "const scaled = Math.floor((numerator * scale) / denominator); // SIMULATED DEFECT: truncation",
)
LLMClientFactory = Callable[[], "LLMClient | None"]
#: Module origins whose bytes came from a model. They are never silently regenerated from templates.
LLM_ORIGINS = frozenset({"OPENROUTER", "TEAMSOCLO"})
GOVERNANCE_RULE_ID = "R-LLM-BACKEND-001"


@dataclass(frozen=True)
class BackendLlm:
    """The provider that may write backend logic when the caller explicitly selects LLM mode."""

    provider: str
    model: str
    client_factory: LLMClientFactory
    #: Larger completion cap and timeout for UI file groups (None -> client_factory is used).
    frontend_client_factory: LLMClientFactory | None = None
#: PP1 boundary: the gate is a contract stub; only the local sandbox preview executes anything.
PP1_SCOPE = {
    "current_execution": "LOCAL_SANDBOX_PREVIEW",
    "ci_cd_implementation": "DEFERRED_AFTER_PP1",
    "production_deployment": "OUT_OF_SCOPE_FOR_PP1",
    "real_c4_readiness_integration": "PENDING_INTEGRATION",
}


def _error(code: str, message: str, status_code: int = status.HTTP_409_CONFLICT, field_name: str | None = None) -> ApplicationError:
    return ApplicationError([ErrorDetail(code=code, field=field_name, message=message)], status_code=status_code)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def _digest_of(files: dict[str, str]) -> str:
    return canonical_sha256(sorted((path, _sha(content)) for path, content in files.items()))


@dataclass
class ModuleBuild:
    module_id: str
    files: dict[str, str]
    layer: str
    artifact_type: str
    template_id: str
    origin: str
    rules: set[str] = field(default_factory=set)
    requirements: dict[str, str] = field(default_factory=dict)
    knowledge: set[str] = field(default_factory=set)
    uml_classes: tuple[str, ...] = ()
    status: str = "ACCEPTED"
    created_in: dict[str, str] = field(default_factory=dict)
    change: str = "GENERATED"

    @property
    def digest(self) -> str:
        return _digest_of(self.files)


@dataclass
class BuildResult:
    validated: ValidatedInput
    spec: GpaSpec | None
    stack: dict[str, Any]
    decisions: list[TargetDecision]
    modules: dict[str, ModuleBuild]
    rag: list[dict[str, Any]]
    ledger: list[dict[str, Any]]
    review_items: list[dict[str, Any]]
    policy_record: dict[str, Any] | None
    generation_mode: str = "TEMPLATE"
    backend_llm: dict[str, Any] | None = None
    frontend_llm: dict[str, Any] | None = None


class HybridPipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        llm_client_factory: LLMClientFactory | None = None,
        knowledge_base: KnowledgeBase | None = None,
        rule_set: RuleSet | None = None,
        rag_store: BestPracticeStore | None = None,
        trace_store: LivingTraceStore | None = None,
        backend_llm: BackendLlm | None = None,
        sandbox_runner=subprocess.run,
    ) -> None:
        self.settings = settings
        self.backend_llm = backend_llm
        self._sandbox_runner = sandbox_runner
        self.kb = knowledge_base or load_knowledge_base()
        self.rules = rule_set or load_rule_set(knowledge_base=self.kb)
        self.engine = RuleEngine(self.rules)
        self.root = Path(settings.generated_workspace_root) / "hybrid"
        self.store = trace_store or LivingTraceStore(settings.traceability_store_path)
        if rag_store is not None:
            self.rag_store, self.rag_backend, self.rag_corpus = rag_store, "custom", None
        else:
            runtime = RagRuntime.from_settings(settings)
            self.rag_store, self.rag_backend, self.rag_corpus = runtime.store, runtime.backend, runtime.rule_corpus_sha256
        self._client_factory = llm_client_factory

    # ------------------------------------------------------------------ catalogue
    def knowledge_summary(self) -> dict[str, Any]:
        return self.kb.summary()

    def rules_summary(self) -> dict[str, Any]:
        return self.rules.summary()

    def contract_report(self, package: HybridInputPackage) -> dict[str, Any]:
        try:
            return HybridContractValidator().validate(package).report.as_json()
        except ApplicationError as error:
            return {
                "status": "REJECTED",
                "input_classification": package.input_classification.value,
                "c1_evidence_class": package.c1.evidence_class.value,
                "c2_evidence_class": package.c2.evidence_class.value,
                "findings": [e.model_dump() for e in error.errors],
                "rule_ids": ["R-INPUT-001@1.0.0", "R-INPUT-002@1.0.0"],
            }

    def policy_acceptance_template(self) -> dict[str, Any]:
        policy = self.kb.gpa_policy
        return {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "policy_digest_sha256": policy.digest_sha256,
            "authority_status": policy.authority_status,
            "requires_explicit_acceptance": policy.requires_explicit_acceptance,
            "acknowledges_sample_status_required": policy.authority_status == "SAMPLE_RESEARCH_POLICY",
        }

    # ------------------------------------------------------------------ build
    def _check_policy(self, acceptance: PolicyAcceptance | None) -> dict[str, Any]:
        policy = self.kb.gpa_policy
        if policy is None:
            raise _error("GPA_POLICY_MISSING", "No grading policy exists in the Knowledge Base; generation is REVIEW_REQUIRED.")
        if policy.requires_explicit_acceptance:
            if acceptance is None:
                raise _error("POLICY_ACCEPTANCE_REQUIRED",
                             f"Policy {policy.policy_id} v{policy.policy_version} is {policy.authority_status}; explicit acceptance is required.",
                             field_name="policy_acceptance")
            if (acceptance.policy_id, acceptance.policy_version, acceptance.policy_digest_sha256) != (
                policy.policy_id, policy.policy_version, policy.digest_sha256
            ):
                raise _error("POLICY_ACCEPTANCE_MISMATCH",
                             "The acceptance is bound to a different policy id, version or digest.", field_name="policy_acceptance")
            if policy.authority_status == "SAMPLE_RESEARCH_POLICY" and not acceptance.acknowledges_sample_status:
                raise _error("SAMPLE_POLICY_NOT_ACKNOWLEDGED",
                             "The policy is a SAMPLE_RESEARCH_POLICY; acceptance must acknowledge that status.", field_name="policy_acceptance")
        return {
            "policy": policy.disclosure(),
            "acceptance": acceptance.model_dump(mode="json") if acceptance else None,
            "accepted_at_utc": _now(),
        }

    def _select_stack(self, validated: ValidatedInput, criteria: StackSelectionCriteria | None) -> dict[str, Any]:
        simulated = criteria is None
        report = StackSelectionService().select(
            StackSelectionRequest(design_context=validated.design_context, criteria=criteria or build_simulated_stack_criteria())
        )
        selected = report.selected_stack
        stack_id = selected.candidate.candidate_id
        kb_stack = self.kb.stacks.get(stack_id, {})
        return {
            "stack_id": stack_id,
            "frontend": selected.candidate.frontend,
            "backend": selected.candidate.backend,
            "database": kb_stack.get("database"),
            "generator_status": kb_stack.get("hybrid_generator_status", "NOT_IMPLEMENTED"),
            "score": selected.normalized_score,
            "reason": report.selection_reason,
            "criteria_source": "SIMULATED_RESEARCHER_CRITERIA" if simulated else "CALLER_SUPPLIED_CRITERIA",
            "candidates": [
                {"stack_id": c.candidate.candidate_id, "eligible": c.eligible, "score": c.normalized_score,
                 "kb_generator_status": self.kb.stacks.get(c.candidate.candidate_id, {}).get("hybrid_generator_status")}
                for c in report.candidate_calculations
            ],
            "report_sha256": canonical_sha256(report),
        }

    def _class_role(self, parsed) -> str:
        roles = self.kb.item("KB-UML-CLASS-ROLES")
        for suffix, role in roles["suffix_roles"].items():
            if parsed.name.endswith(suffix):
                return role
        return roles["default_role_with_attributes_only"] if parsed.attributes and not parsed.methods else roles["default_role_otherwise"]

    def _targets(self, validated: ValidatedInput, stack: dict[str, Any], domain: str | None, persistence: bool) -> list[GenerationTarget]:
        package, design = validated.package, validated.design_context
        anchors: dict[str, list[str]] = {}
        uml_of: dict[str, str] = {}
        for anchor in package.c2.requirement_uml_anchors:
            anchors.setdefault(anchor.uml_element, []).append(anchor.requirement_id)
            uml_of[anchor.uml_element] = anchor.uml_id
        roles = {parsed.name: self._class_role(parsed) for parsed in design.classes}
        targets = [
            GenerationTarget("CONTRACT:C1", "CONTRACT", {"contract": "C1"}),
            GenerationTarget("CONTRACT:C2", "CONTRACT", {"contract": "C2"}),
            GenerationTarget(f"STACK:{stack['stack_id']}", "STACK",
                             {"stack_id": stack["stack_id"], "generator_status": stack["generator_status"]}),
        ]
        for parsed in design.classes:
            targets.append(GenerationTarget(
                f"UML_CLASS:{parsed.name}", "UML_CLASS",
                {"domain": domain, "stack_id": stack["stack_id"], "class_name": parsed.name, "class_role": roles[parsed.name],
                 "methods": [m.name for m in parsed.methods], "attributes": [a.name for a in parsed.attributes]},
                tuple(sorted(set(anchors.get(parsed.name, ())))),
                (f"{uml_of.get(parsed.name, parsed.source_uml_id)}#{parsed.name}",),
            ))
        for requirement in package.c1.requirements:
            if requirement.constraints:
                targets.append(GenerationTarget(
                    f"REQUIREMENT:{requirement.requirement_id}", "REQUIREMENT",
                    {"domain": domain, "has_constraints": True, "requirement_type": requirement.requirement_type,
                     "constraint_kinds": sorted({c.kind.value for c in requirement.constraints})},
                    (requirement.requirement_id,),
                ))
        for screen in package.c2.ui_specification:
            targets.append(GenerationTarget(
                f"UI_SCREEN:{screen.screen_id}", "UI_SCREEN",
                {"domain": domain, "components": sorted({c.kind.value for c in screen.components})},
                tuple(screen.requirement_ids),
            ))
        scoped = {
            "API": tuple(sorted({r for name, role in roles.items() if role in {"SERVICE", "REPOSITORY"} for r in anchors.get(name, ())})),
            "DATABASE": tuple(sorted({r for name, role in roles.items() if role == "REPOSITORY" for r in anchors.get(name, ())})),
            "TEST_SEAM": tuple(sorted({r for seam in TEST_SEAMS for c in seam.classes() for r in anchors.get(c, ())})),
        }
        for concern in _CROSS_CUTTING:
            if concern == "DATABASE" and not persistence:
                continue
            targets.append(GenerationTarget(
                f"CROSS_CUTTING:{concern}", "CROSS_CUTTING",
                {"domain": domain, "stack_id": stack["stack_id"], "concern": concern, "persistence_required": persistence},
                scoped.get(concern, ()),
            ))
        return targets

    def _rag(self, module_id: str, template, applied: bool) -> dict[str, Any]:
        query = RetrievalQuery(
            task=f"{module_id} {template.template_id} {template.layer.lower()} generate",
            stack=template.rag_stack, layer=template.rag_layer, artifact_type=template.artifact_type,
            module=module_id, task_type="GENERATE", top_k=4, max_context_tokens=2000,
        )
        hits = self.rag_store.search(query) if self.rag_store is not None else []
        return {
            "module_id": module_id,
            "query": {"stack": query.stack, "layer": query.layer, "artifact_type": query.artifact_type,
                      "module": query.module, "task_type": query.task_type, "top_k": query.top_k,
                      "max_context_tokens": query.max_context_tokens},
            "hits": [hit.evidence() for hit in hits],
            "context_tokens": sum(hit.card.token_estimate for hit in hits),
            "context_digest_sha256": canonical_sha256([hit.evidence() for hit in hits]),
            "applied_to_prompt": applied and bool(hits),
            "authority": "GUIDANCE_ONLY - cannot override requirements, UML or the KB policy",
            "_prompt": format_rules_for_prompt([hit.card for hit in hits]),
        }

    def _client(self) -> LLMClient | None:
        return self._client_factory() if self._client_factory else None

    async def _custom_module(self, validated: ValidatedInput, stack: dict[str, Any], decision: TargetDecision,
                             parsed, rule_refs: list[str]) -> tuple[ModuleBuild | None, dict[str, Any], list[dict[str, Any]], list[str]]:
        module_id = f"custom.{_kebab(parsed.name)}"
        path = f"backend/src/custom/{parsed.name[0].lower()}{parsed.name[1:]}.js"
        template = MODULES["be.service"]
        rag = self._rag(module_id, template, applied=True)
        requirements = [r for r in validated.package.c1.requirements if r.requirement_id in decision.requirement_ids]
        attributes = "\n".join(f"  +{a.name}: {a.type_name}" for a in parsed.attributes)
        methods = "\n".join(
            f"  +{m.name}({', '.join(f'{p.name}: {p.type_name}' for p in m.parameters)}): {m.return_type or 'void'}" for m in parsed.methods
        )
        context = BoundedModuleContext(
            module_id=module_id, target_path=path, class_name=parsed.name,
            methods=tuple(InterfaceMethod(m.name, tuple(p.name for p in m.parameters)) for m in parsed.methods),
            requirement_slices=tuple({"requirement_id": r.requirement_id, "requirement_version": r.requirement_version,
                                      "statement": r.statement} for r in requirements),
            uml_slice=f"class {parsed.name} {{\n{attributes}\n{methods}\n}}".replace("\n\n", "\n"),
            uml_version=validated.package.c2.uml_version, stack_id=stack["stack_id"], rule_ids=tuple(rule_refs),
            kb_digest=self.kb.digest_sha256, rule_set_digest=self.rules.digest_sha256,
            rag_prompt=rag["_prompt"], rag_digest=rag["context_digest_sha256"],
        )
        gateway = OpenRouterModuleGateway(
            self._client(), provider="openrouter", model=self.settings.openrouter_model,
            cache_dir=self.settings.hybrid_llm_cache_dir, max_input_tokens=self.settings.hybrid_llm_max_input_tokens,
        )
        result = await gateway.generate(context)
        for entry in result.ledger:
            entry["module_id"] = module_id
            entry["cache_key"] = result.cache_key
        if result.status != "ACCEPTED":
            return None, rag, result.ledger, [f"{module_id}: {result.status}"] + result.reasons
        build = ModuleBuild(module_id, {path: result.content}, "SERVICE", "BUSINESS_LOGIC", PROMPT_VERSION,
                            "OPENROUTER", set(rule_refs), {r: DIRECT for r in decision.requirement_ids},
                            {"KB-TEST-SEAMS"}, (parsed.name,), status="REVIEW_REQUIRED_BEFORE_WIRING")
        return build, rag, result.ledger, []

    async def _build(self, package: HybridInputPackage, acceptance: PolicyAcceptance | None,
                     criteria: StackSelectionCriteria | None, allow_llm: bool, *,
                     llm_backend_logic: bool = False, workspace: str = "gpa-hybrid",
                     llm_frontend: bool = False, frontend_shape_only: bool = False) -> BuildResult:
        validated = HybridContractValidator().validate(package)
        policy_record = self._check_policy(acceptance)
        design = validated.design_context
        class_names = {parsed.name for parsed in design.classes}
        recognition = set(self.kb.item("KB-GPA-DOMAIN")["recognition"]["required_uml_classes"])
        domain = "gpa" if recognition <= class_names else None
        stack = self._select_stack(validated, criteria)
        spec: GpaSpec | None = None
        if domain == "gpa":
            try:
                spec = build_gpa_spec(package, design, self.kb)
            except GpaSpecError as error:
                raise _error(error.code, str(error), status.HTTP_422_UNPROCESSABLE_ENTITY) from error
        if spec is not None and spec.clear_history and (llm_backend_logic or llm_frontend or frontend_shape_only):
            raise _error("CLEAR_HISTORY_LLM_UNSUPPORTED",
                         "The released design declares clearHistory(); the LLM backend/frontend modes are not wired for it yet. "
                         "Generate this design in TEMPLATE mode.", status.HTTP_422_UNPROCESSABLE_ENTITY)
        if spec is not None and llm_backend_logic:
            spec = replace(spec, llm_backend_logic=True)
        if spec is not None and (llm_frontend or frontend_shape_only):
            spec = replace(spec, llm_frontend=True)
        persistence = bool(spec and spec.persistence_required)
        targets = self._targets(validated, stack, domain, persistence)
        if llm_backend_logic:
            targets.append(GenerationTarget(
                "CROSS_CUTTING:LLM_BACKEND_LOGIC", "CROSS_CUTTING",
                {"domain": domain, "stack_id": stack["stack_id"], "concern": "LLM_BACKEND_LOGIC", "llm_backend_logic": True}))
        if llm_frontend:
            targets.append(GenerationTarget(
                "CROSS_CUTTING:LLM_FRONTEND", "CROSS_CUTTING",
                {"domain": domain, "stack_id": stack["stack_id"], "concern": "LLM_FRONTEND", "llm_frontend": True}))
        decisions = self.engine.decide_all(targets)
        by_id = {d.target_id: d for d in decisions}
        stack_decision = by_id[f"STACK:{stack['stack_id']}"]
        if stack_decision.outcome is not RuleOutcome.MATCHED:
            raise _error("STACK_UNSUPPORTED",
                         f"Selected stack {stack['stack_id']} has no implemented hybrid template set; C3 does not substitute another stack.",
                         status.HTTP_422_UNPROCESSABLE_ENTITY)
        if domain is None:
            raise _error("DOMAIN_UNSUPPORTED",
                         "No Knowledge Base domain pack recognizes this design; no implementation is fabricated.",
                         status.HTTP_422_UNPROCESSABLE_ENTITY)

        all_reqs = [r.requirement_id for r in package.c1.requirements]
        # Cross-cutting modules implement only requirements whose design classes a rule actually covers.
        covered_reqs = {r for d in decisions if d.kind in {"UML_CLASS", "REQUIREMENT", "UI_SCREEN"}
                        and d.outcome is RuleOutcome.MATCHED for r in d.requirement_ids}
        plan: dict[str, ModuleBuild] = {}
        review_items: list[dict[str, Any]] = []
        for decision in decisions:
            if decision.outcome is not RuleOutcome.MATCHED:
                continue
            if decision.kind == "CROSS_CUTTING":
                decision.requirement_ids = tuple(r for r in decision.requirement_ids if r in covered_reqs)
            for rule in decision.matched_rules:
                for module_id in rule.module_ids:
                    if module_id not in MODULES:
                        raise _error("RULE_TEMPLATE_MISSING", f"Rule {rule.ref} names module {module_id}, which has no template.",
                                     status.HTTP_500_INTERNAL_SERVER_ERROR)
                    template = MODULES[module_id]
                    build = plan.setdefault(module_id, ModuleBuild(
                        module_id, {}, template.layer, template.artifact_type, template.template_id, "TEMPLATE",
                        uml_classes=template.uml_classes))
                    build.rules.add(rule.ref)
                    build.knowledge.update(rule.requires_knowledge)
                    evidence = HOSTING if decision.kind == "STACK" or not decision.requirement_ids else DIRECT
                    for requirement_id in decision.requirement_ids:
                        if build.requirements.get(requirement_id) != DIRECT:
                            build.requirements[requirement_id] = evidence
        for build in plan.values():
            if not any(kind == DIRECT for kind in build.requirements.values()) or not build.requirements:
                for requirement_id in all_reqs:
                    build.requirements.setdefault(requirement_id, HOSTING)
        if llm_frontend or frontend_shape_only:
            # The two template modules are replaced by one UI module whose files an LLM writes (or whose bytes are pinned).
            ui = ModuleBuild("fe.ui", {}, "FRONTEND", "FRONTEND", MODULES["fe.ui"].template_id, "TEMPLATE",
                             uml_classes=MODULES["fe.ui"].uml_classes)
            for old_id in ("fe.gpa-form", "fe.validation"):
                old = plan.pop(old_id, None)
                if old is None:
                    continue
                ui.rules |= old.rules
                ui.knowledge |= old.knowledge
                for requirement_id, evidence in old.requirements.items():
                    if ui.requirements.get(requirement_id) != DIRECT:
                        ui.requirements[requirement_id] = evidence
            plan["fe.ui"] = ui
        rendered = render_modules(spec, [m for m in plan if m != "fe.ui"])
        for module_id, files in rendered.items():
            plan[module_id].files = files

        rag_evidence = [self._rag(module_id, MODULES[module_id], applied=False) for module_id in sorted(plan)]
        ledger: list[dict[str, Any]] = []
        backend_llm_record: dict[str, Any] | None = None
        if llm_backend_logic:
            backend_llm_record = await self._llm_backend_logic(
                validated=validated, stack=stack, spec=spec, plan=plan, decisions=decisions,
                rag_evidence=rag_evidence, ledger=ledger, workspace=workspace)
        parsed_by_name = {parsed.name: parsed for parsed in design.classes}
        frontend_llm_record: dict[str, Any] | None = None
        if llm_frontend:
            frontend_llm_record = await self._llm_frontend(
                validated=validated, stack=stack, spec=spec, plan=plan, decisions=decisions,
                rag_evidence=rag_evidence, ledger=ledger, workspace=workspace)
        for decision in decisions:
            if decision.kind != "UML_CLASS" or decision.outcome is RuleOutcome.MATCHED:
                if decision.outcome in (RuleOutcome.AMBIGUOUS, RuleOutcome.REVIEW_REQUIRED, RuleOutcome.FAILED):
                    review_items.append({"target_id": decision.target_id, "outcome": decision.outcome.value, "reasons": decision.reasons})
                continue
            parsed = parsed_by_name[decision.target_id.split(":", 1)[1]]
            custom = self.engine.decide(GenerationTarget(
                f"CUSTOM_CLASS:{parsed.name}", "CUSTOM_CLASS",
                {"class_role": self._class_role(parsed), "allow_llm": allow_llm, "has_methods": bool(parsed.methods)},
                decision.requirement_ids, decision.uml_refs))
            decisions.append(custom)
            if decision.outcome is not RuleOutcome.UNSUPPORTED or custom.outcome is not RuleOutcome.MATCHED:
                review_items.append({
                    "target_id": decision.target_id, "outcome": "HUMAN_REVIEW_REQUIRED",
                    "reasons": decision.reasons + (["Bounded LLM generation not permitted for this target (allow_llm_for_unsupported=false or class is not a service)."]
                                                   if custom.outcome is not RuleOutcome.MATCHED else custom.reasons),
                })
                continue
            build, rag, entries, problems = await self._custom_module(
                validated, stack, decision, parsed, [rule.ref for rule in custom.matched_rules])
            rag_evidence.append(rag)
            ledger.extend(entries)
            if build is None:
                review_items.append({"target_id": decision.target_id, "outcome": "HUMAN_REVIEW_REQUIRED", "reasons": problems})
            else:
                plan[build.module_id] = build
                review_items.append({"target_id": decision.target_id, "outcome": "REVIEW_REQUIRED_BEFORE_WIRING",
                                     "reasons": ["Model-generated custom module passed static validation; a human must review it before it is wired into routes."]})
        for item in rag_evidence:
            item.pop("_prompt", None)
        return BuildResult(validated, spec, stack, decisions, plan, rag_evidence, ledger, review_items, policy_record,
                           generation_mode="+".join(m for m, on in (("LLM_BACKEND_LOGIC", llm_backend_logic), ("LLM_FRONTEND", llm_frontend)) if on) or "TEMPLATE",
                           backend_llm=backend_llm_record, frontend_llm=frontend_llm_record)

    # ------------------------------------------------------------------ LLM backend logic (explicit opt-in)
    def _human_review(self, workspace: str, package: HybridInputPackage, record: dict[str, Any]) -> ApplicationError:
        """Preserve every attempt and stop. There is no template fallback and no artifact is created."""
        folder = self.root / workspace / "_human-review"
        folder.mkdir(parents=True, exist_ok=True)
        review_id = f"review-{datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz')}-{uuid4().hex[:6]}"
        document = {"review_id": review_id, "status": "HUMAN_REVIEW_REQUIRED", "recorded_at_utc": _now(),
                    "project_id": package.c1.project_id, "srs_version": package.c1.srs_version,
                    "uml_version": package.c2.uml_version, "template_fallback": "NOT_APPLIED",
                    "artifact_created": False, **record}
        target = folder / f"{review_id}.json"
        pending = target.with_suffix(".pending")
        pending.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
        os.replace(pending, target)
        reasons = "; ".join(record.get("reasons", [])[:3])
        frontend = record.get("mode") == "LLM_FRONTEND"
        return _error("HUMAN_REVIEW_REQUIRED",
                      f"{'LLM frontend' if frontend else 'LLM backend logic'} was not accepted ({reasons}). "
                      "No template fallback was applied and no artifact was created. "
                      f"Attempts, ledger and rejected outputs: hybrid/{workspace}/_human-review/{review_id}.json",
                      status.HTTP_422_UNPROCESSABLE_ENTITY, "llm_frontend" if frontend else "llm_backend_logic")

    async def _llm_frontend(self, *, validated: ValidatedInput, stack: dict[str, Any], spec: GpaSpec,
                            plan: dict[str, ModuleBuild], decisions: list[TargetDecision],
                            rag_evidence: list[dict[str, Any]], ledger: list[dict[str, Any]], workspace: str) -> dict[str, Any]:
        package, design = validated.package, validated.design_context
        governance = next((rule for d in decisions for rule in d.matched_rules if rule.rule_id == "R-LLM-FRONTEND-001"), None)
        if governance is None:
            raise _error("LLM_RULE_NOT_MATCHED", "Rule R-LLM-FRONTEND-001 did not match; LLM frontend is not permitted.",
                         status.HTTP_422_UNPROCESSABLE_ENTITY)
        backend = self.backend_llm
        record: dict[str, Any] = {"mode": "LLM_FRONTEND", "governance_rule": governance.ref, "gate_version": FRONTEND_GATE_VERSION,
                                  "provider": backend.provider if backend else None, "model": backend.model if backend else None,
                                  "groups": sorted(group_files(spec)), "attempt_limit_per_group": 2,
                                  "trusted_scaffold": sorted(TRUSTED_PATHS) + ["frontend/package.json", "frontend/index.html",
                                                                               "frontend/vite.config.js", "frontend/src/main.jsx"],
                                  "gate": {"build": "vite build", "tests": "vitest + jsdom", "network": "none", "root": "read-only", "mounts": "none"}}
        factory = (backend.frontend_client_factory or backend.client_factory) if backend else None
        client = factory() if factory else None
        if backend is None or client is None:
            raise self._human_review(workspace, package, {**record, "reasons": [
                "TEAMSOCLO_UNAVAILABLE: the TeamSocLo experiment gate is off or no API key is configured; no model was called."]})
        available, detail = docker_available(self._sandbox_runner)
        if available:
            available, detail = ensure_gate_image(self._sandbox_runner)
        if not available:
            raise self._human_review(workspace, package, {**record, "reasons": [
                f"GATE_UNAVAILABLE: Docker and the UI gate image are needed to verify model-written UI safely ({detail}); no model was called."]})
        ui = plan["fe.ui"]
        direct = sorted(rid for rid, evidence in ui.requirements.items() if evidence == DIRECT)
        requirements = {r.requirement_id: r for r in package.c1.requirements}
        slices = tuple({"requirement_id": rid, "requirement_version": requirements[rid].requirement_version,
                        "statement": requirements[rid].statement} for rid in direct)
        classes = {c.name: c for c in design.classes}
        uml_slice = (attribute_slice("ModuleResult", classes["ModuleResult"].attributes) + chr(10)
                     + attribute_slice("GpaCalculation", classes["GpaCalculation"].attributes))
        notes = shared_contract(spec, [s.model_dump(mode="json") for s in package.c2.ui_specification])
        rag = self._rag("fe.ui", MODULES["fe.ui"], applied=True)
        rag_prompt = rag.pop("_prompt")
        rag_evidence[:] = [item for item in rag_evidence if item["module_id"] != "fe.ui"] + [rag]
        groups = group_files(spec)
        contexts: dict[str, BoundedModuleContext] = {}
        for name, paths in groups.items():
            others = sorted(p for n, ps in groups.items() if n != name for p in ps)
            contexts[name] = BoundedModuleContext(
                module_id=f"fe.ui:{name}", target_path="(file bundle)", class_name=name, methods=(),
                requirement_slices=slices, uml_slice=uml_slice, uml_version=package.c2.uml_version, stack_id=stack["stack_id"],
                rule_ids=tuple(sorted(ui.rules | {governance.ref})), kb_digest=self.kb.digest_sha256,
                rule_set_digest=self.rules.digest_sha256, rag_prompt=rag_prompt, rag_digest=rag["context_digest_sha256"],
                contract_notes=notes + chr(10) + f"YOUR GROUP '{name}' WRITES: {', '.join(paths)}." + chr(10)
                + f"THE OTHER GROUP WRITES (you may import these, follow their contract exactly): {', '.join(others)}.",
                kind="bundle", check_version=FRONTEND_GATE_VERSION, bundle_paths=tuple(paths),
                # importable but never writable here: the trusted scaffold and the other group's files
                trusted_paths=tuple(TRUSTED_PATHS) + tuple(others),
                max_input_tokens=self.settings.hybrid_llm_frontend_max_input_tokens)
        gateway = OpenRouterModuleGateway(client, provider=backend.provider, model=backend.model,
                                          cache_dir=self.settings.hybrid_llm_cache_dir,
                                          max_input_tokens=self.settings.hybrid_llm_frontend_max_input_tokens)
        trusted = {path: content for module_id in ("fe.app-shell", "fe.policy") for path, content in plan[module_id].files.items()}
        outcome = await generate_frontend(gateway=gateway, contexts=contexts, trusted_files=trusted, spec=spec, runner=self._sandbox_runner)
        ledger.extend(outcome.ledger)
        if not outcome.accepted:
            raise self._human_review(workspace, package, {
                **record, "failures": outcome.failures, "gate": outcome.gate, "repaired_groups": outcome.repaired_groups,
                "reasons": [f"{f['module_id']}: {f['status']} {' '.join(f['reasons'])}".strip()[:600] for f in outcome.failures]})
        ui.files = dict(sorted(outcome.files.items()))
        ui.origin = "TEAMSOCLO"
        ui.template_id = f"llm:{PROMPT_VERSION}"
        ui.status = "ACCEPTED_LLM_UI_GATE_PASSED"
        ui.created_in = {}
        ui.rules.add(governance.ref)
        ui.knowledge.update(governance.requires_knowledge)
        return {**record, "accepted_files": sorted(ui.files), "repaired_groups": outcome.repaired_groups,
                "gate_result": {"build_ok": outcome.gate["build"]["ok"], "passed": outcome.gate["passed"], "total": outcome.gate["total"],
                                "cases": [{"id": t["id"], "passed": t["passed"]} for t in outcome.gate["results"]]}}

    async def _llm_backend_logic(self, *, validated: ValidatedInput, stack: dict[str, Any], spec: GpaSpec,
                                 plan: dict[str, ModuleBuild], decisions: list[TargetDecision],
                                 rag_evidence: list[dict[str, Any]], ledger: list[dict[str, Any]], workspace: str) -> dict[str, Any]:
        package, design = validated.package, validated.design_context
        governance = next((rule for d in decisions for rule in d.matched_rules if rule.rule_id == GOVERNANCE_RULE_ID), None)
        if governance is None:
            raise _error("LLM_RULE_NOT_MATCHED", f"Rule {GOVERNANCE_RULE_ID} did not match; LLM backend logic is not permitted.",
                         status.HTTP_422_UNPROCESSABLE_ENTITY)
        backend = self.backend_llm
        record: dict[str, Any] = {"mode": "LLM_BACKEND_LOGIC", "governance_rule": governance.ref, "benchmark_version": BENCHMARK_VERSION,
                                  "provider": backend.provider if backend else None, "model": backend.model if backend else None,
                                  "modules": sorted(LLM_BACKEND_MODULES), "attempt_limit": 2,
                                  "sandbox": {"image": "node:24-bookworm-slim", "network": "none", "root": "read-only", "mounts": "none"}}
        client = backend.client_factory() if backend else None
        if backend is None or client is None:
            raise self._human_review(workspace, package, {**record, "reasons": [
                "TEAMSOCLO_UNAVAILABLE: the TeamSocLo experiment gate is off or no API key is configured; no model was called."]})
        available, detail = docker_available(self._sandbox_runner)
        if not available:
            raise self._human_review(workspace, package, {**record, "reasons": [
                f"SANDBOX_UNAVAILABLE: Docker is needed to benchmark model-written code safely ({detail}); no model was called."]})
        requirements = {r.requirement_id: r for r in package.c1.requirements}
        classes = {c.name: c for c in design.classes}
        gateway = OpenRouterModuleGateway(client, provider=backend.provider, model=backend.model,
                                          cache_dir=self.settings.hybrid_llm_cache_dir,
                                          max_input_tokens=self.settings.hybrid_llm_max_input_tokens)
        loop = asyncio.get_running_loop()
        accepted: dict[str, str] = {}
        failures: list[dict[str, Any]] = []
        for module_id, (kind, name, path) in LLM_BACKEND_MODULES.items():
            module = plan[module_id]
            direct = sorted(rid for rid, evidence in module.requirements.items() if evidence == DIRECT)
            slices = tuple({"requirement_id": rid, "requirement_version": requirements[rid].requirement_version,
                            "statement": requirements[rid].statement} for rid in direct)
            if kind == "class":
                service_class = classes["GpaCalculationService"]
                uml_slice = "class GpaCalculationService {" + chr(10) + chr(10).join(
                    f"  +{m.name}({', '.join(f'{q.name}: {q.type_name}' for q in m.parameters)}): {m.return_type or 'void'}"
                    for m in service_class.methods) + chr(10) + "}"
                methods = tuple(InterfaceMethod(m.name, tuple(q.name for q in m.parameters)) for m in service_class.methods)
                notes = service_contract_notes(self.kb)
                bench = service_spec(spec, path.removeprefix("backend/"))
            else:
                uml_slice = attribute_slice("ModuleResult", classes["ModuleResult"].attributes)
                methods = (InterfaceMethod(name, ("body", "gradingPolicy")),)
                notes = validation_contract_notes(spec)
                bench = validation_spec(spec, path.removeprefix("backend/"))
            rag = self._rag(module_id, MODULES[module_id], applied=True)
            rag_prompt = rag.pop("_prompt")
            rag_evidence[:] = [item for item in rag_evidence if item["module_id"] != module_id] + [rag]
            context = module_context(
                module_id=module_id, rule_ids=tuple(sorted(module.rules | {governance.ref})), requirement_slices=slices,
                uml_slice=uml_slice, uml_version=package.c2.uml_version, stack_id=stack["stack_id"], kb=self.kb,
                rule_set_digest=self.rules.digest_sha256, rag=rag, rag_prompt=rag_prompt, notes=notes,
                target_path=path, name=name, kind=kind, methods=methods)
            entry = path.removeprefix("backend/")

            async def check(content: str, _bench=bench, _entry=entry, _label=module_id) -> list[str]:
                outcome = await loop.run_in_executor(None, run_sandbox, self._sandbox_runner, {_entry: content}, _bench)
                return failures_as_findings(outcome, _label)

            result = await gateway.generate(context, use_cache=True, behaviour_check=check)
            for ledger_entry in result.ledger:
                ledger_entry["module_id"] = module_id
                ledger_entry["cache_key"] = result.cache_key
            ledger.extend(result.ledger)
            if result.status == "ACCEPTED" and result.content is not None:
                accepted[module_id] = result.content
            else:
                failures.append({"module_id": module_id, "status": result.status, "reasons": result.reasons,
                                 "ledger": result.ledger, "rejected_outputs": result.outputs})
                break
        if failures:
            raise self._human_review(workspace, package, {
                **record, "accepted_before_failure": sorted(accepted), "failures": failures,
                "reasons": [f"{f['module_id']}: {f['status']} {' '.join(f['reasons'])}".strip() for f in failures]})
        for module_id, content in accepted.items():
            module = plan[module_id]
            module.files = {LLM_BACKEND_MODULES[module_id][2]: content}
            module.origin = "TEAMSOCLO"
            module.template_id = f"llm:{PROMPT_VERSION}"
            module.status = "ACCEPTED_LLM_BENCHMARK_PASSED"
            module.created_in = {}
            module.rules.add(governance.ref)
            module.knowledge.update(governance.requires_knowledge)
        return {**record, "accepted_modules": sorted(accepted)}

    # ------------------------------------------------------------------ verification + graph
    def _all_files(self, modules: dict[str, ModuleBuild]) -> tuple[dict[str, str], dict[str, str]]:
        files: dict[str, str] = {}
        owners: dict[str, str] = {}
        for module in modules.values():
            for path, content in module.files.items():
                if path in files:
                    raise _error("DUPLICATE_ARTIFACT_PATH", f"{path} is produced by two modules.", status.HTTP_500_INTERNAL_SERVER_ERROR)
                files[path], owners[path] = content, module.module_id
        return files, owners

    def _verify(self, build: BuildResult, files: dict[str, str], owners: dict[str, str]) -> tuple[dict, dict]:
        design = verify_design_to_code(
            build.validated.design_context, files, owners, bool(build.spec and build.spec.persistence_required),
            self.kb.item("KB-TYPE-MAP")["mappings"],
            frozenset(item["target_id"].split(":", 1)[1] for item in build.review_items
                      if item["target_id"].startswith("UML_CLASS:") and item["outcome"] == "HUMAN_REVIEW_REQUIRED"),
            clear_history=bool(build.spec and build.spec.clear_history),
        )
        stack = self.kb.stacks.get(build.stack["stack_id"], {})
        architecture = verify_architecture(files, owners, self.kb.item(stack.get("architecture_item") or "KB-ARCH-NODE-LAYERED"))
        return design.as_json(None), architecture.as_json(None)

    def _graph(self, build: BuildResult, run_id: str, artifact_digest: str, files: dict[str, str]) -> LivingTraceGraph:
        package = build.validated.package
        graph = LivingTraceGraph(graph_id_for(package.c1.project_id), package.c1.project_id)
        graph.generation_run_id, graph.artifact_digest_sha256 = run_id, artifact_digest
        artifact = graph.add_node("ARTIFACT", run_id, f"Artifact {artifact_digest[:12]}", artifact_digest_sha256=artifact_digest)
        req_version = {r.requirement_id: r.requirement_version for r in package.c1.requirements}
        statements = {r.requirement_id: r.statement for r in package.c1.requirements}
        for requirement in package.c1.requirements:
            graph.add_node("REQUIREMENT", requirement.requirement_id, requirement.title,
                           requirement_version=requirement.requirement_version, requirement_type=requirement.requirement_type,
                           srs_version=package.c1.srs_version, statement_sha256=_sha(requirement.statement))
        anchors_by_class: dict[str, set[str]] = {}
        uml_nodes: dict[str, str] = {}
        for anchor in package.c2.requirement_uml_anchors:
            uml = graph.add_node("UML_ELEMENT", f"{anchor.uml_id}#{anchor.uml_element}", anchor.uml_element,
                                 uml_version=package.c2.uml_version)
            uml_nodes[anchor.uml_element] = uml
            anchors_by_class.setdefault(anchor.uml_element, set()).add(anchor.requirement_id)
            graph.add_link(node_id("REQUIREMENT", anchor.requirement_id), "DESIGNED_BY", uml,
                           detail=anchor.anchor_id, version_tag=f"v{req_version[anchor.requirement_id]}")
        for module in build.modules.values():
            mid = graph.add_node("MODULE", module.module_id, module.module_id, module_digest_sha256=module.digest,
                                 layer=module.layer, origin=module.origin, template_id=module.template_id, status=module.status)
            graph.add_link(mid, "PART_OF", artifact, version_tag=module.digest)
            for requirement_id, evidence in sorted(module.requirements.items()):
                graph.add_link(node_id("REQUIREMENT", requirement_id), "IMPLEMENTED_BY", mid, evidence=evidence,
                               version_tag=f"v{req_version[requirement_id]}")
            rule_nodes = [graph.add_node("RULE", ref.split("@")[0], ref, version=ref.split("@")[1]) for ref in sorted(module.rules)]
            kb_nodes = [graph.add_node("KNOWLEDGE_ITEM", item, item, version=self.kb.item_version(item)) for item in sorted(module.knowledge)]
            for path, content in sorted(module.files.items()):
                digest = _sha(content)
                fid = graph.add_node(
                    "CODE_FILE", path, path, sha256=digest, module_id=module.module_id, origin=module.origin,
                    requirement_ids=sorted(module.requirements), srs_version=package.c1.srs_version,
                    uml_version=package.c2.uml_version, rule_ids=sorted(module.rules),
                    template_ref=f"{TEMPLATE_SET_REF}#{module.template_id}" if module.origin == "TEMPLATE" else module.template_id,
                    generation_run_id=module.created_in.get(path, run_id), accepted=True,
                )
                graph.add_link(mid, "CONTAINS", fid, version_tag=digest)
                for rule in rule_nodes:
                    graph.add_link(rule, "PRODUCED", fid, version_tag=digest)
                for item in kb_nodes:
                    graph.add_link(item, "CONSTRAINED", fid, version_tag=digest)
        for symbol in extract_symbols(files, frozenset(c.name for c in build.validated.design_context.classes)):
            sid = graph.add_node("CODE_SYMBOL", f"{symbol['path']}#{symbol['class']}", symbol["class"],
                                 uml_class=symbol["uml_class"], methods=",".join(symbol["methods"]))
            digest = _sha(files[symbol["path"]])
            graph.add_link(node_id("CODE_FILE", symbol["path"]), "DEFINES", sid, version_tag=digest)
            if symbol["uml_class"] in uml_nodes:
                graph.add_link(uml_nodes[symbol["uml_class"]], "GENERATED_AS", sid, version_tag=digest)
        persistence = bool(build.spec and build.spec.persistence_required)
        clear_history = bool(build.spec and build.spec.clear_history)
        for op in operations_for(persistence, clear_history):
            oid = graph.add_node("API_OPERATION", op.operation_id, f"{op.method} {op.path}", method=op.method, path=op.path)
            for requirement_id, why in sorted(requirement_links(op.uml_bindings, op.uml_members, anchors_by_class, statements).items()):
                graph.add_link(node_id("REQUIREMENT", requirement_id), "EXPOSED_BY", oid, detail=why, version_tag=f"v{req_version[requirement_id]}")
        if persistence:
            for entity in DATABASE_ENTITIES:
                did = graph.add_node("DATABASE_ENTITY", entity.table, entity.table, uml_class=entity.uml_class)
                for requirement_id in sorted(anchors_by_class.get(entity.uml_class, ())):
                    graph.add_link(node_id("REQUIREMENT", requirement_id), "STORED_BY", did, version_tag=f"v{req_version[requirement_id]}")
        for seam in TEST_SEAMS:
            seam_module = seam_module_id(build.spec, seam)
            if seam_module not in build.modules or not seam_applies(seam, persistence, clear_history):
                continue
            sid = graph.add_node("TEST_SEAM", seam.seam_id, seam.seam_id, seam_type=seam.seam_type, reference=seam.reference)
            graph.add_link(sid, "TARGETS", node_id("MODULE", seam_module), version_tag=build.modules[seam_module].digest)
            for requirement_id, why in sorted(requirement_links(seam.uml_classes, seam.uml_members, anchors_by_class, statements).items()):
                graph.add_link(node_id("REQUIREMENT", requirement_id), "VERIFIED_THROUGH", sid, detail=why, version_tag=f"v{req_version[requirement_id]}")
        return graph

    # ------------------------------------------------------------------ persistence
    def _run_dir(self, workspace: str, run_id: str) -> Path:
        return self.root / workspace / run_id

    def find_run(self, run_id: str) -> tuple[Path, dict[str, Any]]:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", run_id):
            raise _error("INVALID_RUN_ID", "Run id has an invalid format.", status.HTTP_400_BAD_REQUEST)
        matches = list(self.root.glob(f"*/{run_id}/{PROJECT_DIR}/generation-manifest.json")) if self.root.exists() else []
        if len(matches) != 1:
            raise _error("HYBRID_RUN_NOT_FOUND", f"Hybrid run {run_id} was not found.", status.HTTP_404_NOT_FOUND)
        run_dir = matches[0].parent.parent
        return run_dir, json.loads(matches[0].read_text(encoding="utf-8"))

    def list_runs(self) -> list[dict[str, Any]]:
        runs = []
        if self.root.exists():
            for path in self.root.glob(f"*/*/{PROJECT_DIR}/generation-manifest.json"):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                runs.append({key: manifest.get(key) for key in (
                    "generation_run_id", "generated_at_utc", "status", "run_kind", "artifact_digest_sha256", "parent_run_id")}
                    | {"project_id": manifest["input"]["project_id"], "srs_version": manifest["input"]["srs_version"]})
        return sorted(runs, key=lambda r: r["generated_at_utc"], reverse=True)

    def project_dir(self, run_id: str) -> Path:
        """Absolute folder of a run's generated project (the run must exist)."""
        run_dir, _ = self.find_run(run_id)
        return (run_dir / PROJECT_DIR).resolve()

    def archive_zip(self, run_id: str) -> tuple[str, bytes]:
        """The generated project folder as a zip, after every file was re-hashed against the manifest.

        The zip holds exactly what is on disk under the run's project folder (the generated files plus the
        run manifest and trace graph), under one top-level folder, so it unpacks into a ready-to-read project.
        """
        run_dir, manifest = self.find_run(run_id)
        problems = self.verify_run_files(run_dir, manifest)
        if problems:
            raise _error("HYBRID_RUN_TAMPERED", f"The run's files do not match its manifest ({problems[0]}); nothing was exported.",
                         status.HTTP_409_CONFLICT)
        project = run_dir / PROJECT_DIR
        folder = f"gpa-project-{run_id[-8:]}"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(project.rglob("*")):
                if path.is_symlink():
                    raise _error("UNSAFE_ARTIFACT_PATH", f"{path.name} is a link and is never exported.", status.HTTP_409_CONFLICT)
                if path.is_file():
                    archive.write(path, f"{folder}/{path.relative_to(project).as_posix()}")
        return f"{folder}.zip", buffer.getvalue()

    def _read_project_files(self, run_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
        files = {}
        for record in manifest["files"]:
            path = run_dir / PROJECT_DIR / record["path"]
            files[record["path"]] = path.read_bytes().decode("utf-8")
        return files

    def verify_run_files(self, run_dir: Path, manifest: dict[str, Any]) -> list[str]:
        problems = []
        for record in manifest["files"]:
            path = run_dir / PROJECT_DIR / record["path"]
            if not path.is_file() or path.is_symlink():
                problems.append(f"{record['path']}: missing")
            elif _sha(path.read_bytes().decode("utf-8")) != record["sha256"]:
                problems.append(f"{record['path']}: sha256 mismatch")
        expected = canonical_sha256(sorted((r["path"], r["sha256"]) for r in manifest["files"]))
        if expected != manifest["artifact_digest_sha256"]:
            problems.append("artifact digest does not match file records")
        return problems

    def _write_run(self, workspace: str, run_id: str, files: dict[str, str], manifest: dict[str, Any],
                   graph_json: dict[str, Any] | None, evidence: dict[str, Any]) -> Path:
        final = self._run_dir(workspace, run_id)
        pending = final.with_name(final.name + ".pending")
        if final.exists() or pending.exists():
            raise _error("WORKSPACE_ALREADY_EXISTS", f"Run directory for {run_id} already exists.")
        project = pending / PROJECT_DIR
        try:
            for path, content in sorted(files.items()):
                target = (project / path).resolve()
                if not target.is_relative_to(project.resolve()):
                    raise _error("UNSAFE_ARTIFACT_PATH", f"{path} escapes the project directory.", status.HTTP_500_INTERNAL_SERVER_ERROR)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            if graph_json is not None:
                trace_dir = project / "traceability"
                trace_dir.mkdir(parents=True, exist_ok=True)
                (trace_dir / "trace-graph.json").write_text(json.dumps(graph_json, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
            (project / "generation-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
            evidence_dir = pending / EVIDENCE_DIR
            evidence_dir.mkdir(parents=True, exist_ok=True)
            for name, value in evidence.items():
                text = value if isinstance(value, str) else json.dumps(value, indent=2, sort_keys=True)
                (evidence_dir / name).write_text(text, encoding="utf-8", newline="\n")
            os.replace(pending, final)
        except Exception:
            shutil.rmtree(pending, ignore_errors=True)
            raise
        return final

    def _manifest(self, *, build: BuildResult, run_id: str, run_kind: str, status_value: str, files: dict[str, str],
                  owners: dict[str, str], artifact_digest: str, design: dict, architecture: dict,
                  graph_meta: dict[str, Any] | None, parent: dict[str, Any] | None, workspace: str) -> dict[str, Any]:
        package = build.validated.package
        modules = build.modules
        selected_rules = sorted({ref for d in build.decisions for ref in (r.ref for r in d.matched_rules)})
        kb_items = sorted({item for m in modules.values() for item in m.knowledge})
        ledger = build.ledger
        manifest = {
            "manifest_schema": MANIFEST_SCHEMA,
            "generator_version": HYBRID_GENERATOR_VERSION,
            "generation_run_id": run_id,
            "generation_mode": build.generation_mode,
            "run_kind": run_kind,
            "generated_at_utc": _now(),
            "status": status_value,
            "workspace": f"hybrid/{workspace}/{run_id}",
            "parent_run_id": parent.get("parent_run_id") if parent else None,
            "lineage": parent,
            "input": {
                "contract_version": package.contract_version,
                "input_classification": package.input_classification.value,
                "c1_evidence_class": package.c1.evidence_class.value,
                "c2_evidence_class": package.c2.evidence_class.value,
                "project_id": package.c1.project_id,
                "srs_version": package.c1.srs_version,
                "uml_version": package.c2.uml_version,
                "c1_approval_reference": package.c1.approval_reference,
                "c2_validation_reports": package.c2.validation_reports.model_dump(mode="json"),
                "requirements": {r.requirement_id: {"version": r.requirement_version, "type": r.requirement_type,
                                                    "statement_sha256": _sha(r.statement),
                                                    "constraints_sha256": canonical_sha256([c.model_dump(mode="json") for c in r.constraints])}
                                 for r in package.c1.requirements},
                "human_override": build.validated.report.override_applied,
                "package_sha256": canonical_sha256(package),
                "design_context_sha256": canonical_sha256(build.validated.design_context),
                "class_digests": {c.name: canonical_sha256(c) for c in build.validated.design_context.classes},
            },
            "policy": build.policy_record,
            "knowledge_base": {"kb_id": self.kb.kb_id, "kb_version": self.kb.kb_version, "kb_digest_sha256": self.kb.digest_sha256,
                               "items_used": [{"item_id": i, "version": self.kb.item_version(i)} for i in kb_items]},
            "rule_set": {"rule_set_id": self.rules.rule_set_id, "rule_set_version": self.rules.rule_set_version,
                         "rule_set_digest_sha256": self.rules.digest_sha256, "selected_rules": selected_rules},
            "rule_decisions": [d.as_json() for d in build.decisions],
            "stack": build.stack,
            "templates": {"template_set": TEMPLATE_SET_REF, "spec_fingerprint": build.spec.fingerprint() if build.spec else None},
            "rag": {"backend": self.rag_backend, "rule_corpus_sha256": self.rag_corpus, "retrievals": build.rag},
            "llm": {
                # Providers actually called in this run (OpenRouter: custom classes; TeamSocLo: LLM backend logic).
                "provider": ", ".join(sorted({e["provider"] for e in ledger if e.get("provider")})) or "NONE (no LLM call)",
                "configured_model": ", ".join(sorted({e["requested_model"] for e in ledger if e.get("requested_model")})) or "-",
                "prompt_version": PROMPT_VERSION,
                "backend_logic": build.backend_llm,
                "frontend": build.frontend_llm,
                "calls": sum(1 for e in ledger if not e.get("cache_hit") and e.get("validation_result") != "NOT_CALLED_BUDGET"),
                "cache_hits": sum(1 for e in ledger if e.get("cache_hit")),
                "prompt_tokens": sum(e.get("prompt_tokens") or 0 for e in ledger),
                "completion_tokens": sum(e.get("completion_tokens") or 0 for e in ledger),
                "latency_ms": round(sum(e.get("latency_ms") or 0 for e in ledger), 3),
                "ledger": ledger,
                "deterministic_modules": sorted(m.module_id for m in modules.values() if m.origin == "TEMPLATE"),
                "model_modules": sorted(m.module_id for m in modules.values() if m.origin in LLM_ORIGINS),
            },
            "modules": [
                {"module_id": m.module_id, "layer": m.layer, "artifact_type": m.artifact_type, "origin": m.origin,
                 "template_id": m.template_id, "status": m.status, "change": m.change,
                 "module_digest_sha256": m.digest, "files": sorted(m.files),
                 "requirement_ids": sorted(m.requirements),
                 "direct_requirement_ids": sorted(r for r, kind in m.requirements.items() if kind == DIRECT),
                 "rule_ids": sorted(m.rules), "knowledge_items": sorted(m.knowledge)}
                for m in sorted(modules.values(), key=lambda m: m.module_id)
            ],
            "files": [
                {"path": path, "sha256": _sha(content), "size_bytes": len(content.encode("utf-8")), "module_id": owners[path],
                 "origin": modules[owners[path]].origin, "requirement_ids": sorted(modules[owners[path]].requirements),
                 "srs_version": package.c1.srs_version, "uml_version": package.c2.uml_version,
                 "rule_ids": sorted(modules[owners[path]].rules),
                 "template_ref": (f"{TEMPLATE_SET_REF}#{modules[owners[path]].template_id}"
                                  if modules[owners[path]].origin == "TEMPLATE" else modules[owners[path]].template_id),
                 "created_in_generation_run_id": modules[owners[path]].created_in.get(path, run_id)}
                for path, content in sorted(files.items())
            ],
            "api_operations": [op.__dict__ for op in operations_for(build.spec.persistence_required, build.spec.clear_history)],
            "database_entities": [e.__dict__ for e in DATABASE_ENTITIES] if build.spec.persistence_required else [],
            "test_seams": [s.__dict__ | {"module_id": seam_module_id(build.spec, s), "module_digest_sha256": modules[seam_module_id(build.spec, s)].digest}
                           for s in TEST_SEAMS if seam_module_id(build.spec, s) in modules],
            "artifact_digest_sha256": artifact_digest,
            "verification": {"design_to_code": design["status"], "architecture": architecture["status"]},
            "traceability": graph_meta,
            "review_items": build.review_items,
            "claims": {
                "execution": "NOT_EXECUTED_BY_GENERATOR (Docker preview is a separate, explicit step)",
                "c4_independent_evidence": "NONE",
                "upstream_authenticity_verified": False,
                "correctness": "NOT_CLAIMED - structural verification and smoke checks are not independent testing",
                "pp1_scope": PP1_SCOPE,
            },
        }
        manifest["evidence_digest_sha256"] = canonical_sha256({k: v for k, v in manifest.items() if k != "generated_at_utc"})
        return manifest

    def _finalize(self, build: BuildResult, *, workspace: str, run_kind: str, parent: dict[str, Any] | None,
                  extra_events: list[tuple[str, dict]] | None = None, base_graph: LivingTraceGraph | None = None,
                  status_override: str | None = None) -> dict[str, Any]:
        run_id = f"{datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz')}-{uuid4().hex[:8]}"
        for module in build.modules.values():
            module.created_in = {p: (run_id if v == "__NEW_RUN__" else v) for p, v in module.created_in.items()}
        files, owners = self._all_files(build.modules)
        artifact_digest = _digest_of(files)
        design, architecture = self._verify(build, files, owners)
        graph = self._graph(build, run_id, artifact_digest, files)
        for kind, payload in extra_events or []:
            self._apply_event(graph, kind, payload)
        orphans = graph.orphans()
        latest = self.store.latest(graph.graph_id)
        if status_override:
            status_value = status_override
        elif design["status"] == "FAIL" or architecture["status"] == "FAIL":
            status_value = "REJECTED_BY_VERIFICATION"
        elif orphans:
            status_value = "REJECTED_ORPHAN_ARTIFACTS"
        elif any(item["outcome"] != "REVIEW_REQUIRED_BEFORE_WIRING" for item in build.review_items) or any(
            not m.status.startswith("ACCEPTED") for m in build.modules.values()
        ):
            status_value = "PARTIAL_REVIEW_REQUIRED"
        else:
            status_value = "ACCEPTED"
        accepted = not status_value.startswith("REJECTED")
        graph_meta = None
        change = None
        if accepted:
            change = evolve(latest, graph)
            graph_meta = {"graph_id": graph.graph_id, "graph_version": graph.version, "link_changes": change,
                          "coverage": graph.coverage()}
        manifest = self._manifest(build=build, run_id=run_id, run_kind=run_kind, status_value=status_value, files=files,
                                  owners=owners, artifact_digest=artifact_digest, design=design, architecture=architecture,
                                  graph_meta=graph_meta, parent=parent, workspace=workspace)
        evidence = {
            "input-package.json": build.validated.package.model_dump(mode="json"),
            "policy-acceptance.json": build.policy_record,
            "contract-report.json": build.validated.report.as_json(),
            "stack-selection.json": build.stack,
            "rule-decisions.json": [d.as_json() for d in build.decisions],
            "rag-retrievals.json": build.rag,
            "llm-ledger.json": build.ledger,
            "verification-design.json": {**design, "artifact_digest_sha256": artifact_digest},
            "verification-architecture.json": {**architecture, "artifact_digest_sha256": artifact_digest},
            "orphans.json": orphans,
        }
        self._write_run(workspace, run_id, files, manifest, graph.to_json() if accepted else None, evidence)
        if accepted:
            self.store.append(graph, expected_version=graph.version)
        return {"generation_run_id": run_id, "status": status_value, "workspace": manifest["workspace"],
                "manifest": manifest, "verification": {"design_to_code": design, "architecture": architecture},
                "orphans": orphans, "link_changes": change}

    # ------------------------------------------------------------------ public flows
    async def generate(self, request: HybridGenerationRequest) -> dict[str, Any]:
        build = await self._build(request.package, request.policy_acceptance, request.stack_criteria, request.allow_llm_for_unsupported,
                                  llm_backend_logic=request.llm_backend_logic, workspace=request.workspace_name,
                                  llm_frontend=request.llm_frontend)
        return self._finalize(build, workspace=request.workspace_name, run_kind="FULL_GENERATION", parent=None)

    def _latest_graph_for(self, project_id: str) -> LivingTraceGraph | None:
        return self.store.latest(graph_id_for(project_id))

    def _require_latest(self, manifest: dict[str, Any], code: str) -> LivingTraceGraph:
        graph = self._latest_graph_for(manifest["input"]["project_id"])
        if graph is None or graph.generation_run_id != manifest["generation_run_id"]:
            raise _error(code, f"Run {manifest['generation_run_id']} is not the current artifact for its project "
                               f"(current: {graph.generation_run_id if graph else 'none'}).")
        return graph

    def _base_modules(self, run_dir: Path, manifest: dict[str, Any]) -> dict[str, ModuleBuild]:
        files = self._read_project_files(run_dir, manifest)
        created = {record["path"]: record["created_in_generation_run_id"] for record in manifest["files"]}
        modules = {}
        for record in manifest["modules"]:
            modules[record["module_id"]] = ModuleBuild(
                record["module_id"], {p: files[p] for p in record["files"]}, record["layer"], record["artifact_type"],
                record["template_id"], record["origin"], set(record["rule_ids"]),
                {r: (DIRECT if r in record["direct_requirement_ids"] else HOSTING) for r in record["requirement_ids"]},
                set(record["knowledge_items"]), status=record["status"], created_in={p: created[p] for p in record["files"]},
                change="PRESERVED",
            )
        return modules

    def _load_base(self, run_id: str) -> tuple[Path, dict[str, Any]]:
        run_dir, manifest = self.find_run(run_id)
        problems = self.verify_run_files(run_dir, manifest)
        if problems:
            raise _error("BASE_RUN_TAMPERED", f"Run {run_id} no longer matches its manifest: {problems[:5]}")
        return run_dir, manifest

    def _preservation(self, base: dict[str, ModuleBuild], merged: dict[str, ModuleBuild], impact: set[str]) -> list[dict[str, Any]]:
        rows = []
        for module_id in sorted(merged):
            before = base.get(module_id)
            after = merged[module_id]
            for path in sorted(set(after.files) | set(before.files if before else {})):
                old = _sha(before.files[path]) if before and path in before.files else None
                new = _sha(after.files[path]) if path in after.files else None
                if module_id not in impact:
                    state = "PRESERVED_UNTOUCHED" if old == new else "UNEXPECTED_CHANGE"
                else:
                    state = "REGENERATED_IDENTICAL" if old == new else "REGENERATED_CHANGED"
                rows.append({"module_id": module_id, "path": path, "before_sha256": old, "after_sha256": new, "state": state})
        return rows

    def _merge(self, base: dict[str, ModuleBuild], fresh: dict[str, ModuleBuild], impact: set[str], run_marker: str) -> dict[str, ModuleBuild]:
        merged: dict[str, ModuleBuild] = {}
        for module_id, module in base.items():
            if module_id in impact:
                regenerated = fresh[module_id]
                regenerated.created_in = {
                    path: (module.created_in.get(path) if module.files.get(path) == content else run_marker)
                    for path, content in regenerated.files.items()
                }
                regenerated.change = "REGENERATED"
                merged[module_id] = regenerated
            else:
                merged[module_id] = module
        return merged

    async def requirement_change(self, request: RequirementChangeRequest) -> dict[str, Any]:
        run_dir, manifest = self._load_base(request.base_generation_run_id)
        base_graph = self._require_latest(manifest, "STALE_BASE_RUN")
        package = request.package
        if package.c1.project_id != manifest["input"]["project_id"]:
            raise _error("PROJECT_MISMATCH", "The change package belongs to a different project.")
        old_reqs = manifest["input"]["requirements"]
        new_reqs = {r.requirement_id: r for r in package.c1.requirements}
        if set(old_reqs) != set(new_reqs):
            raise _error("FULL_REGENERATION_REQUIRED",
                         "Requirements were added or removed; scoped regeneration only handles changes to existing requirements.")
        changed: set[str] = set()
        for requirement_id, requirement in new_reqs.items():
            old = old_reqs[requirement_id]
            content_changed = (old["statement_sha256"] != _sha(requirement.statement) or old["constraints_sha256"]
                               != canonical_sha256([c.model_dump(mode="json") for c in requirement.constraints]))
            if content_changed and requirement.requirement_version <= old["version"]:
                raise _error("REQUIREMENT_CHANGED_WITHOUT_VERSION_BUMP",
                             f"{requirement_id} changed but its version was not increased; C1 must approve a new version.")
            if requirement.requirement_version != old["version"]:
                changed.add(requirement_id)
        build = await self._build(package, request.policy_acceptance, None, False,
                                  frontend_shape_only="LLM_FRONTEND" in manifest.get("generation_mode", ""))
        new_classes = {c.name: canonical_sha256(c) for c in build.validated.design_context.classes}
        changed_classes = {name for name, digest in new_classes.items() if manifest["input"]["class_digests"].get(name) != digest}
        if set(new_classes) != set(manifest["input"]["class_digests"]):
            raise _error("FULL_REGENERATION_REQUIRED", "UML classes were added or removed; scoped regeneration is not applicable.")
        for anchor in package.c2.requirement_uml_anchors:
            if anchor.uml_element in changed_classes:
                changed.add(anchor.requirement_id)
        if not changed:
            raise _error("NO_APPROVED_CHANGE", "No requirement version or UML class changed relative to the base run.")
        if package.c1.srs_version == manifest["input"]["srs_version"] and package.c2.uml_version == manifest["input"]["uml_version"]:
            raise _error("SRS_VERSION_NOT_BUMPED", "Changed requirements must arrive under a new approved SRS or UML version.")
        impact = base_graph.modules_for_requirements(changed, direct_only=True) | set(request.approved_dependency_modules)
        base_modules = self._base_modules(run_dir, manifest)
        if set(build.modules) != set(base_modules):
            raise _error("FULL_REGENERATION_REQUIRED", "The change alters the module set; scoped regeneration is not applicable.")
        llm_run = "LLM_BACKEND_LOGIC" in manifest.get("generation_mode", "")
        # Model-written modules (and, in LLM mode, the smoke test that encodes their benchmark) are pinned: they are
        # never silently replaced by template output, and a change that reaches them needs a new reviewed LLM call.
        pinned = {m for m, b in base_modules.items() if b.origin in LLM_ORIGINS or (llm_run and m == "be.smoke")}
        if impact & pinned:
            raise _error("LLM_MODULE_IMPACTED_REQUIRES_REVIEW",
                         f"The change reaches model-written modules {sorted(impact & pinned)}; scoped regeneration would need a new "
                         "LLM call and human review, so it is not done automatically.", status.HTTP_422_UNPROCESSABLE_ENTITY)
        build.generation_mode = manifest.get("generation_mode", "TEMPLATE")
        build.backend_llm = (manifest.get("llm") or {}).get("backend_logic")
        build.frontend_llm = (manifest.get("llm") or {}).get("frontend")
        drift = sorted(m for m in base_modules if m not in impact and m not in pinned
                       and build.modules[m].files != base_modules[m].files)
        if drift:
            raise _error("IMPACT_SET_INCOMPLETE",
                         f"Modules outside the traced impact set would change: {drift}. Approve them as dependency modules or regenerate fully.")
        marker = "__NEW_RUN__"
        merged = self._merge(base_modules, build.modules, impact, marker)
        preservation = self._preservation(base_modules, merged, impact)
        build.modules = merged
        parent = {"parent_run_id": manifest["generation_run_id"], "change_type": "APPROVED_REQUIREMENT_CHANGE",
                  "changed_requirement_ids": sorted(changed), "changed_uml_classes": sorted(changed_classes),
                  "impact_set": sorted(impact), "approved_dependency_modules": sorted(request.approved_dependency_modules),
                  "preserved_modules": sorted(set(merged) - impact), "preservation": preservation,
                  "base_artifact_digest_sha256": manifest["artifact_digest_sha256"]}
        result = self._finalize_regeneration(build, manifest, parent, impact, "PATCH_EVENT_REQUIREMENT_CHANGE")
        result["c4_handoff"] = self._handoff(result, impact, sorted(changed))
        return result

    def _finalize_regeneration(self, build: BuildResult, base_manifest: dict[str, Any], parent: dict[str, Any],
                               impact: set[str], event_kind: str, extra_events: list | None = None,
                               status_override: str | None = None) -> dict[str, Any]:
        workspace = base_manifest["workspace"].split("/")[1]
        events = [(event_kind, {"modules": sorted(impact), "parent_run_id": base_manifest["generation_run_id"]})] + (extra_events or [])
        return self._finalize(build, workspace=workspace, run_kind="SCOPED_REGENERATION", parent=parent,
                              extra_events=events, status_override=status_override)

    def _append_event_version(self, graph: LivingTraceGraph) -> LivingTraceGraph:
        """Append an event-only graph version (no artifact change)."""
        evolved = LivingTraceGraph.from_json(graph.to_json())
        evolved.version, evolved.parent_version = graph.version + 1, graph.version
        return evolved

    def _commit_event_version(self, evolved: LivingTraceGraph) -> None:
        for link in evolved.links:
            if link["created_in_version"] is None:
                link["created_in_version"] = evolved.version
        self.store.append(evolved, expected_version=evolved.version)

    def _apply_event(self, graph: LivingTraceGraph, kind: str, payload: dict[str, Any]) -> None:
        stamp = _now()
        if kind.startswith("PATCH_EVENT"):
            pid = graph.add_node("PATCH_EVENT", f"{graph.generation_run_id}:{kind}", kind, recorded_at_utc=stamp,
                                 parent_run_id=payload.get("parent_run_id"))
            for module_id in payload["modules"]:
                if node_id("MODULE", module_id) in graph.nodes:
                    graph.add_link(pid, "REGENERATED", node_id("MODULE", module_id))
        elif kind == "DEFECT_REPORT":
            did = graph.add_node("DEFECT_REPORT", payload["report_id"], payload["report_id"], evidence_class=payload["evidence_class"],
                                 category=payload["category"], severity=payload["severity"], status=payload["status"])
            tid = graph.add_node("C4_TEST", payload["failing_test_id"], payload["failing_test_id"], evidence_class=payload["evidence_class"])
            if node_id("TEST_SEAM", payload["test_seam_id"]) in graph.nodes:
                graph.add_link(tid, "EXERCISES", node_id("TEST_SEAM", payload["test_seam_id"]))
            for module_id in payload["modules"]:
                if node_id("MODULE", module_id) in graph.nodes:
                    graph.add_link(did, "IMPACTS", node_id("MODULE", module_id))
        graph.events.append({"kind": kind, "recorded_at_utc": stamp, **{k: v for k, v in payload.items() if k != "modules"},
                             "modules": payload.get("modules", [])})

    def _handoff(self, result: dict[str, Any], impact: set[str], requirement_ids: list[str]) -> dict[str, Any]:
        manifest = result["manifest"]
        return {
            "classification": "C3_TO_C4_REVERIFICATION_REQUEST (no C4 integration exists; C4 action is pending)",
            "generation_run_id": result["generation_run_id"],
            "artifact_digest_sha256": manifest["artifact_digest_sha256"],
            "module_digests": {m["module_id"]: m["module_digest_sha256"] for m in manifest["modules"]},
            "changed_modules": sorted(impact),
            "requirement_ids_to_reverify": requirement_ids,
            "required_c4_actions": ["RERUN_AFFECTED_TESTS", "REGRESSION_ON_PRESERVED_MODULES",
                                    "ASSESS_SEMANTIC_PRESERVATION", "ISSUE_EXACT_ARTIFACT_READINESS_SIGNAL"],
            "retest_status": "PENDING",
            "independent_c4_evidence": "NONE",
        }

    async def c4_defect(self, submission: C4DefectSubmission) -> dict[str, Any]:
        report = submission.report
        run_dir, manifest = self._load_base(report.generation_run_id)
        if report.project_id != manifest["input"]["project_id"]:
            raise _error("PROJECT_MISMATCH", "Defect report project does not match the run.")
        if report.artifact_digest_sha256 != manifest["artifact_digest_sha256"]:
            raise _error("STALE_DEFECT_REPORT", "The report cites an artifact digest that is not this run's digest.")
        graph = self._require_latest(manifest, "STALE_DEFECT_REPORT")
        modules = {m["module_id"]: m for m in manifest["modules"]}
        if report.module_id not in modules:
            raise _error("UNKNOWN_MODULE", f"Module {report.module_id} is not part of run {report.generation_run_id}.")
        if report.module_digest_sha256 != modules[report.module_id]["module_digest_sha256"]:
            raise _error("STALE_MODULE_DIGEST", f"Module {report.module_id} digest differs from the cited digest.")
        seam_ids = {s["seam_id"] for s in manifest["test_seams"]}
        if report.test_seam_id not in seam_ids:
            raise _error("UNKNOWN_TEST_SEAM", f"Test seam {report.test_seam_id} is not published for this run.")
        unknown_reqs = sorted(set(report.traceability_refs) - set(manifest["input"]["requirements"]))
        if unknown_reqs:
            raise _error("UNKNOWN_TRACEABILITY_REFERENCE", f"Unknown requirement references {unknown_reqs}.")
        allowed = {report.module_id} | graph.modules_for_seam(report.test_seam_id) | set(submission.approved_dependency_modules)
        outside = sorted(set(report.proposed_repair_scope) - allowed)
        if outside:
            raise _error("PATCH_OUTSIDE_IMPACT_SET",
                         f"Proposed repair scope {outside} is outside the traced impact set {sorted(allowed)} and has no approved dependency reason.")
        impact = set(report.proposed_repair_scope)
        base_modules = self._base_modules(run_dir, manifest)
        package = HybridInputPackage.model_validate(json.loads((run_dir / EVIDENCE_DIR / "input-package.json").read_text(encoding="utf-8")))
        acceptance_raw = json.loads((run_dir / EVIDENCE_DIR / "policy-acceptance.json").read_text(encoding="utf-8"))
        acceptance = PolicyAcceptance.model_validate(acceptance_raw["acceptance"]) if acceptance_raw and acceptance_raw.get("acceptance") else None
        build = await self._build(package, acceptance, None, False,
                                  frontend_shape_only="LLM_FRONTEND" in manifest.get("generation_mode", ""))
        build.generation_mode = manifest.get("generation_mode", "TEMPLATE")
        build.backend_llm = (manifest.get("llm") or {}).get("backend_logic")
        build.frontend_llm = (manifest.get("llm") or {}).get("frontend")
        defect_event = {"report_id": report.report_id, "evidence_class": report.evidence_class.value,
                        "category": report.category.value, "severity": report.severity.value,
                        "failing_test_id": report.failing_test_id, "test_seam_id": report.test_seam_id,
                        "modules": sorted(impact), "status": "OPEN"}
        llm_modules = sorted(m for m in impact if base_modules[m].origin in LLM_ORIGINS)
        if llm_modules:
            raise _error("MODEL_MODULE_REPAIR_REQUIRES_REVIEW",
                         f"Modules {llm_modules} are model-generated; bounded repair must be requested through human review.",
                         status.HTTP_422_UNPROCESSABLE_ENTITY)
        unchanged = [m for m in impact if build.modules[m].files == base_modules[m].files]
        if len(unchanged) == len(impact):
            defect_event["status"] = "REVIEW_REQUIRED_TEMPLATE_DEFECT"
            evolved = self._append_event_version(graph)
            self._apply_event(evolved, "DEFECT_REPORT", defect_event)
            self._commit_event_version(evolved)
            return {
                "status": "REVIEW_REQUIRED",
                "reason": "TEMPLATE_DEFECT_REQUIRES_RULE_OR_KB_CHANGE: regenerating the affected modules from the current rules, "
                          "templates and KB reproduces identical bytes, so C3 cannot fix this defect by regeneration. "
                          "A maintainer must change the rule, template or KB fact (or C1/C2 must change the requirement/design).",
                "impact_set": sorted(impact), "graph_version": evolved.version,
            }
        merged = self._merge(base_modules, build.modules, impact, "__NEW_RUN__")
        preservation = self._preservation(base_modules, merged, impact)
        build.modules = merged
        defect_event["status"] = "REGENERATED_PENDING_C4_REVERIFICATION"
        parent = {"parent_run_id": manifest["generation_run_id"], "change_type": "C4_DEFECT_FEEDBACK",
                  "defect_report_id": report.report_id, "defect_evidence_class": report.evidence_class.value,
                  "impact_set": sorted(impact), "preserved_modules": sorted(set(merged) - impact),
                  "preservation": preservation, "base_artifact_digest_sha256": manifest["artifact_digest_sha256"]}
        result = self._finalize_regeneration(build, manifest, parent, impact, "PATCH_EVENT_DEFECT_REPAIR",
                                             extra_events=[("DEFECT_REPORT", defect_event)])
        result["c4_handoff"] = self._handoff(result, impact, sorted(report.traceability_refs))
        return result

    def inject_defect_for_demo(self, run_id: str) -> dict[str, Any]:
        """SIMULATED: derive a run whose GPA service truncates instead of rounding half-up."""
        run_dir, manifest = self._load_base(run_id)
        graph = self._require_latest(manifest, "STALE_BASE_RUN")
        base_modules = self._base_modules(run_dir, manifest)
        service = base_modules["be.service"]
        path = "backend/src/services/gpaCalculationService.js"
        if _DEFECT_INJECTION[0] not in service.files[path]:
            raise _error("DEFECT_INJECTION_NOT_APPLICABLE", "The service does not contain the expected rounding statement.")
        package = HybridInputPackage.model_validate(json.loads((run_dir / EVIDENCE_DIR / "input-package.json").read_text(encoding="utf-8")))
        acceptance_raw = json.loads((run_dir / EVIDENCE_DIR / "policy-acceptance.json").read_text(encoding="utf-8"))
        validated = HybridContractValidator().validate(package)
        spec = build_gpa_spec(package, validated.design_context, self.kb)
        mutated = ModuleBuild(service.module_id, {path: service.files[path].replace(*_DEFECT_INJECTION)}, service.layer,
                              service.artifact_type, service.template_id, "SIMULATED_DEFECT_INJECTION", set(service.rules),
                              dict(service.requirements), set(service.knowledge), status="SIMULATED_DEFECT", created_in={path: "__NEW_RUN__"},
                              change="SIMULATED_DEFECT_INJECTION")
        modules = dict(base_modules)
        modules["be.service"] = mutated
        build = BuildResult(validated, spec, json.loads((run_dir / EVIDENCE_DIR / "stack-selection.json").read_text(encoding="utf-8")),
                            [], modules, [], [], [{"target_id": "be.service", "outcome": "SIMULATED_DEFECT_INJECTION",
                                                   "reasons": ["Demo-only mutation; not generated output."]}], acceptance_raw)
        parent = {"parent_run_id": run_id, "change_type": "SIMULATED_DEFECT_INJECTION", "impact_set": ["be.service"],
                  "preserved_modules": sorted(set(modules) - {"be.service"}),
                  "base_artifact_digest_sha256": manifest["artifact_digest_sha256"]}
        del graph
        return self._finalize_regeneration(build, manifest, parent, {"be.service"}, "PATCH_EVENT_SIMULATED_DEFECT_INJECTION",
                                           status_override="DEFECT_INJECTED_FOR_DEMO")

    # ------------------------------------------------------------------ simulated C4 fixtures
    def simulated_defect(self, run_id: str) -> dict[str, Any]:
        _, manifest = self.find_run(run_id)
        module = next(m for m in manifest["modules"] if m["module_id"] == "be.service")
        report = C4DefectFeedback(
            report_id=f"SIM-C4-DEFECT-{run_id[-8:]}", report_version="2.0", evidence_class=EvidenceClass.SIMULATED_FIXTURE,
            project_id=manifest["input"]["project_id"], generation_run_id=run_id,
            artifact_digest_sha256=manifest["artifact_digest_sha256"], module_id="be.service",
            module_digest_sha256=module["module_digest_sha256"], failing_test_id="SIM-C4-TEST-GPA-ROUNDING-001",
            test_seam_id="SEAM-GPA-SERVICE", category=C4DefectCategory.BUSINESS_LOGIC, severity=C4Severity.HIGH,
            observed_evidence="SIMULATED: calculate() returned 3.41 for the benchmark modules (A/4, B+/3, C/2, A-/3).",
            inferred_cause="SIMULATED: result appears truncated instead of rounded HALF_UP per KB-GPA-ROUNDING.",
            proposed_repair_scope=("be.service",), traceability_refs=("REQ-GPA-102",), reported_at_utc=_now(),
        )
        return {"classification": "SIMULATED_C4_FIXTURE - not independent Component 4 evidence",
                "submission": {"report": report.model_dump(mode="json"), "approved_dependency_modules": []}}

    def simulated_readiness(self, run_id: str) -> dict[str, Any]:
        _, manifest = self.find_run(run_id)
        signal = C4ReadinessSignal(
            signal_id=f"SIM-C4-READY-{run_id[-8:]}", signal_version="2.0", evidence_class=EvidenceClass.SIMULATED_FIXTURE,
            project_id=manifest["input"]["project_id"], generation_run_id=run_id,
            artifact_digest_sha256=manifest["artifact_digest_sha256"],
            modules=tuple(ModuleDigest(module_id=m["module_id"], module_digest_sha256=m["module_digest_sha256"]) for m in manifest["modules"]),
            status=ReadinessStatus.READY, issued_at_utc=_now(), revoked=False,
            semantic_preservation=SemanticPreservation.PRESERVED, convergence=ConvergenceState.CONVERGED,
            evidence_refs=("SIMULATED-C4-READINESS-EVIDENCE",),
        )
        return {"classification": "SIMULATED_C4_FIXTURE - not independent Component 4 readiness",
                "readiness_signal": signal.model_dump(mode="json")}

    # ------------------------------------------------------------------ deployment gate
    def deployment_gate(self, request: DeploymentGateRequest) -> dict[str, Any]:
        run_dir, manifest = self.find_run(request.generation_run_id)
        reasons: list[str] = []
        problems = self.verify_run_files(run_dir, manifest)
        if problems:
            reasons.append(f"ARTIFACT_TAMPERED: {problems[:3]}")
        if manifest["status"] not in {"ACCEPTED"}:
            reasons.append(f"RUN_STATUS_{manifest['status']}: only fully ACCEPTED runs can be deployed.")
        if manifest["input"]["input_classification"] != InputClassification.VALIDATED_CONTRACT_INPUT.value:
            reasons.append("PROVISIONAL_DEMO_INPUT: provisional input can never be deployed.")
        graph = self._latest_graph_for(manifest["input"]["project_id"])
        if graph is None or graph.generation_run_id != manifest["generation_run_id"]:
            reasons.append("SUPERSEDED_ARTIFACT: a newer artifact exists for this project.")
        signal = request.readiness_signal
        if signal is None:
            reasons.append("NO_C4_READINESS_SIGNAL: deployment requires an exact-artifact readiness signal from Component 4.")
        else:
            modules = {m["module_id"]: m["module_digest_sha256"] for m in manifest["modules"]}
            checks = [
                (signal.project_id == manifest["input"]["project_id"], "PROJECT_MISMATCH"),
                (signal.generation_run_id == manifest["generation_run_id"], "RUN_MISMATCH: signal is for a different run."),
                (signal.artifact_digest_sha256 == manifest["artifact_digest_sha256"], "ARTIFACT_DIGEST_MISMATCH: signal does not cite this exact artifact."),
                ({m.module_id: m.module_digest_sha256 for m in signal.modules} == modules, "MODULE_DIGEST_MISMATCH: module set or digests differ."),
                (signal.status is ReadinessStatus.READY, f"READINESS_{signal.status.value}"),
                (not signal.revoked, f"READINESS_REVOKED: {signal.revocation_reason or 'no reason given'}"),
                (signal.semantic_preservation is SemanticPreservation.PRESERVED, f"SEMANTIC_PRESERVATION_{signal.semantic_preservation.value}"),
                (signal.convergence is ConvergenceState.CONVERGED, f"CONVERGENCE_{signal.convergence.value}"),
                (signal.issued_at_utc >= manifest["generated_at_utc"], "READINESS_PREDATES_ARTIFACT"),
            ]
            reasons.extend(message for ok, message in checks if not ok)
        decision = "ALLOWED" if not reasons else "BLOCKED"
        record = {
            "gate_rule": "R-DEPLOY-GATE-001@1.0.0",
            "decision": decision,
            "generation_run_id": manifest["generation_run_id"],
            "artifact_digest_sha256": manifest["artifact_digest_sha256"],
            "reasons": reasons,
            "readiness_signal_id": signal.signal_id if signal else None,
            "readiness_evidence_class": signal.evidence_class.value if signal else None,
            "authorization_scope": (
                "SIMULATED readiness fixture: authorizes the demo gate only, not a real deployment"
                if signal and signal.evidence_class is EvidenceClass.SIMULATED_FIXTURE else
                "Component 4 readiness signal (authenticity not cryptographically verified by C3)"
            ) if decision == "ALLOWED" else None,
            "deployment_action": "NONE_PERFORMED - C3 records the gate decision; no external deployment target is configured",
            "pp1_scope": PP1_SCOPE,
            "decided_at_utc": _now(),
        }
        with (run_dir / EVIDENCE_DIR / "gate-decisions.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        if decision == "ALLOWED" and graph is not None:
            evolved = self._append_event_version(graph)
            artifact = node_id("ARTIFACT", manifest["generation_run_id"])
            rid = evolved.add_node("READINESS_SIGNAL", signal.signal_id, signal.signal_id, evidence_class=signal.evidence_class.value,
                                   status=signal.status.value)
            did = evolved.add_node("DEPLOYMENT_EVENT", f"{signal.signal_id}:gate", "Gate authorization",
                                   action="GATE_AUTHORIZATION_ONLY", evidence_class=signal.evidence_class.value)
            evolved.add_link(rid, "AUTHORIZES", artifact)
            evolved.add_link(did, "DEPLOYED", artifact, detail="gate authorization only; no deployment performed")
            evolved.events.append({"kind": "DEPLOYMENT_GATE_ALLOWED", "recorded_at_utc": record["decided_at_utc"],
                                   "signal_id": signal.signal_id, "evidence_class": signal.evidence_class.value})
            self._commit_event_version(evolved)
            record["graph_version"] = evolved.version
        return record

    # ------------------------------------------------------------------ reports
    def trace(self, project_id: str, version: int | None = None) -> dict[str, Any]:
        gid = graph_id_for(project_id)
        graph = self.store.get(gid, version) if version else self.store.latest(gid)
        if graph is None:
            raise _error("TRACE_GRAPH_NOT_FOUND", f"No living trace graph exists for {project_id}.", status.HTTP_404_NOT_FOUND)
        return {"graph": graph.to_json(), "coverage": graph.coverage(), "versions": self.store.versions(gid)}

    def run_report(self, run_id: str) -> dict[str, Any]:
        run_dir, manifest = self.find_run(run_id)
        evidence = {}
        for path in sorted((run_dir / EVIDENCE_DIR).glob("*.json")):
            if path.name in {"verification-design.json", "verification-architecture.json", "orphans.json", "contract-report.json"}:
                evidence[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        gates = run_dir / EVIDENCE_DIR / "gate-decisions.jsonl"
        evidence["gate_decisions"] = [json.loads(line) for line in gates.read_text(encoding="utf-8").splitlines()] if gates.exists() else []
        previews = run_dir / EVIDENCE_DIR / "preview-events.jsonl"
        evidence["preview_events"] = [json.loads(line) for line in previews.read_text(encoding="utf-8").splitlines()] if previews.exists() else []
        evidence["integrity_problems"] = self.verify_run_files(run_dir, manifest)
        return {"manifest": manifest, "evidence": evidence, "run_directory": str(run_dir.relative_to(self.root.parent))}

    def audit_markdown(self, run_id: str) -> str:
        report = self.run_report(run_id)
        m, e = report["manifest"], report["evidence"]
        llm = m["llm"]
        coverage = (m.get("traceability") or {}).get("coverage") or {}
        lines = [
            f"# C3 hybrid generation audit - {m['generation_run_id']}",
            "",
            f"* Status: **{m['status']}** ({m['run_kind']}); parent run: {m.get('parent_run_id') or '-'}",
            f"* Input: {m['input']['input_classification']} (C1 {m['input']['c1_evidence_class']}, C2 {m['input']['c2_evidence_class']}); "
            f"project {m['input']['project_id']}, SRS {m['input']['srs_version']}, UML {m['input']['uml_version']}",
            f"* Policy: {m['policy']['policy']['policy_id']} v{m['policy']['policy']['policy_version']} - {m['policy']['policy']['authority_status']}",
            f"* Knowledge Base {m['knowledge_base']['kb_version']} ({m['knowledge_base']['kb_digest_sha256'][:12]}); "
            f"rule set {m['rule_set']['rule_set_version']} ({len(m['rule_set']['selected_rules'])} rules selected)",
            f"* Stack: {m['stack']['stack_id']} ({m['stack']['criteria_source']}), generator {m['stack']['generator_status']}",
            f"* Artifact digest: `{m['artifact_digest_sha256']}` over {len(m['files'])} files in {len(m['modules'])} modules",
            f"* Model calls: {llm['calls']} calls, {llm['cache_hits']} cache hits, {llm['prompt_tokens']} prompt / "
            f"{llm['completion_tokens']} completion tokens",
            f"* RAG: {sum(len(r['hits']) for r in m['rag']['retrievals'])} chunks across {len(m['rag']['retrievals'])} module queries "
            f"(guidance only)",
            f"* Verification: design-to-code {m['verification']['design_to_code']}, architecture {m['verification']['architecture']}",
            f"* Traceability: {coverage.get('traced_count', 0)}/{coverage.get('total', 0)} requirements traced to code and seam; "
            f"orphan artifacts {len(e.get('orphans', []))}",
            f"* Gate decisions: {[g['decision'] for g in e['gate_decisions']] or 'none recorded'}",
            f"* Integrity problems: {e['integrity_problems'] or 'none'}",
            "",
            "Claims: no independent C4 evidence; smoke checks and static verification are not correctness proofs.",
        ]
        return "\n".join(lines) + "\n"
