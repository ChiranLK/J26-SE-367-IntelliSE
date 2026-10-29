"""LLM backend logic mode: TeamSocLo writes be.service + be.validation under rule/RAG governance.

The LLM client and the Docker sandbox are test doubles here, so these tests are deterministic and need
neither network nor Docker. ``test_template_modules_pass_the_shared_benchmarks_in_the_real_sandbox`` runs the
real sandbox when Docker is available, which proves the benchmark cases themselves are sound.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from uuid import uuid4

import pytest

from intelise_c3.contracts.hybrid import RequirementChangeRequest
from intelise_c3.core.config import COMPONENT_ROOT, Settings
from intelise_c3.domain.llm import (
    LLMGenerationParameters,
    LLMInferenceMetadata,
    LLMInferenceResponse,
    TeamSocLoResponseMetadata,
)
from intelise_c3.hybrid.gpa_spec import build_gpa_spec
from intelise_c3.hybrid.input_contracts import HybridContractValidator
from intelise_c3.contracts.hybrid import HybridInputPackage
from intelise_c3.hybrid.llm_sandbox import docker_available, run_sandbox, service_spec, validation_spec
from intelise_c3.hybrid.living_trace import graph_id_for
from intelise_c3.hybrid.pipeline import BackendLlm, HybridPipeline
from intelise_c3.hybrid.knowledge_base import load_knowledge_base

from test_hybrid_pipeline import _acceptance, _codes, _generate, _package

@pytest.fixture
def pipeline() -> HybridPipeline:
    workdir = COMPONENT_ROOT / "tmp" / f"pytest-hybrid-llm-{uuid4().hex[:8]}"
    settings = Settings(generated_workspace_root=workdir / "ws", traceability_store_path=workdir / "trace.sqlite3",
                        rag_enabled=True, rag_backend="filter", hybrid_llm_cache_dir=workdir / "cache")
    yield HybridPipeline(settings)
    shutil.rmtree(workdir, ignore_errors=True)


SERVICE_JSON = json.dumps({"path": "backend/src/services/gpaCalculationService.js", "content": (
    "export class GpaCalculationService {\n"
    "    constructor({ repository, gradingPolicy, clock, idGenerator }) {\n"
    "        this.repository = repository;\n"
    "    }\n"
    "    async calculate(modules) {\n"
    "        return this.repository.save({ gpaText: '0.00', modules });\n"
    "    }\n"
    "    async listHistory() {\n"
    "        return this.repository.list();\n"
    "    }\n"
    "}\n")})
VALIDATION_JSON = json.dumps({"path": "backend/src/validation/gpaRequestValidator.js", "content": (
    "export function validateGpaRequest(body, gradingPolicy) {\n"
    "  return { value: { modules: body.modules }, errors: [], review: [] };\n"
    "}\n")})


class FakeTeamSocLo:
    """Anthropic-shaped usage (input/output tokens), as the real TeamSocLo client reports."""

    def __init__(self, outputs):
        self.outputs, self.requests = list(outputs), []

    async def generate(self, request):
        self.requests.append(request)
        return LLMInferenceResponse(output_text=self.outputs.pop(0), metadata=LLMInferenceMetadata(
            provider="teamsoclo-claude", configured_model_identifier="claude-haiku-4-5", response_model_identifier="claude-haiku-4-5-test",
            prompt_template_version=request.prompt_template_version,
            generation_parameters=LLMGenerationParameters(temperature=0.0, timeout_seconds=30, max_tokens=4096),
            client_inference_latency_ms=21.0,
            response=TeamSocLoResponseMetadata(model="claude-haiku-4-5-test", input_tokens=700, output_tokens=180, total_tokens=880)))


class FakeSandbox:
    """Stands in for docker: `docker version` succeeds; benchmark runs report PASS except for chosen case ids."""

    def __init__(self, fail_cases=(), docker_ok=True):
        self.benchmarks, self.fail_cases, self.docker_ok = [], set(fail_cases), docker_ok

    def __call__(self, command, input=None, **_kwargs):
        if command[1] == "version":
            return subprocess.CompletedProcess(command, 0 if self.docker_ok else 1, "29.0" if self.docker_ok else "", "" if self.docker_ok else "daemon down")
        payload = json.loads(input)
        spec = json.loads(payload["files"]["cases.json"])
        self.benchmarks.append((spec["kind"], payload))
        results = [{"id": c["id"], "passed": c["id"] not in self.fail_cases, "observed": "x"} for c in spec["cases"]]
        return subprocess.CompletedProcess(command, 0, "RESULTS " + json.dumps(results), "")


def _wire(pipeline, client, sandbox):
    pipeline.backend_llm = BackendLlm("teamsoclo", "claude-haiku-4-5", lambda: client)
    pipeline._sandbox_runner = sandbox
    pipeline._client_factory = lambda: pytest.fail("OpenRouter must not be used in LLM backend mode")


def _llm_generate(pipeline):
    return _generate(pipeline, llm_backend_logic=True)


def test_teamsoclo_writes_service_and_validation_under_rule_and_rag_governance(pipeline):
    client, sandbox = FakeTeamSocLo([SERVICE_JSON, VALIDATION_JSON]), FakeSandbox()
    _wire(pipeline, client, sandbox)
    run = _llm_generate(pipeline)
    manifest = run["manifest"]
    assert run["status"] == "ACCEPTED" and manifest["generation_mode"] == "LLM_BACKEND_LOGIC"
    modules = {m["module_id"]: m for m in manifest["modules"]}
    for module_id in ("be.service", "be.validation"):
        assert modules[module_id]["origin"] == "TEAMSOCLO" and modules[module_id]["status"] == "ACCEPTED_LLM_BENCHMARK_PASSED"
        assert "R-LLM-BACKEND-001@1.0.0" in modules[module_id]["rule_ids"]
    assert modules["be.controller"]["origin"] == "TEMPLATE" and modules["db.schema"]["origin"] == "TEMPLATE"
    assert "R-GPA-CALC-001@1.0.0" in modules["be.service"]["rule_ids"]  # the deterministic rule still decided WHAT to build
    assert "R-LLM-BACKEND-001@1.0.0" in manifest["rule_set"]["selected_rules"]
    llm = manifest["llm"]
    assert llm["provider"] == "teamsoclo" and llm["calls"] == 2 and llm["model_modules"] == ["be.service", "be.validation"]
    assert llm["prompt_tokens"] == 1400 and llm["completion_tokens"] == 360  # TeamSocLo input/output tokens are mapped
    assert llm["backend_logic"]["accepted_modules"] == ["be.service", "be.validation"]
    # minimized prompts: each module sees only its own requirement, its own UML and applied RAG guidance
    service_prompt, validation_prompt = (r.messages[1].content for r in client.requests)
    assert "REQ-GPA-102" in service_prompt and "REQ-GPA-103" not in service_prompt and "REQ-GPA-104" not in service_prompt
    assert "REQ-GPA-103" in validation_prompt and "REQ-GPA-102" not in validation_prompt
    assert "class GpaCalculationService" in service_prompt and "class ModuleResult" in validation_prompt
    for prompt in (service_prompt, validation_prompt):
        assert "Apply these project best-practice rules" in prompt and "KB-GPA" in prompt
    applied = {r["module_id"]: r["applied_to_prompt"] for r in manifest["rag"]["retrievals"]}
    assert applied["be.service"] and applied["be.validation"] and not applied["be.controller"]
    # sandbox gate ran once per module, in the right order, over the module alone (no host execution)
    assert [kind for kind, _ in sandbox.benchmarks] == ["service", "validation"]
    # the shipped smoke test is the LLM-mode one (shared benchmark cases) and no longer needs template-only helpers
    paths = {f["path"] for f in manifest["files"]}
    assert {"backend/test/bench-cases.mjs", "backend/test/bench-runner.mjs", "backend/test/gpa.smoke.test.js"} <= paths
    smoke = next(f for f in pipeline.find_run(run["generation_run_id"])[0].rglob("gpa.smoke.test.js")).read_text(encoding="utf-8")
    assert "roundHalfUp" not in smoke and "runServiceCases" in smoke
    # verification, traceability and orphan checks still hold for model-written files
    assert run["verification"]["design_to_code"]["status"] == "PASS" and run["verification"]["architecture"]["status"] == "PASS"
    assert run["orphans"] == []
    graph = pipeline.trace("PROJECT-GPA-HYBRID-001")["graph"]
    produced = {(l["source"], l["target"]) for l in graph["links"] if l["relation"] == "PRODUCED" and l["status"] == "ACTIVE"}
    assert ("RULE:R-LLM-BACKEND-001", "CODE_FILE:backend/src/services/gpaCalculationService.js") in produced


def test_failed_benchmark_feeds_exact_findings_back_then_stops_for_human_review_without_fallback(pipeline):
    client, sandbox = FakeTeamSocLo([SERVICE_JSON, SERVICE_JSON]), FakeSandbox(fail_cases={"half-up-rounding"})
    _wire(pipeline, client, sandbox)
    codes = _codes(lambda: _llm_generate(pipeline))
    assert codes == {"HUMAN_REVIEW_REQUIRED"}
    assert len(client.requests) == 2  # attempt limit; the validation module was never started
    assert "BENCHMARK_CASE_FAILED[be.service] half-up-rounding" in client.requests[1].messages[1].content
    assert "CURRENT_MODULE" in client.requests[1].messages[1].content  # attempt 2 sends the failed module back
    assert pipeline.list_runs() == []  # no artifact, so nothing a template fallback could have produced
    assert pipeline.store.latest(graph_id_for("PROJECT-GPA-HYBRID-001")) is None  # nothing was accepted into the trace graph
    record = json.loads(next((pipeline.root / "gpa-hybrid" / "_human-review").glob("review-*.json")).read_text(encoding="utf-8"))
    assert record["template_fallback"] == "NOT_APPLIED" and record["artifact_created"] is False
    failure = record["failures"][0]
    assert failure["module_id"] == "be.service" and len(failure["rejected_outputs"]) == 2 and len(failure["ledger"]) == 2
    assert all("BENCHMARK_CASE_FAILED" in entry["validation_result"] for entry in failure["ledger"])


def test_missing_docker_or_teamsoclo_stops_before_any_model_call(pipeline):
    client = FakeTeamSocLo([SERVICE_JSON, VALIDATION_JSON])
    _wire(pipeline, client, FakeSandbox(docker_ok=False))
    assert _codes(lambda: _llm_generate(pipeline)) == {"HUMAN_REVIEW_REQUIRED"}
    assert client.requests == []
    record = json.loads(next((pipeline.root / "gpa-hybrid" / "_human-review").glob("review-*.json")).read_text(encoding="utf-8"))
    assert record["reasons"][0].startswith("SANDBOX_UNAVAILABLE")
    pipeline.backend_llm = BackendLlm("teamsoclo", "claude-haiku-4-5", lambda: None)  # gate off / no key
    assert _codes(lambda: _llm_generate(pipeline)) == {"HUMAN_REVIEW_REQUIRED"}
    # Two records can share a timestamp second, so identify them by content, never by file order.
    reviews = list((pipeline.root / "gpa-hybrid" / "_human-review").glob("review-*.json"))
    reasons = sorted(json.loads(path.read_text(encoding="utf-8"))["reasons"][0].split(":")[0] for path in reviews)
    assert reasons == ["SANDBOX_UNAVAILABLE", "TEAMSOCLO_UNAVAILABLE"]


def test_scoped_regeneration_never_silently_replaces_model_written_modules(pipeline):
    client, sandbox = FakeTeamSocLo([SERVICE_JSON, VALIDATION_JSON]), FakeSandbox()
    _wire(pipeline, client, sandbox)
    run = _llm_generate(pipeline)
    change = RequirementChangeRequest.model_validate({
        "base_generation_run_id": run["generation_run_id"], "package": _package("gpa_input_package_req103_v2.json"),
        "policy_acceptance": _acceptance(pipeline)})
    assert "LLM_MODULE_IMPACTED_REQUIRES_REVIEW" in _codes(lambda: asyncio.run(pipeline.requirement_change(change)))
    defect = pipeline.simulated_defect(run["generation_run_id"])["submission"]
    from intelise_c3.contracts.hybrid import C4DefectSubmission

    assert "MODEL_MODULE_REPAIR_REQUIRES_REVIEW" in _codes(
        lambda: asyncio.run(pipeline.c4_defect(C4DefectSubmission.model_validate(defect))))
    assert pipeline.run_report(run["generation_run_id"])["evidence"]["integrity_problems"] == []


def test_the_default_run_never_calls_a_model(pipeline):
    pipeline.backend_llm = BackendLlm("teamsoclo", "m", lambda: pytest.fail("TeamSocLo must not be called without the explicit opt-in"))
    pipeline._client_factory = lambda: pytest.fail("OpenRouter must not be called without the explicit opt-in")
    run = _generate(pipeline)
    assert run["manifest"]["generation_mode"] == "TEMPLATE" and run["manifest"]["llm"]["calls"] == 0
    assert run["manifest"]["llm"]["provider"].startswith("NONE")


@pytest.mark.skipif(shutil.which("docker") is None or not docker_available()[0], reason="Docker is not available")
def test_template_modules_pass_the_shared_benchmarks_in_the_real_sandbox(pipeline):
    """Control experiment: the template modules must pass the very cases an LLM module is held to."""
    run = _generate(pipeline)
    run_dir, manifest = pipeline.find_run(run["generation_run_id"])
    files = pipeline._read_project_files(run_dir, manifest)
    package = HybridInputPackage.model_validate(_package())
    spec = build_gpa_spec(package, HybridContractValidator().validate(package).design_context, load_knowledge_base())
    service = run_sandbox(subprocess.run, {"src/errors.js": files["backend/src/errors.js"],
                                           "src/services/gpaCalculationService.js": files["backend/src/services/gpaCalculationService.js"]},
                          service_spec(spec, "src/services/gpaCalculationService.js"))
    validation = run_sandbox(subprocess.run, {"src/validation/gpaRequestValidator.js": files["backend/src/validation/gpaRequestValidator.js"]},
                             validation_spec(spec, "src/validation/gpaRequestValidator.js"))
    for outcome in (service, validation):
        assert outcome["executed"], outcome.get("reason")
        assert outcome["passed"] == outcome["total"], [r for r in outcome["results"] if not r["passed"]]
