import asyncio
import json

import pytest

from app.services.agent_testing_service import TestCoordinationService
from app.services.docker_runner import DockerTestRunner
from app.services.test_classification import classify_project_tests, integration_boundary_evidence


def _categorized_project():
    unit_test = "from app.math_ops import add\ndef test_add(): assert add(2, 3) == 5\n"
    return unit_test, {
        "fixture/app/__init__.py": "",
        "fixture/app/math_ops.py": "def add(a, b): return a + b\n",
        "fixture/app/service.py": "from app.math_ops import add\ndef total(a, b): return add(a, b)\n",
        "fixture/tests/test_math.py": unit_test,
        "fixture/tests/test_integration.py": (
            "from app.math_ops import add\n"
            "from app.service import total\n"
            "def test_service_boundary(): assert total(2, 3) == add(2, 3) == 5\n"
        ),
        "fixture/tests/test_performance.py": (
            "import time\n"
            "from app.math_ops import add\n"
            "def test_measured_addition_workload():\n"
            "    samples_ms = []\n"
            "    for _ in range(5):\n"
            "        start = time.perf_counter_ns()\n"
            "        assert add(2, 3) == 5\n"
            "        samples_ms.append((time.perf_counter_ns() - start) / 1_000_000)\n"
            "    ordered = sorted(samples_ms)\n"
            "    mean_ms = sum(samples_ms) / len(samples_ms)\n"
            "    p95_ms = ordered[-1]\n"
            "    print(f'INTELISE_PERFORMANCE sample_count={len(samples_ms)} p95_ms={p95_ms:.6f} mean_ms={mean_ms:.6f} threshold_ms=200.0', flush=True)\n"
            "    assert p95_ms <= 200.0\n"
        ),
    }


def test_reserved_paths_are_mutually_exclusive_and_unclassified_tests_remain_unit():
    _test_code, files = _categorized_project()
    classification = classify_project_tests(files)

    assert classification.errors == []
    assert classification.paths_for("unit") == ["fixture/tests/test_math.py"]
    assert classification.paths_for("integration") == ["fixture/tests/test_integration.py"]
    assert classification.paths_for("performance") == ["fixture/tests/test_performance.py"]
    assert len(classification.assignments) == len(set(classification.assignments)) == 3


def test_syntax_only_imports_do_not_authorize_an_integration_suite():
    files = {
        "app/alpha.py": "def alpha(): return 1\n",
        "app/beta.py": "def beta(): return 2\n",
        "tests/test_integration.py": (
            "import app.alpha\n"
            "import app.beta\n\n"
            "def test_sources_compile():\n"
            "    compile('x = 1', '<test>', 'exec')\n"
        ),
    }
    classification = classify_project_tests(files)

    authorized, evidence = integration_boundary_evidence(files, classification.paths_for("integration"))
    assert authorized is False
    assert evidence == []


def test_arbitrary_test_function_names_do_not_authorize_categories():
    files = {
        "app.py": "def value(): return 1\n",
        "tests/test_misc.py": (
            "def test_integration_by_name_only(): assert True\n"
            "def test_performance_by_name_only(): assert True\n"
        ),
    }
    classification = classify_project_tests(files)

    assert classification.has_explicit_metadata is False
    assert classification.paths_for("unit") == ["tests/test_misc.py"]
    assert classification.paths_for("integration") == []
    assert classification.paths_for("performance") == []


def test_pytest_module_marker_and_valid_manifest_are_supported():
    marked = {
        "src/pkg.py": "def value(): return 1\n",
        "tests/check_boundary.py": "import pytest\npytestmark = pytest.mark.integration\ndef test_boundary(): assert True\n",
    }
    marked_result = classify_project_tests(marked)
    assert marked_result.paths_for("integration") == ["tests/check_boundary.py"]

    manifested = {
        "pkg.py": "def value(): return 1\n",
        "checks/workload.py": "def test_value(): assert True\n",
        "intelise-test-manifest.json": json.dumps({
            "version": 1,
            "tests": [{"path": "checks/workload.py", "category": "performance", "threshold_ms": 250}],
        }),
    }
    manifest_result = classify_project_tests(manifested)
    assert manifest_result.paths_for("performance") == ["checks/workload.py"]
    assert manifest_result.performance_thresholds_ms["checks/workload.py"] == 250.0


@pytest.mark.parametrize(
    "manifest",
    [
        {"version": 2, "tests": []},
        {"version": 1, "tests": [{"path": "tests/test_x.py", "category": "load"}]},
        {"version": 1, "tests": [
            {"path": "tests/test_x.py", "category": "unit"},
            {"path": "tests/test_x.py", "category": "performance"},
        ]},
    ],
)
def test_invalid_manifest_is_rejected(manifest):
    result = classify_project_tests({
        "app.py": "def value(): return 1\n",
        "tests/test_x.py": "def test_value(): assert True\n",
        "intelise-tests.json": json.dumps(manifest),
    })
    assert result.errors
    assert result.assignments == {}


@pytest.mark.anyio
async def test_unsupported_performance_workload_is_not_executed():
    files = {
        "fixture/app.py": "def value(): return 1\n",
        "fixture/tests/test_performance.py": "def test_fast(): assert True\n",
    }
    service = TestCoordinationService(runner=DockerTestRunner())
    plan = service.create_coordination_plan("run-unsupported", "def value(): return 1", ["performance"])

    result = await service.execute_coordinated_verification(
        plan=plan,
        source_code="def value(): return 1",
        test_code="",
        project_files=files,
    )

    report = result["agent_reports"]["performance"]
    assert report.status == "NOT_EXECUTED"
    assert report.pipeline_sla_status == "NOT_EVALUATED"
    assert "timing API" in report.authorization_reason
    assert report.test_results == []


def test_real_docker_execution_classifies_each_embedded_test_once():
    unit_test, files = _categorized_project()
    service = TestCoordinationService(runner=DockerTestRunner())
    plan = service.create_coordination_plan(
        "run-categorized-regression",
        files["fixture/app/math_ops.py"],
        ["unit", "integration", "performance"],
        latency_threshold_ms=200.0,
    )

    result = asyncio.run(service.execute_coordinated_verification(
        plan=plan,
        source_code=files["fixture/app/math_ops.py"],
        test_code=unit_test,
        filename="fixture.zip",
        project_files=files,
    ))

    unit = result["agent_reports"]["unit"]
    integration = result["agent_reports"]["integration"]
    performance = result["agent_reports"]["performance"]
    assert result["overall_status"] == "PASSED"
    assert (unit.total_tests, unit.passed_tests) == (1, 1)
    assert (integration.total_interactions, integration.passed_interactions) == (1, 1)
    assert performance.status == "PASSED"
    assert performance.embedded_assertion_status == "PASSED"
    assert performance.pipeline_sla_status == "PASSED"
    assert performance.metrics.sample_size == 5
    assert performance.metrics.latency_p95_ms >= 0
    assert performance.metrics.threshold_latency_ms == 200.0

    embedded_names = [item.name for item in result["test_results"]]
    assert sorted(embedded_names) == ["test_add", "test_measured_addition_workload", "test_service_boundary"]
    assert len(embedded_names) == len(set(embedded_names))
    assert len(result["test_results"]) == 3
