"""Component 3 automated tests for the rule-governed hybrid pipeline (GPA domain pack).

These are C3's own tests. They never execute generated JavaScript on the host;
generated-app smoke checks run inside the Docker build, and nothing here is
Component 4 evidence.
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest
from pydantic import ValidationError

from intelise_c3.contracts.hybrid import (
    C4DefectSubmission,
    DeploymentGateRequest,
    HybridGenerationRequest,
    HybridInputPackage,
    RequirementChangeRequest,
)
from intelise_c3.core.config import COMPONENT_ROOT, Settings
from intelise_c3.core.errors import ApplicationError
from intelise_c3.domain.llm import (
    LLMGenerationParameters,
    LLMInferenceMetadata,
    LLMInferenceResponse,
    OpenRouterResponseMetadata,
)
from intelise_c3.core.errors import ErrorDetail
from intelise_c3.hybrid.gpa_spec import build_gpa_spec
from intelise_c3.hybrid.gpa_templates import MODULES, render_modules
from intelise_c3.hybrid.input_contracts import HybridContractValidator, classify_legacy_package
from intelise_c3.hybrid.knowledge_base import KB_ROOT, KnowledgeBaseError, load_knowledge_base
from intelise_c3.hybrid.living_trace import LivingTraceGraph
from intelise_c3.hybrid.llm_trial import CASES, LlmModuleTrial
from intelise_c3.hybrid.llm_gateway import BoundedModuleContext, InterfaceMethod, OpenRouterModuleGateway, cache_key
from intelise_c3.hybrid.pipeline import HybridPipeline
from intelise_c3.hybrid.preview import RESERVED_PORTS, HybridPreviewService
from intelise_c3.hybrid.rule_engine import (
    RULES_ROOT,
    GenerationTarget,
    RuleEngine,
    RuleOutcome,
    RuleSetError,
    load_rule_set,
    review_state,
)
from intelise_c3.hybrid.verification import verify_architecture, verify_design_to_code
from intelise_c3.rag.best_practices import (
    FilterBestPracticeStore,
    RetrievalQuery,
    RuleCardError,
    _validate,
    load_rule_cards,
)
from intelise_c3.contracts.provisional_input import ProvisionalInputPackage

FIXTURES = Path(__file__).parent / "fixtures" / "hybrid"
SIMULATED = Path(__file__).parent / "fixtures" / "simulated"


def _package(name: str = "gpa_input_package.json") -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _acceptance(pipeline: HybridPipeline, **overrides) -> dict:
    template = pipeline.policy_acceptance_template()
    return {"policy_id": template["policy_id"], "policy_version": template["policy_version"],
            "policy_digest_sha256": template["policy_digest_sha256"], "accepted_by": "test-researcher",
            "acceptance_reference": "TEST-ACCEPT-001", "acknowledges_sample_status": True, **overrides}


@pytest.fixture
def pipeline(tmp_path) -> HybridPipeline:
    workdir = COMPONENT_ROOT / "tmp" / f"pytest-hybrid-{uuid4().hex[:8]}"
    settings = Settings(generated_workspace_root=workdir / "ws", traceability_store_path=workdir / "trace.sqlite3",
                        rag_enabled=True, rag_backend="filter", hybrid_llm_cache_dir=workdir / "cache")
    yield HybridPipeline(settings)
    shutil.rmtree(workdir, ignore_errors=True)


def _generate(pipeline: HybridPipeline, package: dict | None = None, **extra) -> dict:
    request = HybridGenerationRequest.model_validate(
        {"package": package or _package(), "policy_acceptance": _acceptance(pipeline), **extra})
    return asyncio.run(pipeline.generate(request))


# --------------------------------------------------------------------------- contracts


def _validate_pkg(payload: dict):
    return HybridContractValidator().validate(HybridInputPackage.model_validate(payload))


def _codes(callable_) -> set[str]:
    with pytest.raises(ApplicationError) as caught:
        callable_()
    return {error.code for error in caught.value.errors}


def test_valid_package_is_accepted_and_labelled_simulated():
    validated = _validate_pkg(_package())
    report = validated.report.as_json()
    assert report["status"] == "ACCEPTED"
    assert report["simulated"] is True
    assert {c.name for c in validated.design_context.classes} >= {"ModuleResult", "GpaCalculationService"}


@pytest.mark.parametrize("mutate, code", [
    (lambda p: p["c1"].update(approval_status="PENDING_CLIENT_APPROVAL"), "C1_NOT_CLIENT_APPROVED"),
    (lambda p: p["c1"]["requirements"][0].update(approval_status="REJECTED"), "C1_REQUIREMENT_NOT_APPROVED"),
    (lambda p: p["c2"].update(srs_version="SRS-GPA-1.9"), "SRS_VERSION_MISMATCH"),
    (lambda p: p["c2"].update(project_id="OTHER"), "PROJECT_ID_MISMATCH"),
    (lambda p: p["c2"].update(release_status="FAILED"), "C2_RELEASE_NOT_VALIDATED"),
    (lambda p: p["c2"].update(release_status="DRAFT"), "C2_RELEASE_NOT_VALIDATED"),
    (lambda p: p["c2"].update(release_status="NEEDS_HUMAN_REVIEW"), "C2_NEEDS_HUMAN_REVIEW"),
    (lambda p: p["c2"].update(requirement_uml_anchors=[a for a in p["c2"]["requirement_uml_anchors"] if a["requirement_id"] != "REQ-GPA-104"]),
     "FR_WITHOUT_UML_ANCHOR"),
    (lambda p: p["c2"]["requirement_uml_anchors"][0].update(uml_element="Ghost"), "UNKNOWN_UML_ELEMENT"),
    (lambda p: p["c1"]["requirements"][2]["constraints"][0].update(target="ModuleResult.ghost"), "CONSTRAINT_TARGET_NOT_IN_DESIGN"),
])
def test_contract_rejections(mutate, code):
    payload = _package()
    mutate(payload)
    assert code in _codes(lambda: _validate_pkg(payload))


def test_missing_stable_id_is_a_schema_error():
    payload = _package()
    payload["c1"]["requirements"][0]["requirement_id"] = ""
    with pytest.raises(ValidationError):
        HybridInputPackage.model_validate(payload)


def _override(payload: dict, **changes) -> dict:
    return {"override_id": "OVR-1", "scope": "C2_NEEDS_HUMAN_REVIEW_RELEASE", "reason": "Reviewed by the research supervisor.",
            "approved_by": "supervisor", "approval_reference": "SIM-OVR-REF", "bound_project_id": payload["c1"]["project_id"],
            "bound_srs_version": payload["c1"]["srs_version"], "bound_uml_version": payload["c2"]["uml_version"],
            "approved_at_utc": "2026-10-03T00:00:00Z", **changes}


def test_human_override_is_explicit_version_bound_and_recorded():
    payload = _package()
    payload["c2"]["release_status"] = "NEEDS_HUMAN_REVIEW"
    payload["human_override"] = _override(payload)
    assert _validate_pkg(payload).report.override_applied["override_id"] == "OVR-1"
    payload["human_override"] = _override(payload, bound_uml_version="UML-OLD")
    assert "OVERRIDE_VERSION_MISMATCH" in _codes(lambda: _validate_pkg(payload))
    failed = _package()
    failed["c2"]["release_status"] = "FAILED"
    failed["human_override"] = _override(failed)
    assert "C2_RELEASE_NOT_VALIDATED" in _codes(lambda: _validate_pkg(failed))


def test_exported_contract_schemas_are_current():
    result = subprocess.run([sys.executable, str(COMPONENT_ROOT / "scripts" / "export_hybrid_schemas.py"), "--check"],
                            capture_output=True, text=True, cwd=COMPONENT_ROOT)
    assert result.returncode == 0, result.stdout


def test_legacy_upload_adapter_is_provisional_demo_input():
    legacy = ProvisionalInputPackage.model_validate(json.loads((SIMULATED / "gpa_input_package.json").read_text(encoding="utf-8")))
    assert classify_legacy_package(legacy) == "PROVISIONAL_DEMO_INPUT"


# --------------------------------------------------------------------------- knowledge base


def test_kb_loads_sliit_sample_policy_with_provenance():
    kb = load_knowledge_base()
    policy = kb.gpa_policy
    assert kb.kb_version == "1.0.0" and len(kb.digest_sha256) == 64
    assert policy.authority_status == "SAMPLE_RESEARCH_POLICY" and policy.requires_explicit_acceptance
    assert policy.provenance["verified_by_institution"] is False
    points = {g.grade: g.grade_point for g in policy.grades}
    assert points == {"A+": 4.0, "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7, "C+": 2.3,
                      "C": 2.0, "C-": 1.7, "D+": 1.3, "D": 1.0, "E": 0.0}
    assert policy.grade_point_tenths("Z") is None
    assert load_knowledge_base().digest_sha256 == kb.digest_sha256


def _kb_copy(tmp_path: Path) -> Path:
    target = tmp_path / "kb"
    shutil.copytree(KB_ROOT, target)
    return target


def test_kb_rejects_duplicate_grade_and_bad_precision(tmp_path):
    root = _kb_copy(tmp_path)
    path = root / "domains/gpa/grading-policy.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"][0]["grades"][1]["grade"] = "A+"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="duplicate grade"):
        load_knowledge_base(root)
    data["items"][0]["grades"][1]["grade"] = "A"
    data["items"][0]["grades"][1]["grade_point"] = 3.95
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="decimal"):
        load_knowledge_base(root)


def test_kb_change_changes_digest(tmp_path):
    root = _kb_copy(tmp_path)
    path = root / "domains/gpa/calculation-rules.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"][1]["decimal_places"] = 3
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_knowledge_base(root).digest_sha256 != load_knowledge_base().digest_sha256


# --------------------------------------------------------------------------- rules


def test_rule_engine_matches_gpa_targets_deterministically():
    kb = load_knowledge_base()
    engine = RuleEngine(load_rule_set(knowledge_base=kb))
    target = GenerationTarget("UML_CLASS:GpaCalculationService", "UML_CLASS",
                              {"domain": "gpa", "stack_id": "react-nodejs", "class_name": "GpaCalculationService",
                               "class_role": "SERVICE", "methods": ["calculate", "listHistory"], "attributes": []})
    decision = engine.decide(target)
    assert decision.outcome is RuleOutcome.MATCHED
    assert [r.rule_id for r in decision.matched_rules] == ["R-GPA-CALC-001"]
    assert engine.decide(target).as_json() == decision.as_json()


def test_no_rule_is_unsupported_and_nothing_is_fabricated():
    engine = RuleEngine(load_rule_set())
    decision = engine.decide(GenerationTarget("UML_CLASS:Payroll", "UML_CLASS",
                                              {"domain": "gpa", "class_name": "Payroll", "class_role": "SERVICE", "methods": ["pay"]}))
    assert decision.outcome is RuleOutcome.UNSUPPORTED and not decision.matched_rules
    assert "NO_RULE_MATCHED" in decision.reasons[0]


def _rules_copy(tmp_path: Path) -> Path:
    target = tmp_path / "rules"
    shutil.copytree(RULES_ROOT, target)
    return target


def test_equal_priority_rules_are_ambiguous(tmp_path):
    root = _rules_copy(tmp_path)
    path = root / "gpa-calculation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    twin = copy.deepcopy(data["rules"][1])
    twin["rule_id"] = "R-GPA-CALC-TWIN"
    data["rules"].append(twin)
    path.write_text(json.dumps(data), encoding="utf-8")
    engine = RuleEngine(load_rule_set(root))
    decision = engine.decide(GenerationTarget("UML_CLASS:GpaCalculationService", "UML_CLASS",
                                              {"domain": "gpa", "class_name": "GpaCalculationService", "class_role": "SERVICE",
                                               "methods": ["calculate", "listHistory"]}))
    assert decision.outcome is RuleOutcome.AMBIGUOUS
    assert review_state([decision]) is RuleOutcome.REVIEW_REQUIRED


def test_rule_referencing_unknown_knowledge_item_is_rejected(tmp_path):
    root = _rules_copy(tmp_path)
    path = root / "crud.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rules"][0]["requires_knowledge"].append("KB-DOES-NOT-EXIST")
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuleSetError, match="unknown knowledge items"):
        load_rule_set(root, knowledge_base=load_knowledge_base())


# --------------------------------------------------------------------------- policy acceptance + generation


def test_sample_policy_requires_explicit_bound_acceptance(pipeline):
    def run(acceptance):
        return asyncio.run(pipeline.generate(HybridGenerationRequest.model_validate(
            {"package": _package(), "policy_acceptance": acceptance})))
    assert "POLICY_ACCEPTANCE_REQUIRED" in _codes(lambda: run(None))
    assert "POLICY_ACCEPTANCE_MISMATCH" in _codes(lambda: run(_acceptance(pipeline, policy_digest_sha256="0" * 64)))
    assert "SAMPLE_POLICY_NOT_ACKNOWLEDGED" in _codes(lambda: run(_acceptance(pipeline, acknowledges_sample_status=False)))


def test_generation_is_deterministic_rule_governed_and_token_free(pipeline):
    first, second = _generate(pipeline), _generate(pipeline)
    m1, m2 = first["manifest"], second["manifest"]
    assert first["status"] == "ACCEPTED"
    assert m1["artifact_digest_sha256"] == m2["artifact_digest_sha256"]
    assert [f["sha256"] for f in m1["files"]] == [f["sha256"] for f in m2["files"]]
    assert m1["llm"]["calls"] == 0 and m1["llm"]["model_modules"] == []
    assert {"R-GPA-CALC-001@1.0.0", "R-GPA-POLICY-001@1.0.0", "R-DB-001@1.0.0"} <= set(m1["rule_set"]["selected_rules"])
    assert m1["knowledge_base"]["kb_version"] == "1.0.0"
    assert m1["policy"]["policy"]["authority_status"] == "SAMPLE_RESEARCH_POLICY"
    paths = {f["path"] for f in m1["files"]}
    for prefix in ("frontend/", "backend/src/", "database/migrations/", "openapi/", "test-seams/", "deployment/"):
        assert any(p.startswith(prefix) for p in paths), prefix
    for record in m1["files"]:
        assert record["requirement_ids"] and record["rule_ids"] and record["srs_version"] == "SRS-GPA-2.0"
    run_dir = pipeline.root / "gpa-hybrid" / first["generation_run_id"]
    assert (run_dir / "generated-project" / "generation-manifest.json").is_file()
    assert (run_dir / "generated-project" / "traceability" / "trace-graph.json").is_file()


def test_rendered_templates_embed_policy_and_approved_constraints():
    package = HybridInputPackage.model_validate(_package())
    validated = HybridContractValidator().validate(package)
    spec = build_gpa_spec(package, validated.design_context, load_knowledge_base())
    files = {p: c for m in render_modules(spec, list(MODULES)).values() for p, c in m.items()}
    assert '"B+": 33' in files["backend/src/policy/gradingPolicy.js"]
    assert "SAMPLE_RESEARCH_POLICY" in files["frontend/src/policy/gradingPolicy.js"]
    assert "credits BETWEEN 1 AND 20" in files["database/migrations/001_create_gpa_calculations.sql"]
    assert '"max": 20' in files["backend/src/validation/gpaRequestValidator.js"]
    assert "UNKNOWN_GRADE" in files["backend/src/validation/gpaRequestValidator.js"]
    assert "REPEATED_MODULE_POLICY_UNDEFINED" in files["backend/src/services/gpaCalculationService.js"]
    assert "run" not in json.dumps(sorted(files)).lower().replace("runtime", "")  # no run ids in paths
    assert not any("SRS-GPA" in content for content in files.values())


def test_gpa_reference_oracle_matches_known_benchmark():
    """Python reference of KB-GPA-FORMULA + KB-GPA-ROUNDING; the JS twin is checked in the Docker smoke test."""
    policy = load_knowledge_base().gpa_policy
    modules = [(4, "A"), (3, "B+"), (2, "C"), (3, "A-")]
    numerator = sum(c * policy.grade_point_tenths(g) for c, g in modules)
    denominator = 10 * sum(c for c, _ in modules)
    scaled = (2 * numerator * 100 + denominator) // (2 * denominator)
    assert f"{scaled / 100:.2f}" == "3.42"


# --------------------------------------------------------------------------- RAG


def test_rag_metadata_filters_topk_and_budget():
    store = FilterBestPracticeStore(load_rule_cards(COMPONENT_ROOT / "rules"))
    hits = store.search(RetrievalQuery(task="repository sql", stack="node", layer="repository",
                                       artifact_type="REPOSITORY", module="be.repository"))
    assert 1 <= len(hits) <= 5 and hits[0].card.id == "node-repo-001"
    evidence = hits[0].evidence()
    assert {"chunk_id", "document_id", "version", "content_digest_sha256", "score", "stack", "layer"} <= set(evidence)
    excluded = store.search(RetrievalQuery(task="x", stack="react", layer="ui", artifact_type="FRONTEND", module="fe.other"))
    assert all("fe.gpa-form" not in hit.card.modules for hit in excluded)
    many = store.search(RetrievalQuery(task="x", stack="node", layer="api", top_k=50))
    assert len(many) <= 5
    tiny = store.search(RetrievalQuery(task="x", stack="node", layer="api", max_context_tokens=60))
    assert sum(h.card.token_estimate for h in tiny) <= 60


def test_rag_refuses_authoritative_truth_as_guidance():
    raw = {"id": "bad", "stack": "any", "layer": "any", "category": "grading-policy", "priority": 1,
           "rule": "A is 4.0", "bad_example": "x", "good_example": "y"}
    with pytest.raises(RuleCardError, match="authoritative"):
        _validate(raw, "test")


def test_generation_records_retrieved_chunk_ids_and_versions(pipeline):
    manifest = _generate(pipeline)["manifest"]
    retrieval = next(r for r in manifest["rag"]["retrievals"] if r["module_id"] == "be.repository")
    assert retrieval["hits"][0]["rule_id"] == "node-repo-001" and retrieval["hits"][0]["version"]
    assert retrieval["applied_to_prompt"] is False and len(retrieval["hits"]) <= 5
    assert retrieval["context_tokens"] <= 2000


# --------------------------------------------------------------------------- OpenRouter gateway


class FakeOpenRouter:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        output = self.outputs.pop(0)
        if isinstance(output, ApplicationError):
            raise output
        return LLMInferenceResponse(output_text=output, metadata=LLMInferenceMetadata(
            provider="openrouter", configured_model_identifier="test/model", response_model_identifier="test/model-2026",
            prompt_template_version=request.prompt_template_version,
            generation_parameters=LLMGenerationParameters(temperature=0.0, timeout_seconds=30, max_tokens=1500),
            client_inference_latency_ms=12.5,
            response=OpenRouterResponseMetadata(model="test/model-2026", prompt_tokens=400, completion_tokens=120, total_tokens=520)))


GOOD_TREND = json.dumps({"path": "backend/src/custom/gpaTrendService.js", "content":
    "export class GpaTrendService {\n  compare(previousGpa, currentGpa) {\n    if (currentGpa > previousGpa) return 'IMPROVED';\n"
    "    if (currentGpa < previousGpa) return 'DECLINED';\n    return 'UNCHANGED';\n  }\n}\n"})


def _context(**changes) -> BoundedModuleContext:
    values = dict(module_id="custom.gpa-trend-service", target_path="backend/src/custom/gpaTrendService.js",
                  class_name="GpaTrendService", methods=(InterfaceMethod("compare", ("previousGpa", "currentGpa")),),
                  requirement_slices=({"requirement_id": "REQ-GPA-106", "requirement_version": 1, "statement": "Compare GPAs."},),
                  uml_slice="class GpaTrendService {\n  +compare(previousGpa: Number, currentGpa: Number): String\n}",
                  uml_version="UML-GPA-2.0", stack_id="react-nodejs", rule_ids=("R-LLM-BOUNDED-001@1.0.0",),
                  kb_digest="k" * 64, rule_set_digest="r" * 64, rag_prompt="", rag_digest="d" * 64)
    values.update(changes)
    return BoundedModuleContext(**values)


def test_gateway_caches_and_reports_cache_hits(tmp_path):
    client = FakeOpenRouter([GOOD_TREND])
    gateway = OpenRouterModuleGateway(client, provider="openrouter", model="test/model", cache_dir=tmp_path)
    first = asyncio.run(gateway.generate(_context()))
    second = asyncio.run(gateway.generate(_context()))
    assert first.status == "ACCEPTED" and not first.cache_hit and first.ledger[0]["prompt_tokens"] == 400
    assert second.cache_hit and second.ledger[0]["cache_hit"] and len(client.requests) == 1
    assert cache_key(_context(), "openrouter", "test/model") != cache_key(_context(), "openrouter", "other/model")
    assert cache_key(_context(), "openrouter", "m") != cache_key(_context(kb_digest="z" * 64), "openrouter", "m")
    assert cache_key(_context(), "openrouter", "m") != cache_key(_context(rag_digest="e" * 64), "openrouter", "m")


def test_gateway_retry_limit_escalates_to_human_review(tmp_path):
    bad = json.dumps({"path": "backend/src/custom/gpaTrendService.js", "content": "export function nope() {}"})
    client = FakeOpenRouter([bad, bad, GOOD_TREND])
    result = asyncio.run(OpenRouterModuleGateway(client, provider="openrouter", model="m", cache_dir=tmp_path).generate(_context()))
    assert result.status == "HUMAN_REVIEW_REQUIRED" and len(client.requests) == 2 and len(result.ledger) == 2
    repair_prompt = client.requests[1].messages[1].content
    assert "VALIDATOR_FINDINGS" in repair_prompt and "INTERFACE_VIOLATION" in repair_prompt


def test_gateway_provider_errors_and_budget_are_explicit(tmp_path):
    limited = ApplicationError([ErrorDetail(code="OPENROUTER_RATE_LIMITED", message="429")], status_code=429)
    client = FakeOpenRouter([limited])
    result = asyncio.run(OpenRouterModuleGateway(client, provider="openrouter", model="m", cache_dir=tmp_path).generate(_context()))
    assert result.status == "PROVIDER_ERROR" and "OPENROUTER_RATE_LIMITED" in result.reasons[0] and len(client.requests) == 1
    huge = _context(uml_slice="x" * 40000)
    blocked = asyncio.run(OpenRouterModuleGateway(FakeOpenRouter([]), provider="openrouter", model="m", cache_dir=tmp_path,
                                                  max_input_tokens=1000).generate(huge))
    assert blocked.status == "BUDGET_EXCEEDED"
    none = asyncio.run(OpenRouterModuleGateway(None, provider="openrouter", model="m", cache_dir=tmp_path).generate(_context()))
    assert none.status == "PROVIDER_ERROR" and "OPENROUTER_UNAVAILABLE" in none.reasons[0]


def test_unsupported_custom_class_without_llm_permission_requires_review(pipeline):
    result = _generate(pipeline, _package("gpa_custom_extension_package.json"))
    assert result["status"] == "PARTIAL_REVIEW_REQUIRED"
    items = {i["target_id"]: i for i in result["manifest"]["review_items"]}
    assert items["UML_CLASS:GpaTrendService"]["outcome"] == "HUMAN_REVIEW_REQUIRED"
    coverage = {r["requirement_id"]: r["status"] for r in result["manifest"]["traceability"]["coverage"]["requirements"]}
    assert coverage["REQ-GPA-106"] == "NOT_IMPLEMENTED" and result["manifest"]["llm"]["calls"] == 0


def test_llm_request_is_minimized_to_the_affected_module(pipeline):
    client = FakeOpenRouter([GOOD_TREND])
    pipeline._client_factory = lambda: client
    result = _generate(pipeline, _package("gpa_custom_extension_package.json"), allow_llm_for_unsupported=True)
    prompt = client.requests[0].messages[1].content
    assert "REQ-GPA-106" in prompt and "REQ-GPA-101" not in prompt and "REQ-GPA-103" not in prompt
    assert "ModuleResult" not in prompt and "gpaCalculationService" not in prompt
    manifest = result["manifest"]
    assert manifest["llm"]["calls"] == 1 and manifest["llm"]["model_modules"] == ["custom.gpa-trend-service"]
    entry = manifest["llm"]["ledger"][0]
    assert entry["response_model"] == "test/model-2026" and entry["prompt_tokens"] == 400 and entry["accepted"]
    assert result["status"] == "PARTIAL_REVIEW_REQUIRED"  # model output stays REVIEW_REQUIRED before wiring


# --------------------------------------------------------------------------- traceability


def test_traceability_links_cover_the_required_chain(pipeline):
    result = _generate(pipeline)
    graph = pipeline.trace("PROJECT-GPA-HYBRID-001")
    relations = {link["relation"] for link in graph["graph"]["links"] if link["status"] == "ACTIVE"}
    assert {"DESIGNED_BY", "GENERATED_AS", "PRODUCED", "CONSTRAINED", "EXPOSED_BY", "STORED_BY",
            "VERIFIED_THROUGH", "IMPLEMENTED_BY", "CONTAINS", "TARGETS"} <= relations
    assert graph["coverage"]["traced_count"] == 5 and graph["coverage"]["orphan_artifacts"] == []
    assert result["orphans"] == []


def test_orphan_artifacts_are_detected():
    graph = LivingTraceGraph("G", "P")
    graph.add_node("CODE_FILE", "backend/src/x.js", sha256="a", accepted=True)
    reasons = {o["reason"] for o in graph.orphans()}
    assert "no RULE PRODUCED link" in reasons and "not contained in any MODULE" in reasons


def test_requirement_change_regenerates_only_the_impact_set(pipeline):
    base = _generate(pipeline)
    change = RequirementChangeRequest.model_validate({
        "base_generation_run_id": base["generation_run_id"], "package": _package("gpa_input_package_req103_v2.json"),
        "policy_acceptance": _acceptance(pipeline)})
    result = asyncio.run(pipeline.requirement_change(change))
    lineage = result["manifest"]["lineage"]
    assert lineage["changed_requirement_ids"] == ["REQ-GPA-103"]
    assert "be.service" not in lineage["impact_set"] and "be.validation" in lineage["impact_set"]
    states = {row["path"]: row["state"] for row in lineage["preservation"]}
    assert states["backend/src/services/gpaCalculationService.js"] == "PRESERVED_UNTOUCHED"
    assert states["backend/src/validation/gpaRequestValidator.js"] == "REGENERATED_CHANGED"
    assert "UNEXPECTED_CHANGE" not in states.values()
    old = {f["path"]: f for f in base["manifest"]["files"]}
    for record in result["manifest"]["files"]:
        if states[record["path"]] == "PRESERVED_UNTOUCHED":
            assert record["sha256"] == old[record["path"]]["sha256"]
            assert record["created_in_generation_run_id"] == base["generation_run_id"]
    assert result["link_changes"]["preserved"] > 0 and result["link_changes"]["superseded"] > 0
    assert result["c4_handoff"]["retest_status"] == "PENDING"
    assert (pipeline.root / "gpa-hybrid" / base["generation_run_id"]).is_dir()  # previous version preserved
    assert "STALE_BASE_RUN" in _codes(lambda: asyncio.run(pipeline.requirement_change(change)))


def test_requirement_change_without_version_bump_is_rejected(pipeline):
    base = _generate(pipeline)
    package = _package("gpa_input_package_req103_v2.json")
    for requirement in package["c1"]["requirements"]:
        if requirement["requirement_id"] == "REQ-GPA-103":
            requirement["requirement_version"] = 1
    change = RequirementChangeRequest.model_validate({"base_generation_run_id": base["generation_run_id"], "package": package,
                                                      "policy_acceptance": _acceptance(pipeline)})
    assert "REQUIREMENT_CHANGED_WITHOUT_VERSION_BUMP" in _codes(lambda: asyncio.run(pipeline.requirement_change(change)))


# --------------------------------------------------------------------------- verification


def _files_and_design():
    package = HybridInputPackage.model_validate(_package())
    validated = HybridContractValidator().validate(package)
    kb = load_knowledge_base()
    spec = build_gpa_spec(package, validated.design_context, kb)
    rendered = render_modules(spec, list(MODULES))
    files = {p: c for m in rendered.values() for p, c in m.items()}
    owners = {p: mid for mid, m in rendered.items() for p in m}
    return validated.design_context, files, owners, kb


def test_design_to_code_passes_and_detects_mismatches():
    design, files, owners, kb = _files_and_design()
    types = kb.item("KB-TYPE-MAP")["mappings"]
    assert verify_design_to_code(design, files, owners, True, types).status == "PASS"
    broken = dict(files)
    broken["backend/src/services/gpaCalculationService.js"] = broken["backend/src/services/gpaCalculationService.js"].replace(
        "async listHistory()", "async history()")
    openapi = json.loads(broken["openapi/openapi.json"])
    openapi["components"]["schemas"]["ModuleResult"]["properties"]["credits"]["type"] = "string"
    del openapi["paths"]["/api/v1/gpa/policy"]
    openapi["paths"]["/api/v1/extra"] = {"get": {"operationId": "extraThing"}}
    broken["openapi/openapi.json"] = json.dumps(openapi)
    broken["database/migrations/001_create_gpa_calculations.sql"] = broken["database/migrations/001_create_gpa_calculations.sql"].replace(
        "CREATE TABLE IF NOT EXISTS gpa_calculation_modules", "CREATE TABLE IF NOT EXISTS module_rows")
    codes = {f.code for f in verify_design_to_code(design, broken, owners, True, types).findings}
    assert {"MISSING_METHOD", "TYPE_MISMATCH", "MISSING_ENDPOINT", "UNSUPPORTED_EXTRA_ELEMENT", "MISSING_DATABASE_ENTITY"} <= codes


def test_architecture_verifier_flags_forbidden_dependencies():
    _, files, owners, kb = _files_and_design()
    convention = kb.item("KB-ARCH-NODE-LAYERED")
    assert verify_architecture(files, owners, convention).status == "PASS"
    broken = dict(files)
    broken["backend/src/controllers/gpaController.js"] = "import { PostgresGpaCalculationRepository } from '../repositories/postgresGpaCalculationRepository.js';\n" + broken["backend/src/controllers/gpaController.js"]
    broken["backend/src/routes/gpaRoutes.js"] = "import { createPool } from '../db/pool.js';\n" + broken["backend/src/routes/gpaRoutes.js"]
    broken["frontend/src/App.jsx"] = "import pg from 'pg';\n" + broken["frontend/src/App.jsx"]
    broken["backend/src/services/gpaCalculationService.js"] += "\nexport const leak = (pool) => pool.query('SELECT 1');\n"
    report = verify_architecture(broken, owners, convention)
    observed = {f.observed.split(" (")[0] for f in report.findings if f.code == "FORBIDDEN_DEPENDENCY"}
    assert {"CONTROLLER -> REPOSITORY", "ROUTE -> DATABASE", "FRONTEND -> DATABASE"} <= observed
    assert "DATABASE_ACCESS_OUTSIDE_REPOSITORY" in {f.code for f in report.findings}
    assert report.regeneration_triggers()  # verifiers only trigger; they never patch


# --------------------------------------------------------------------------- C4 contracts and gate


def test_c4_defect_flow_rejects_stale_and_out_of_scope_reports(pipeline):
    base = _generate(pipeline)
    defective = pipeline.inject_defect_for_demo(base["generation_run_id"])
    assert defective["status"] == "DEFECT_INJECTED_FOR_DEMO"
    submission = pipeline.simulated_defect(defective["generation_run_id"])["submission"]
    bad_scope = copy.deepcopy(submission)
    bad_scope["report"]["proposed_repair_scope"] = ["be.service", "fe.gpa-form"]
    assert "PATCH_OUTSIDE_IMPACT_SET" in _codes(lambda: asyncio.run(pipeline.c4_defect(C4DefectSubmission.model_validate(bad_scope))))
    unknown = copy.deepcopy(submission)
    unknown["report"]["test_seam_id"] = "SEAM-NOPE"
    assert "UNKNOWN_TEST_SEAM" in _codes(lambda: asyncio.run(pipeline.c4_defect(C4DefectSubmission.model_validate(unknown))))
    repaired = asyncio.run(pipeline.c4_defect(C4DefectSubmission.model_validate(submission)))
    states = {r["path"]: r["state"] for r in repaired["manifest"]["lineage"]["preservation"]}
    assert states["backend/src/services/gpaCalculationService.js"] == "REGENERATED_CHANGED"
    assert list(states.values()).count("PRESERVED_UNTOUCHED") == len(states) - 1
    assert repaired["manifest"]["artifact_digest_sha256"] == base["manifest"]["artifact_digest_sha256"]
    assert "STALE_DEFECT_REPORT" in _codes(lambda: asyncio.run(pipeline.c4_defect(C4DefectSubmission.model_validate(submission))))


def test_defect_in_template_module_cannot_be_fixed_by_regeneration(pipeline):
    base = _generate(pipeline)
    submission = pipeline.simulated_defect(base["generation_run_id"])["submission"]
    result = asyncio.run(pipeline.c4_defect(C4DefectSubmission.model_validate(submission)))
    assert result["status"] == "REVIEW_REQUIRED" and "TEMPLATE_DEFECT" in result["reason"]


def test_deployment_gate_requires_exact_artifact_readiness(pipeline):
    base = _generate(pipeline)
    run_id = base["generation_run_id"]
    blocked = pipeline.deployment_gate(DeploymentGateRequest(generation_run_id=run_id))
    assert blocked["decision"] == "BLOCKED" and blocked["reasons"][0].startswith("NO_C4_READINESS_SIGNAL")
    assert blocked["pp1_scope"]["production_deployment"] == "OUT_OF_SCOPE_FOR_PP1"
    signal = pipeline.simulated_readiness(run_id)["readiness_signal"]
    for change, reason in [({"artifact_digest_sha256": "0" * 64}, "ARTIFACT_DIGEST_MISMATCH"),
                           ({"revoked": True}, "READINESS_REVOKED"),
                           ({"semantic_preservation": "UNRESOLVED"}, "SEMANTIC_PRESERVATION_UNRESOLVED"),
                           ({"convergence": "NON_CONVERGENT"}, "CONVERGENCE_NON_CONVERGENT")]:
        decision = pipeline.deployment_gate(DeploymentGateRequest.model_validate(
            {"generation_run_id": run_id, "readiness_signal": {**signal, **change}}))
        assert decision["decision"] == "BLOCKED" and any(r.startswith(reason) for r in decision["reasons"])
    allowed = pipeline.deployment_gate(DeploymentGateRequest.model_validate({"generation_run_id": run_id, "readiness_signal": signal}))
    assert allowed["decision"] == "ALLOWED" and "SIMULATED" in allowed["authorization_scope"]
    assert allowed["deployment_action"].startswith("NONE_PERFORMED")
    _generate(pipeline)  # a newer artifact supersedes the old one
    stale = pipeline.deployment_gate(DeploymentGateRequest.model_validate({"generation_run_id": run_id, "readiness_signal": signal}))
    assert stale["decision"] == "BLOCKED" and any(r.startswith("SUPERSEDED_ARTIFACT") for r in stale["reasons"])


# --------------------------------------------------------------------------- docker preview orchestration


class FakeDocker:
    def __init__(self):
        self.calls = []
        self.containers = {}

    def __call__(self, args, **_kwargs):
        self.calls.append(args)
        command = args[1]
        out = ""
        if command == "version":
            out = "29.0.0"
        elif command in {"run", "create"}:
            name = args[args.index("--name") + 1]
            labels = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
            self.containers[name] = {"Names": name, "State": "running", "Status": "Up", "Labels": ",".join(labels)}
        elif command == "rm":
            self.containers.pop(args[-1], None)
        elif command == "ps":
            selector = args[args.index("--filter") + 1].removeprefix("label=")
            out = "\n".join(json.dumps(c) for c in self.containers.values() if selector in c["Labels"])
        return subprocess.CompletedProcess(args, 0, out, "")


class FakeResponse:
    def __init__(self, status_code, body=None, text=""):
        self.status_code, self._body, self.text = status_code, body, text

    def json(self):
        return self._body


def test_preview_orchestration_is_isolated_and_reports_urls_after_health(pipeline):
    run_id = _generate(pipeline)["generation_run_id"]
    docker = FakeDocker()
    get = lambda url: FakeResponse(200, {"status": "UP", "database": "UP"}) if url.endswith("/api/health") else FakeResponse(200, text='<div id="root"></div>')
    post = lambda url, body: FakeResponse(201, {"gpaText": "3.42", "policyId": "P", "policyVersion": "1", "policyAuthorityStatus": "S"})
    service = HybridPreviewService(pipeline, runner=docker, http_get=get, http_post=post, health_timeout=5)
    session = service.start(run_id)
    assert session["status"] == "RUNNING" and session["execution"] == "LOCAL_SANDBOX_PREVIEW_NOT_DEPLOYED"
    ui_port, api_port = int(session["frontend_url"].rsplit(":", 1)[1]), int(session["api_url"].rsplit(":", 1)[1])
    assert ui_port != api_port and not {ui_port, api_port} & RESERVED_PORTS
    flat = [" ".join(call) for call in docker.calls]
    runs = [c for c in flat if c.startswith("docker run") or c.startswith("docker create")]
    assert all("--cap-drop ALL" in c and "no-new-privileges" in c and "--user" in c for c in runs)
    assert not any(" -v " in c or "docker.sock" in c or "--privileged" in c for c in flat)
    published = [c for c in runs if " -p " in c]
    assert len(published) == 2 and all("-p 127.0.0.1:" in c for c in published)
    db = next(c for c in runs if "-db " in c)
    assert " -p " not in db and any("network create --internal" in c for c in flat)
    assert service.gpa_check(session["preview_id"])["passed"] is True
    stopped = service.stop(session["preview_id"])
    assert stopped["status"] == "STOPPED" and len(stopped["removed_containers"]) == 3 and not docker.containers


def test_preview_unhealthy_is_cleaned_up_with_evidence(pipeline):
    run_id = _generate(pipeline)["generation_run_id"]
    docker = FakeDocker()
    service = HybridPreviewService(pipeline, runner=docker, http_get=lambda url: FakeResponse(503, None), health_timeout=1)
    assert "PREVIEW_UNHEALTHY" in _codes(lambda: service.start(run_id))
    assert not docker.containers
    report = pipeline.run_report(run_id)
    assert report["evidence"]["preview_events"][-1]["event"] == "PREVIEW_UNHEALTHY"


def test_preview_reports_docker_unavailable(pipeline):
    run_id = _generate(pipeline)["generation_run_id"]

    def missing(args, **_kwargs):
        raise FileNotFoundError("docker")

    assert "DOCKER_UNAVAILABLE" in _codes(lambda: HybridPreviewService(pipeline, runner=missing).start(run_id))


# --------------------------------------------------------------------------- OpenRouter trial (LLM vs template)

TRIAL_MODULE = json.dumps({"path": "backend/src/services/gpaCalculationService.js", "content": (
    "export class GpaCalculationService {\n"
    "  constructor({ repository }) { this.repository = repository; }\n"
    "  async calculate(modules) { return this.repository.save({ gpaText: '0.00', modules }); }\n"
    "  async listHistory() { return this.repository.list(); }\n"
    "}\n"
)})


class FakeSandbox:
    """Stands in for `docker run`: reports PASS for every case on the first call (LLM), a chosen split on the second."""

    def __init__(self, llm_failures=()):
        self.calls, self.llm_failures = [], set(llm_failures)

    def __call__(self, command, input=None, **_kwargs):
        self.calls.append((command, json.loads(input)))
        is_llm = len(self.calls) == 1
        results = [{"id": c["id"], "passed": not (is_llm and c["id"] in self.llm_failures), "observed": "x"} for c in CASES]
        return subprocess.CompletedProcess(command, 0, "RESULTS " + json.dumps(results), "")


def test_llm_trial_compares_in_a_locked_sandbox_without_touching_the_artifact(pipeline):
    run = _generate(pipeline)
    client = FakeOpenRouter([TRIAL_MODULE])
    pipeline._client_factory = lambda: client
    sandbox = FakeSandbox(llm_failures={"half-up-rounding"})
    trial = asyncio.run(LlmModuleTrial(pipeline, runner=sandbox).run(run["generation_run_id"], bypass_cache=True))
    assert trial["classification"] == "LLM_TRIAL_NOT_PART_OF_ARTIFACT" and trial["status"] == "ACCEPTED"
    assert trial["verdict"].startswith(f"LLM_MODULE_FAILED_1_OF_{len(CASES)}") and "half-up-rounding" in trial["verdict"]
    # bounded context: only the requirements linked to the service module, only its UML class
    prompt = client.requests[0].messages[1].content
    assert "REQ-GPA-102" in prompt and "REQ-GPA-101" not in prompt and "REQ-GPA-104" not in prompt
    assert "KB-GPA-FORMULA" in prompt and "HALF_UP" in prompt and "class GpaCalculationService" in prompt
    assert trial["context_summary"]["other_requirements_or_files_sent"] == 0
    # sandbox command is locked down and the module is passed on stdin, never mounted
    command, payload = sandbox.calls[0]
    flat = " ".join(command)
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--user 1000:1000", "no-new-privileges"):
        assert flag in flat, flag
    assert "-v " not in flat and "--mount" not in flat and "docker.sock" not in flat and "--privileged" not in flat
    assert "src/services/gpaCalculationService.js" in payload["files"]
    template_run = sandbox.calls[1][1]["files"]
    assert "src/errors.js" in template_run and "src/services/gpaCalculationService.js" in template_run  # control run uses the template
    # artifact, manifest and evidence integrity untouched; trial is recorded as evidence
    report = pipeline.run_report(run["generation_run_id"])
    assert report["manifest"]["artifact_digest_sha256"] == run["manifest"]["artifact_digest_sha256"]
    assert report["evidence"]["integrity_problems"] == []
    log = pipeline.find_run(run["generation_run_id"])[0] / "evidence" / "llm-trials.jsonl"
    assert json.loads(log.read_text(encoding="utf-8").splitlines()[-1])["trial_id"] == trial["trial_id"]


def test_llm_trial_provider_failure_and_missing_docker_are_explicit(pipeline):
    run = _generate(pipeline)
    truncated = ApplicationError([ErrorDetail(code="OPENROUTER_OUTPUT_TRUNCATED", message="stopped (reasoning_tokens=4096)")], status_code=502)
    pipeline._client_factory = lambda: FakeOpenRouter([truncated, truncated])
    failed = asyncio.run(LlmModuleTrial(pipeline, runner=FakeSandbox()).run(run["generation_run_id"], bypass_cache=True))
    assert failed["status"] == "HUMAN_REVIEW_REQUIRED" and failed["llm"] is None and failed["comparison"] is None
    assert [e["error_code"] for e in failed["ledger"]] == ["OPENROUTER_OUTPUT_TRUNCATED"] * 2
    assert "reasoning_tokens=4096" in failed["ledger"][0]["error_message"]
    assert failed["verdict"].startswith("NO_MODULE_TO_COMPARE")

    def no_docker(command, **_kwargs):
        raise FileNotFoundError("docker")

    pipeline._client_factory = lambda: FakeOpenRouter([TRIAL_MODULE])
    unrun = asyncio.run(LlmModuleTrial(pipeline, runner=no_docker).run(run["generation_run_id"], bypass_cache=True))
    assert unrun["status"] == "ACCEPTED" and unrun["verdict"].startswith("NOT_EXECUTED: DOCKER_UNAVAILABLE")
    pipeline._client_factory = None
    none = asyncio.run(LlmModuleTrial(pipeline, runner=FakeSandbox()).run(run["generation_run_id"], bypass_cache=True))
    assert none["status"] == "PROVIDER_ERROR" and "OPENROUTER_UNAVAILABLE" in none["reasons"][0]


# --------------------------------------------------------------------------- clear history (REQ-GPA-104 v2)


def _clear_history_files(name: str = "gpa_input_package_req104_v2.json"):
    package = HybridInputPackage.model_validate(_package(name))
    validated = HybridContractValidator().validate(package)
    kb = load_knowledge_base()
    spec = build_gpa_spec(package, validated.design_context, kb)
    rendered = render_modules(spec, list(MODULES))
    files = {p: c for m in rendered.values() for p, c in m.items()}
    owners = {p: mid for mid, m in rendered.items() for p in m}
    return spec, validated.design_context, files, owners, kb


def test_clear_history_is_only_generated_when_the_released_design_declares_it():
    base_spec, _, base_files, _, _ = _clear_history_files("gpa_input_package.json")
    assert base_spec.clear_history is False
    joined = "\n".join(base_files.values())
    assert "clearHistory" not in joined and "clearGpaHistory" not in joined and "'GET,POST,OPTIONS'" in joined

    spec, _, files, _, _ = _clear_history_files()
    assert spec.clear_history is True
    assert "async clearHistory()" in files["backend/src/services/gpaCalculationService.js"]
    assert "router.delete('/gpa/calculations'" in files["backend/src/routes/gpaRoutes.js"]
    assert "DELETE FROM gpa_calculations" in files["backend/src/repositories/postgresGpaCalculationRepository.js"]
    assert "'GET,POST,DELETE,OPTIONS'" in files["backend/src/app.js"]
    assert "onClear={clear}" in files["frontend/src/App.jsx"]
    assert "clearCalculations" in files["frontend/src/api/gpaApi.js"]
    assert json.loads(files["openapi/openapi.json"])["paths"]["/api/v1/gpa/calculations"]["delete"]["operationId"] == "clearGpaHistory"
    seams = json.loads(files["test-seams/c4-test-seams.json"])
    assert "SEAM-GPA-API-CLEAR" in {seam["seam_id"] for seam in seams["seams"]}
    assert "clearGpaHistory" in {op["operation_id"] for op in seams["operations"]}


def test_clear_history_design_passes_design_to_code_and_incomplete_designs_are_refused():
    spec, design, files, owners, kb = _clear_history_files()
    types = kb.item("KB-TYPE-MAP")["mappings"]
    assert verify_design_to_code(design, files, owners, True, types, clear_history=True).status == "PASS"
    without_route = dict(files)
    without_route["backend/src/routes/gpaRoutes.js"] = files["backend/src/routes/gpaRoutes.js"].replace("router.delete", "router.options")
    codes = {f.code for f in verify_design_to_code(design, without_route, owners, True, types, clear_history=True).findings}
    assert "MISSING_ENDPOINT" in codes

    broken = _package("gpa_input_package_req104_v2.json")
    for artifact in broken["c2"]["uml_artifacts"]:
        if artifact["diagram_type"] == "CLASS":
            artifact["plantuml_source"] = artifact["plantuml_source"].replace("  +clear(): void\n", "")
    package = HybridInputPackage.model_validate(broken)
    validated = HybridContractValidator().validate(package)
    with pytest.raises(Exception) as caught:
        build_gpa_spec(package, validated.design_context, kb)
    assert getattr(caught.value, "code", "") == "CLEAR_HISTORY_DESIGN_INCOMPLETE"


def test_clear_history_arrives_as_an_approved_requirement_change(pipeline):
    base = _generate(pipeline)
    change = RequirementChangeRequest.model_validate({
        "base_generation_run_id": base["generation_run_id"], "package": _package("gpa_input_package_req104_v2.json"),
        "policy_acceptance": _acceptance(pipeline)})
    result = asyncio.run(pipeline.requirement_change(change))
    lineage = result["manifest"]["lineage"]
    assert "REQ-GPA-104" in lineage["changed_requirement_ids"]
    assert {"be.service", "be.repository", "be.controller", "be.routes", "api.openapi", "fe.app-shell", "test-seams"} <= set(lineage["impact_set"])
    assert "be.validation" not in lineage["impact_set"]
    states = {row["path"]: row["state"] for row in lineage["preservation"]}
    assert states["backend/src/validation/gpaRequestValidator.js"] == "PRESERVED_UNTOUCHED"
    assert states["backend/src/services/gpaCalculationService.js"] == "REGENERATED_CHANGED"
    assert "UNEXPECTED_CHANGE" not in states.values()
    old_service = (pipeline.root / "gpa-hybrid" / base["generation_run_id"] / "generated-project" / "backend/src/services/gpaCalculationService.js").read_text(encoding="utf-8")
    new_service = (pipeline.root / "gpa-hybrid" / result["generation_run_id"] / "generated-project" / "backend/src/services/gpaCalculationService.js").read_text(encoding="utf-8")
    assert "clearHistory" not in old_service and "async clearHistory()" in new_service


def test_api_and_seam_links_follow_the_members_a_requirement_names(pipeline):
    """Clearing the history belongs to REQ-GPA-104 only; calculating must not inherit it through the shared service class."""
    run = _generate(pipeline, _package("gpa_input_package_req104_v2.json"))
    graph = pipeline.trace(run["manifest"]["input"]["project_id"])["graph"]
    nodes = {node["node_id"]: node for node in graph["nodes"]}

    def requirements_of(relation: str, target_key: str) -> set[str]:
        return {
            nodes[link["source"]]["key"]
            for link in graph["links"]
            if link["status"] == "ACTIVE" and link["relation"] == relation and nodes[link["target"]]["key"] == target_key
        }

    assert requirements_of("EXPOSED_BY", "clearGpaHistory") == {"REQ-GPA-104"}
    assert requirements_of("VERIFIED_THROUGH", "SEAM-GPA-API-CLEAR") == {"REQ-GPA-104"}
    assert requirements_of("EXPOSED_BY", "listGpaCalculations") == {"REQ-GPA-104"}
    assert requirements_of("EXPOSED_BY", "getGradingPolicy") == {"REQ-GPA-102", "REQ-GPA-105"}
    assert "REQ-GPA-102" in requirements_of("EXPOSED_BY", "calculateGpa")
    assert {"REQ-GPA-101", "REQ-GPA-103"} <= requirements_of("EXPOSED_BY", "calculateGpa")


def test_project_zip_is_exactly_the_verified_project_folder(pipeline):
    import hashlib
    import io
    import zipfile

    run = _generate(pipeline)
    run_id = run["generation_run_id"]
    name, data = pipeline.archive_zip(run_id)
    assert name == f"gpa-project-{run_id[-8:]}.zip"
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert archive.testzip() is None
    folder = name.removesuffix(".zip")
    assert {entry.split("/")[0] for entry in archive.namelist()} == {folder}
    project = next(pipeline.root.glob(f"*/{run_id}/generated-project"))
    on_disk = {p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file()}
    assert {entry.removeprefix(folder + "/") for entry in archive.namelist()} == on_disk
    for record in run["manifest"]["files"]:
        assert hashlib.sha256(archive.read(f"{folder}/{record['path']}")).hexdigest() == record["sha256"]
    assert {"generation-manifest.json", "traceability/trace-graph.json"} <= on_disk

    tampered = project / run["manifest"]["files"][0]["path"]
    tampered.write_text(tampered.read_text(encoding="utf-8") + " // edited", encoding="utf-8")
    assert "HYBRID_RUN_TAMPERED" in _codes(lambda: pipeline.archive_zip(run_id))


def test_project_location_and_open_folder_routes(pipeline, application, monkeypatch):
    from fastapi.testclient import TestClient

    run = _generate(pipeline)
    run_id = run["generation_run_id"]
    application.state.hybrid_pipeline = pipeline
    opened = []
    monkeypatch.setattr("intelise_c3.api.routes.hybrid._open_in_file_manager", opened.append)
    with TestClient(application) as client:
        application.state.hybrid_pipeline = pipeline
        located = client.get(f"/api/v1/hybrid/runs/{run_id}/location").json()
        assert Path(located["path"]).is_dir() and Path(located["path"]).name == "generated-project"
        assert (Path(located["path"]) / "README.md").is_file()
        assert client.post(f"/api/v1/hybrid/runs/{run_id}/open-folder").json()["opened"] is True
        assert opened == [Path(located["path"])]
        assert client.get("/api/v1/hybrid/runs/no-such-run/location").status_code == 404
        assert client.post("/api/v1/hybrid/runs/no-such-run/open-folder").status_code == 404
