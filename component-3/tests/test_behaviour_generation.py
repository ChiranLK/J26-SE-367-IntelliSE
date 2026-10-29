"""Behaviour (non-CRUD) generator, Stage 0: spec, validation, probe, service and app runner."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import urllib.request

import pytest

from intelise_c3.contracts.behaviour import BehaviourGenerationRequest
from intelise_c3.contracts.generation import GenerationMode, ProvisionalApprovalStatus, ProvisionalStackApproval
from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.contracts.stack_selection import StackSelectionRequest
from intelise_c3.core.errors import ApplicationError, ErrorDetail
from intelise_c3.domain.llm import (
    LLMGenerationParameters,
    LLMInferenceMetadata,
    LLMInferenceResponse,
    OllamaResponseMetadata,
)
from intelise_c3.generation.behaviour_spec import build_behaviour_spec, render_domain_skeleton
from intelise_c3.generation.behaviour_validation import (
    extract_class_block,
    run_behaviour_probe,
    validate_domain_module,
)
from intelise_c3.generation.js_safety import inspect_javascript_safety
from intelise_c3.scripts.generate_task_mvp import build_simulated_stack_criteria
from intelise_c3.services.behaviour_apps import BehaviourAppRunner
from intelise_c3.services.behaviour_generation import BehaviourGenerationService
from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService
from intelise_c3.services.stack_selection import StackSelectionService

FIXTURE = Path(__file__).parent / "fixtures" / "simulated" / "calculator_behaviour_input_package.json"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node.js is required for the probe and runner")

LEAVES = {
    "Addition": "export class Addition extends Operation {\n  constructor() {\n    super();\n  }\n\n  calculate(firstNumber, secondNumber) {\n    return firstNumber + secondNumber;\n  }\n}\n",
    "Subtraction": "export class Subtraction extends Operation {\n  constructor() {\n    super();\n  }\n\n  calculate(firstNumber, secondNumber) {\n    return firstNumber - secondNumber;\n  }\n}\n",
    "Multiplication": "export class Multiplication extends Operation {\n  constructor() {\n    super();\n  }\n\n  calculate(firstNumber, secondNumber) {\n    return firstNumber * secondNumber;\n  }\n}\n",
    "Division": "export class Division extends Operation {\n  constructor() {\n    super();\n  }\n\n  calculate(firstNumber, secondNumber) {\n    if (secondNumber === 0) {\n      throw new Error(\"Division by zero\");\n    }\n    return firstNumber / secondNumber;\n  }\n}\n",
    "Calculation": "export class Calculation {\n  constructor() {\n    this.firstNumber = 0;\n    this.secondNumber = 0;\n    this.result = 0;\n    this.status = \"\";\n    this.operation = null;\n  }\n\n  calculate() {\n    this.result = this.operation.calculate(this.firstNumber, this.secondNumber);\n    this.status = CalculationStatus.SUCCESS;\n  }\n}\n",
    "History": "export class History {\n  constructor() {\n    this.totalCount = 0;\n    this.calculations = [];\n  }\n\n  addCalculation(calculation) {\n    this.calculations.push(calculation);\n    this.totalCount = this.calculations.length;\n  }\n}\n",
}
GOOD_FACADE = """export class Calculator {
  constructor() {
    this.displayValue = 0;
    this.history = new History();
    this.firstNumber = 0;
    this.operation = null;
  }

  enterNumber(number) {
    this.displayValue = number;
  }

  selectOperation(operation) {
    this.firstNumber = this.displayValue;
    this.operation = operation;
  }

  calculateResult() {
    const calculation = new Calculation();
    calculation.firstNumber = this.firstNumber;
    calculation.secondNumber = this.displayValue;
    calculation.operation = this.operation;
    calculation.calculate();
    this.history.addCalculation(calculation);
    this.displayValue = calculation.result;
  }

  clearHistory() {
    this.history = new History();
  }
}
"""
# Ignores the first operand: runs cleanly but the metamorphic check must flag it.
IGNORING_FACADE = GOOD_FACADE.replace("calculation.firstNumber = this.firstNumber;", "calculation.firstNumber = this.displayValue;")
UNSAFE_FACADE = GOOD_FACADE.replace("this.displayValue = number;", "this.displayValue = require(\"x\");")


@pytest.fixture(scope="module")
def request_model() -> BehaviourGenerationRequest:
    package = ProvisionalInputPackage.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
    context = InputValidationService().validate(package)
    design = DesignUnderstandingService().build(context)
    report = StackSelectionService().select(
        StackSelectionRequest(design_context=design, criteria=build_simulated_stack_criteria())
    )
    return BehaviourGenerationRequest(
        generation_context=context,
        design_context=design,
        stack_selection_report=report,
        stack_approval=ProvisionalStackApproval(
            status=ProvisionalApprovalStatus.APPROVED_FOR_MVP_GENERATION,
            approval_reference="SIMULATED-BEHAVIOUR-TEST-APPROVAL",
            approved_by="LOCAL-RESEARCHER-TEST",
            acknowledges_provisional_policy=True,
        ),
        mode=GenerationMode.LOCAL_LLM,
        workspace_name="calc-behaviour-test",
    )


def _module(spec, facade: str = GOOD_FACADE) -> str:
    from intelise_c3.generation.behaviour_spec import assemble_module

    return assemble_module(spec, {**LEAVES, "Calculator": facade})


def test_the_crud_generator_still_refuses_this_design(request_model) -> None:
    with pytest.raises(ApplicationError) as error:
        CrudApplicationSpecBuilder().build(request_model.design_context)
    assert error.value.errors[0].code == "UNSUPPORTED_CRUD_CLASS_KIND"


def test_spec_derives_structure_facade_and_plan_from_uml(request_model) -> None:
    spec = build_behaviour_spec(request_model.design_context)
    names = [item.name for item in spec.classes]
    assert spec.facade == "Calculator"
    assert names.index("CalculationStatus") == 0  # enums first
    assert names.index("Operation") < names.index("Addition")  # bases before subclasses
    by_name = spec.by_name()
    assert by_name["Addition"].base == "Operation"
    assert {f.name for f in by_name["Calculation"].fields} >= {"operation", "firstNumber"}
    assert any(f.name == "calculations" and f.kind == "ARRAY" for f in by_name["History"].fields)
    assert spec.concrete_subtypes("Operation") == ("Addition", "Subtraction", "Multiplication", "Division")
    anchored = {a["class_name"] for a in spec.anchors}
    assert anchored == {"Addition", "Subtraction", "Multiplication", "Division", "Calculator"}
    assert [step["method"] for step in spec.probe_plan()] == [
        "enterNumber", "selectOperation", "enterNumber", "calculateResult", "enterNumber", "clearHistory",
    ]


def test_skeleton_is_policy_clean_and_only_missing_implementations(request_model) -> None:
    spec = build_behaviour_spec(request_model.design_context)
    skeleton = render_domain_skeleton(spec)
    assert inspect_javascript_safety(skeleton).accepted
    codes = [f.code for f in validate_domain_module(skeleton, spec).findings]
    assert codes == ["UNIMPLEMENTED_METHOD"]


def test_validator_accepts_a_complete_module_and_rejects_unsafe_or_changed_ones(request_model) -> None:
    spec = build_behaviour_spec(request_model.design_context)
    assert validate_domain_module(_module(spec), spec).accepted
    unsafe = validate_domain_module(_module(spec, UNSAFE_FACADE), spec)
    assert "UNSAFE_GENERATED_CONTENT" in [f.code for f in unsafe.findings]
    renamed = validate_domain_module(_module(spec, GOOD_FACADE.replace("enterNumber(number)", "enterNumber(value)")), spec)
    assert "MISSING_METHOD" in [f.code for f in renamed.findings]


def test_class_extraction_ignores_extra_text_and_restores_export() -> None:
    answer = "```js\nclass Addition extends Operation {\n  calculate(a, b) { return a + b; }\n}\nconsole.log(1);\n```"
    assert extract_class_block(answer, "Addition").startswith("export class Addition extends Operation {")
    assert "console" not in extract_class_block(answer, "Addition")


@needs_node
def test_probe_passes_a_working_module_and_flags_an_ignored_input(request_model) -> None:
    spec = build_behaviour_spec(request_model.design_context)
    spec_json = json.dumps(spec.as_json())
    good = run_behaviour_probe(_module(spec), spec_json)
    assert good.status == "PASSED"
    assert good.steps[3]["state"]["displayValue"] == 17  # 12 + 5, observed (not asserted by the probe)
    ignoring = run_behaviour_probe(_module(spec, IGNORING_FACADE), spec_json)
    assert ignoring.status == "WARNINGS"
    assert ignoring.warnings[0].code == "PROBE_INPUT_IGNORED"
    broken = run_behaviour_probe(_module(spec, GOOD_FACADE.replace("this.displayValue = calculation.result;", "this.displayValue = calculation.missing;")), spec_json)
    assert broken.status == "FAILED"
    assert broken.findings[0].code == "PROBE_INVALID_FIELD"


class ScriptedClient:
    """Returns prepared class answers; the facade answers are consumed in order."""

    def __init__(self, facades: list[str]) -> None:
        self.facades = facades
        self.calls: list[tuple[str, float]] = []

    def factory(self, temperature: float):
        outer = self

        class _Client:
            async def generate(self, request):
                user = request.messages[-1].content
                unit = user.split("Implement the class `", 1)[1].split("`", 1)[0]
                outer.calls.append((unit, temperature))
                text = outer.facades.pop(0) if unit == "Calculator" else LEAVES[unit]
                return LLMInferenceResponse(
                    output_text=text,
                    metadata=LLMInferenceMetadata(
                        configured_model_identifier="qwen2.5-coder:3b",
                        response_model_identifier="qwen2.5-coder:3b",
                        prompt_template_version=request.prompt_template_version,
                        generation_parameters=LLMGenerationParameters(temperature=temperature, timeout_seconds=60),
                        client_inference_latency_ms=1.0,
                        response=OllamaResponseMetadata(created_at="2026-10-20T00:00:00Z", done=True, eval_count=10),
                    ),
                )

        return _Client()


@needs_node
@pytest.mark.anyio
async def test_service_repairs_the_facade_and_writes_an_evidenced_workspace(request_model, tmp_path) -> None:
    client = ScriptedClient([IGNORING_FACADE, GOOD_FACADE])
    result = await BehaviourGenerationService(tmp_path, client.factory).generate(request_model)
    manifest = result.manifest
    facade_attempts = [a for a in manifest.attempts if a.unit == "Calculator"]
    assert [a.verdict for a in facade_attempts] == ["REJECTED", "ACCEPTED"]
    assert facade_attempts[0].findings[0].code == "PROBE_INPUT_IGNORED"
    assert [a.temperature for a in facade_attempts] == [0.0, 0.3]
    assert manifest.probe.status == "PASSED"
    origins = {f.relative_path: f.origin.value for f in manifest.files}
    assert origins["backend/src/domain.mjs"] == "LOCAL_LLM"
    assert {p for p, o in origins.items() if o == "TEMPLATE"} >= {"backend/server.mjs", "backend/runtime.mjs", "frontend/src/App.jsx"}
    run_dir = tmp_path.joinpath(*result.workspace_relative_path.split("/"))
    assert (run_dir / "behaviour-manifest.json").is_file()
    assert client.calls[-1] == ("Calculator", 0.3)


@needs_node
@pytest.mark.anyio
async def test_service_writes_nothing_when_the_facade_is_never_acceptable(request_model, tmp_path) -> None:
    client = ScriptedClient([UNSAFE_FACADE] * 5)
    with pytest.raises(ApplicationError) as error:
        await BehaviourGenerationService(tmp_path, client.factory).generate(request_model)
    codes = [item.code for item in error.value.errors]
    assert codes[0] == "BEHAVIOUR_CLASS_REJECTED"
    assert "UNSAFE_GENERATED_CONTENT" in codes
    assert not (tmp_path / "behaviour").exists()


@pytest.mark.anyio
async def test_service_keeps_the_researcher_approval_gate(request_model, tmp_path) -> None:
    unapproved = request_model.model_copy(
        update={"stack_approval": request_model.stack_approval.model_copy(update={"acknowledges_provisional_policy": False})}
    )
    with pytest.raises(ApplicationError) as error:
        await BehaviourGenerationService(tmp_path, ScriptedClient([]).factory).generate(unapproved)
    assert error.value.errors[0].code == "STACK_APPROVAL_REQUIRED"


@needs_node
@pytest.mark.anyio
async def test_runner_starts_on_a_fresh_port_and_refuses_a_tampered_workspace(request_model, tmp_path) -> None:
    result = await BehaviourGenerationService(tmp_path, ScriptedClient([GOOD_FACADE]).factory).generate(request_model)
    runner = BehaviourAppRunner(tmp_path, tmp_path / "logs", build_frontend=False)  # the API is what is exercised here
    session = runner.start(result.workspace_relative_path)
    try:
        assert session.status == "RUNNING" and session.url.startswith("http://127.0.0.1:")

        def invoke(method, args):
            body = json.dumps({"method": method, "args": args}).encode()
            req = urllib.request.Request(f"{session.url}api/invoke", data=body, headers={"content-type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read())

        invoke("enterNumber", ["8"])
        invoke("selectOperation", ["Multiplication"])
        invoke("enterNumber", ["7"])
        assert invoke("calculateResult", [])["state"]["displayValue"] == 56
    finally:
        assert runner.stop(result.workspace_relative_path).status == "STOPPED"
    domain_file = tmp_path.joinpath(*result.workspace_relative_path.split("/"), "backend", "src", "domain.mjs")
    domain_file.write_text(domain_file.read_text(encoding="utf-8") + "\n// edited\n", encoding="utf-8")
    with pytest.raises(ApplicationError) as error:
        runner.start(result.workspace_relative_path)
    assert error.value.errors[0].code == "BEHAVIOUR_WORKSPACE_TAMPERED"


@needs_node
@pytest.mark.anyio
async def test_zip_matches_the_verified_workspace(request_model, tmp_path) -> None:
    import io
    import zipfile

    from intelise_c3.services import behaviour_export

    result = await BehaviourGenerationService(tmp_path, ScriptedClient([GOOD_FACADE]).factory).generate(request_model)
    run_dir, manifest = BehaviourAppRunner(tmp_path, tmp_path / "logs").workspace(result.workspace_relative_path)
    names = zipfile.ZipFile(io.BytesIO(behaviour_export.build_archive(run_dir, manifest, "demo"))).namelist()
    assert set(names) == {f"demo/{f.relative_path}" for f in manifest.files} | {"demo/behaviour-manifest.json"}


@needs_node
@pytest.mark.anyio
async def test_best_practice_rules_are_retrieved_per_class_and_recorded(request_model, tmp_path) -> None:
    from intelise_c3.core.config import COMPONENT_ROOT
    from intelise_c3.rag.best_practices import FilterBestPracticeStore, load_rule_cards
    from intelise_c3.rag.runtime import RagRuntime

    runtime = RagRuntime.for_test(FilterBestPracticeStore(load_rule_cards(COMPONENT_ROOT / "rules")))
    client = ScriptedClient([GOOD_FACADE])
    result = await BehaviourGenerationService(tmp_path, client.factory, rag_runtime=runtime).generate(request_model)
    evidence = result.manifest.rag_evidence
    assert evidence is not None and evidence.enabled
    assert {r.module_path.split("#")[1] for r in evidence.retrievals} >= {"Calculator"}
    assert all(r.applied_to_prompt and r.retrieved_rule_ids for r in evidence.retrievals)


@needs_node
@pytest.mark.anyio
async def test_openrouter_engine_is_recorded_as_such(request_model, tmp_path) -> None:
    openrouter_request = request_model.model_copy(update={"mode": GenerationMode.EXPERIMENTAL_OPENROUTER})
    result = await BehaviourGenerationService(tmp_path, ScriptedClient([GOOD_FACADE]).factory).generate(openrouter_request)
    manifest = result.manifest
    assert manifest.generation_mode == "EXPERIMENTAL_OPENROUTER"
    assert manifest.llm_provider == "openrouter"
    domain = next(f for f in manifest.files if f.relative_path == "backend/src/domain.mjs")
    assert domain.origin.value == "EXPERIMENTAL_OPENROUTER"


@needs_node
@pytest.mark.anyio
async def test_openrouter_batch_mode_generates_the_complete_module_in_one_call(request_model, tmp_path) -> None:
    spec = build_behaviour_spec(request_model.design_context)
    complete_module = _module(spec)
    calls = []

    def factory(temperature: float):
        class _Client:
            async def generate(self, request):
                calls.append((request.prompt_template_version, temperature))
                return LLMInferenceResponse(
                    output_text=complete_module,
                    metadata=LLMInferenceMetadata(
                        configured_model_identifier="openrouter/test-model",
                        response_model_identifier="openrouter/test-model",
                        prompt_template_version=request.prompt_template_version,
                        generation_parameters=LLMGenerationParameters(temperature=temperature, timeout_seconds=60),
                        client_inference_latency_ms=1.0,
                        response=OllamaResponseMetadata(created_at="2026-10-20T00:00:00Z", done=True, eval_count=100),
                    ),
                )

        return _Client()

    openrouter_request = request_model.model_copy(update={"mode": GenerationMode.EXPERIMENTAL_OPENROUTER})
    result = await BehaviourGenerationService(tmp_path, factory, batch_mode=True).generate(openrouter_request)

    assert calls == [("behaviour-domain-whole-module-v1", 0.0)]
    assert len(result.manifest.attempts) == 1
    assert result.manifest.attempts[0].unit == "COMPLETE_MODULE"
    assert result.manifest.probe.status == "PASSED"


@needs_node
@pytest.mark.anyio
async def test_teamsoclo_engine_is_recorded_as_such(request_model, tmp_path) -> None:
    claude_request = request_model.model_copy(update={"mode": GenerationMode.EXPERIMENTAL_CLAUDE})
    result = await BehaviourGenerationService(
        tmp_path,
        ScriptedClient([GOOD_FACADE]).factory,
        configured_model="claude-opus-5-5",
    ).generate(claude_request)
    assert result.manifest.generation_mode == "EXPERIMENTAL_CLAUDE"
    assert result.manifest.llm_provider == "teamsoclo-claude"
    domain = next(f for f in result.manifest.files if f.relative_path == "backend/src/domain.mjs")
    assert domain.origin.value == "EXPERIMENTAL_CLAUDE"


class EmptyOnceClient(ScriptedClient):
    """Raises the OpenRouter empty-content error on the first facade call, then answers normally."""

    def __init__(self, error_code: str, then: list[str]) -> None:
        super().__init__(then)
        self.error_code = error_code
        self.raised = False

    def factory(self, temperature: float):
        outer = self
        inner = super().factory(temperature)

        class _Client:
            async def generate(self, request):
                if "Implement the class `Calculator`" in request.messages[-1].content and not outer.raised:
                    outer.raised = True
                    raise ApplicationError(
                        [ErrorDetail(code=outer.error_code, field="openrouter", message="finish_reason=length, reasoning_tokens=4096")],
                        status_code=502,
                    )
                return await inner.generate(request)

        return _Client()


@needs_node
@pytest.mark.anyio
@pytest.mark.parametrize("code", ["OPENROUTER_EMPTY_CONTENT", "OPENROUTER_OUTPUT_TRUNCATED"])
async def test_an_empty_provider_answer_is_a_failed_attempt_not_a_failed_run(request_model, tmp_path, code) -> None:
    client = EmptyOnceClient(code, [GOOD_FACADE])
    result = await BehaviourGenerationService(tmp_path, client.factory, configured_model="cohere/north-mini-code:free").generate(request_model)
    facade = [a for a in result.manifest.attempts if a.unit == "Calculator"]
    assert [a.verdict for a in facade] == ["REJECTED", "ACCEPTED"]
    assert facade[0].findings[0].code == code
    assert facade[0].configured_model_identifier == "cohere/north-mini-code:free"
    assert facade[0].response_model_identifier == "(no usable answer)"


@pytest.mark.anyio
async def test_auth_and_credit_errors_still_stop_the_run_immediately(request_model, tmp_path) -> None:
    client = EmptyOnceClient("OPENROUTER_INSUFFICIENT_CREDITS", [GOOD_FACADE])
    with pytest.raises(ApplicationError) as error:
        await BehaviourGenerationService(tmp_path, client.factory).generate(request_model)
    assert error.value.errors[0].code == "OPENROUTER_INSUFFICIENT_CREDITS"
    assert not (tmp_path / "behaviour").exists()
