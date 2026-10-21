"""Docker-sandboxed behaviour benchmarks for LLM-written backend modules.

The same benchmark cases are used in three places so they cannot drift apart:

* the pipeline gate (an LLM module is accepted only if it passes inside the sandbox),
* the OpenRouter trial (LLM module vs template module, side by side),
* the generated project's own smoke test (``backend/test/gpa.smoke.test.js``), which the Docker
  preview build runs again against the files that are actually shipped.

Candidate source never runs on the host. It is piped over stdin into a disposable container with no
network, a read-only root filesystem, tmpfs only, no mounts, a non-root user and all capabilities dropped.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import subprocess
from typing import Any

from intelise_c3.hybrid.gpa_spec import GpaSpec

BENCHMARK_VERSION = "gpa-backend-bench-2"
SANDBOX_IMAGE = "node:24-bookworm-slim"
SANDBOX_TIMEOUT_SECONDS = 90

_A = lambda code, credits, grade, counts=True: {"moduleCode": code, "credits": credits, "grade": grade, "countsTowardGpa": counts}  # noqa: E731

#: GpaCalculationService cases. Expected values are worked out by hand from KB-GPA-FORMULA / ROUNDING / edge-case items.
CASES: list[dict[str, Any]] = [
    # (4*4.0 + 3*3.3 + 2*2.0 + 3*3.7) / 12 = 41.0 / 12 = 3.4166 -> 3.42
    {"id": "known-benchmark", "modules": [_A("IT1010", 4, "A"), _A("IT1020", 3, "B+"), _A("IT1030", 2, "C"), _A("IT1040", 3, "A-")],
     "expect": {"gpaText": "3.42", "totalCredits": 12}},
    # (11*3.3 + 5*3.7) / 16 = 54.8 / 16 = 3.425 exactly -> HALF_UP 3.43 (truncation or banker's rounding would give 3.42)
    {"id": "half-up-rounding", "modules": [_A("IT1050", 11, "B+"), _A("IT1060", 5, "A-")],
     "expect": {"gpaText": "3.43", "totalCredits": 16}},
    # non-GPA module excluded from both sums: 4*4.0 / 4 = 4.00
    {"id": "non-gpa-excluded", "modules": [_A("IT1010", 4, "A"), _A("IT1070", 2, "E", False)],
     "expect": {"gpaText": "4.00", "totalCredits": 4, "resultModules": 2}},
    # an unknown grade is never guessed, even on a module that does not count toward GPA
    {"id": "unknown-grade-on-non-gpa-module", "modules": [_A("IT1010", 4, "A"), _A("IT1070", 2, "Z", False)],
     "expect": {"throws": "UNKNOWN_GRADE"}},
    {"id": "unknown-grade-review", "modules": [_A("IT1010", 3, "Z")], "expect": {"throws": "UNKNOWN_GRADE"}},
    {"id": "repeated-module-review", "modules": [_A("IT1010", 3, "A"), _A("it1010", 3, "B")],
     "expect": {"throws": "REPEATED_MODULE_POLICY_UNDEFINED"}},
    {"id": "no-gpa-credits", "modules": [_A("IT1010", 3, "A", False)], "expect": {"throws": "NO_GPA_CREDITS"}},
    {"id": "zero-credit-rejected", "modules": [_A("IT1010", 0, "A")], "expect": {"throws": "ZERO_CREDIT_NOT_ALLOWED"}},
    {"id": "history-via-repository", "kind": "history", "modules": [_A("IT1010", 4, "A")], "expect": {"gpaText": "4.00"}},
]


def validation_cases(spec: GpaSpec) -> list[dict[str, Any]]:
    """validateGpaRequest cases whose limits come from the approved C1 constraints (+ KB defaults)."""
    credits = spec.constraint("ModuleResult.credits")
    code = spec.constraint("ModuleResult.moduleCode")
    ok = lambda module_code, credit, grade, **extra: {"moduleCode": module_code, "credits": credit, "grade": grade, **extra}  # noqa: E731
    cases: list[dict[str, Any]] = [
        {"id": "valid-request", "body": {"modules": [ok("IT1010", 4, "A"), ok("IT1020", 3, "B", countsTowardGpa=False)]},
         "expect": {"errors": [], "review": [], "modules": 2}},
        {"id": "empty-modules", "body": {"modules": []}, "expect": {"errors": ["MODULES_REQUIRED"], "review": []}},
        {"id": "modules-not-an-array", "body": {"modules": "IT1010"}, "expect": {"errors": ["MODULES_REQUIRED"], "review": []}},
        {"id": "too-many-modules", "body": {"modules": [ok(f"IT{1000 + i}", 3, "A") for i in range(spec.max_modules + 1)]},
         "expect": {"errors": ["TOO_MANY_MODULES"], "review": []}},
        {"id": "missing-module-code", "body": {"modules": [{"credits": 3, "grade": "A"}]},
         "expect": {"errors": ["MODULE_CODE_REQUIRED"], "review": []}},
        {"id": "credits-above-maximum", "body": {"modules": [ok("IT1010", credits.maximum + 1, "A")]},
         "expect": {"errors": ["CREDITS_OUT_OF_RANGE"], "review": []}},
        {"id": "fractional-credits", "body": {"modules": [ok("IT1010", 2.5, "A")]},
         "expect": {"errors": ["CREDITS_OUT_OF_RANGE"], "review": []}},
        {"id": "zero-credits", "body": {"modules": [ok("IT1010", 0, "A")]},
         "expect": {"errors": ["ZERO_CREDIT_NOT_ALLOWED"], "review": []}},
        {"id": "missing-grade", "body": {"modules": [{"moduleCode": "IT1010", "credits": 3}]},
         "expect": {"errors": ["GRADE_REQUIRED"], "review": []}},
        {"id": "unknown-grade-is-review-not-error", "body": {"modules": [ok("IT1010", 3, "Z")]},
         "expect": {"errors": [], "review": ["UNKNOWN_GRADE"]}},
        {"id": "repeated-module-is-review", "body": {"modules": [ok("IT1010", 3, "A"), ok("IT1010", 3, "B")]},
         "expect": {"errors": [], "review": ["REPEATED_MODULE_POLICY_UNDEFINED"]}},
        {"id": "counts-flag-must-be-boolean", "body": {"modules": [ok("IT1010", 3, "A", countsTowardGpa="yes")]},
         "expect": {"errors": ["COUNTS_TOWARD_GPA_BOOLEAN"], "review": []}},
    ]
    if code.max_length:
        cases.append({"id": "module-code-too-long", "body": {"modules": [ok("X" * (code.max_length + 1), 3, "A")]},
                      "expect": {"errors": ["MODULE_CODE_TOO_LONG"], "review": []}})
    if code.pattern:
        cases.append({"id": "module-code-pattern", "body": {"modules": [ok("bad code!", 3, "A")]},
                      "expect": {"errors": ["MODULE_CODE_PATTERN"], "review": []}})
    return cases


def _policy_parts(spec: GpaSpec) -> dict[str, Any]:
    policy = spec.policy
    return {
        "gradeTenths": {g.grade: g.grade_point_tenths for g in policy.grades},
        "metadata": {"policyId": policy.policy_id, "policyVersion": policy.policy_version, "authorityStatus": policy.authority_status},
    }


def service_spec(spec: GpaSpec, entry: str) -> dict[str, Any]:
    return {"kind": "service", "entry": entry, "cases": CASES, **_policy_parts(spec)}


def validation_spec(spec: GpaSpec, entry: str) -> dict[str, Any]:
    return {"kind": "validation", "entry": entry, "cases": validation_cases(spec), **_policy_parts(spec)}


#: Shared runner (ESM). Used by the sandbox harness AND copied into the generated project's test folder.
BENCH_RUNNER_MJS = """
// Benchmark runner generated by InteliSE Component 3 (gpa-backend-bench-1). SMOKE CHECKS, not Component 4 tests.
export function makePolicy(spec) {
  const has = (grade) => Object.prototype.hasOwnProperty.call(spec.gradeTenths, grade);
  return {
    gradePointTenths: (grade) => (has(grade) ? spec.gradeTenths[grade] : null),
    gradePoint: (grade) => (has(grade) ? spec.gradeTenths[grade] / 10 : null),
    metadata: () => spec.metadata,
  };
}

function makeRepo() {
  const items = [];
  return {
    saves: 0,
    // Mirrors the PostgreSQL table: every persisted module line needs all of these, with the right types.
    async save(calculation) {
      const lines = calculation && calculation.modules;
      if (!Array.isArray(lines) || lines.length === 0) throw new Error('repository rejected the calculation: modules[] is required');
      lines.forEach((line, i) => {
        const bad = typeof line.moduleCode !== 'string' || !Number.isInteger(line.credits) || typeof line.grade !== 'string'
          || typeof line.gradePoint !== 'number' || typeof line.countsTowardGpa !== 'boolean';
        if (bad) throw new Error('repository rejected modules[' + i + ']: needs moduleCode, integer credits, grade, numeric gradePoint and boolean countsTowardGpa');
      });
      this.saves += 1;
      items.push(structuredClone(calculation));
      return structuredClone(calculation);
    },
    async list() { return items.map((item) => structuredClone(item)); },
  };
}

const matchesThrow = (error, code) => Boolean(error) && (error.code === code || (Array.isArray(error.details) && error.details.some((d) => d && d.code === code)));

export async function runServiceCases(Service, spec) {
  const policy = makePolicy(spec);
  const results = [];
  for (const c of spec.cases) {
    const repository = makeRepo();
    let passed = false;
    let observed = '';
    try {
      const service = new Service({ repository, gradingPolicy: policy, clock: () => new Date('2026-01-01T00:00:00.000Z'), idGenerator: () => 'id-1' });
      if (c.kind === 'history') {
        const r = await service.calculate(c.modules);
        const h = await service.listHistory();
        passed = r.gpaText === c.expect.gpaText && Array.isArray(h) && h.length === 1 && h[0].gpaText === c.expect.gpaText && repository.saves === 1;
        observed = 'result=' + r.gpaText + ', history=' + (Array.isArray(h) ? h.length : typeof h) + ', saves=' + repository.saves;
      } else if (c.expect.throws) {
        try {
          const r = await service.calculate(c.modules);
          observed = 'returned ' + (r && r.gpaText);
        } catch (error) {
          passed = matchesThrow(error, c.expect.throws);
          observed = 'threw ' + (error && error.code);
        }
      } else {
        const r = await service.calculate(c.modules);
        passed = r.gpaText === c.expect.gpaText && r.totalCredits === c.expect.totalCredits;
        observed = 'gpaText=' + r.gpaText + ', totalCredits=' + r.totalCredits;
        if (c.expect.resultModules !== undefined) {
          const count = Array.isArray(r.modules) ? r.modules.length : -1;
          passed = passed && count === c.expect.resultModules;
          observed += ', result.modules=' + count;
        }
      }
    } catch (error) {
      observed = 'error: ' + (error && error.message);
    }
    results.push({ id: c.id, passed, observed });
  }
  return results;
}

export async function runValidationCases(validate, spec) {
  const policy = makePolicy(spec);
  const codes = (list) => (Array.isArray(list) ? list.map((item) => item && item.code) : null);
  const results = [];
  for (const c of spec.cases) {
    let passed = false;
    let observed = '';
    try {
      const out = await validate(structuredClone(c.body), policy);
      const errs = codes(out && out.errors);
      const rev = codes(out && out.review);
      if (!errs || !rev) {
        observed = 'the result needs errors[] and review[] arrays';
      } else {
        const wantErr = c.expect.errors;
        const wantRev = c.expect.review;
        const okErr = wantErr.every((x) => errs.includes(x)) && (wantErr.length > 0 || errs.length === 0);
        const okRev = wantRev.every((x) => rev.includes(x)) && (wantRev.length > 0 || rev.length === 0);
        let okValue = true;
        if (c.expect.modules !== undefined) {
          const m = out.value && out.value.modules;
          okValue = Array.isArray(m) && m.length === c.expect.modules
            && m.every((x) => typeof x.moduleCode === 'string' && typeof x.credits === 'number' && typeof x.grade === 'string' && typeof x.countsTowardGpa === 'boolean')
            && m[0].countsTowardGpa === true && m[1].countsTowardGpa === false;
        }
        passed = okErr && okRev && okValue;
        observed = 'errors=' + JSON.stringify(errs) + ', review=' + JSON.stringify(rev) + (okValue ? '' : ', value.modules has the wrong shape');
      }
    } catch (error) {
      observed = 'error: ' + (error && error.message);
    }
    results.push({ id: c.id, passed, observed });
  }
  return results;
}
"""

HARNESS_MJS = """
import fs from 'node:fs';
import { runServiceCases, runValidationCases } from './bench-runner.mjs';
const spec = JSON.parse(fs.readFileSync('/tmp/w/cases.json', 'utf8'));
const mod = await import('file:///tmp/w/' + spec.entry);
const results = spec.kind === 'validation'
  ? await runValidationCases(mod.validateGpaRequest, spec)
  : await runServiceCases(mod.GpaCalculationService, spec);
console.log('RESULTS ' + JSON.stringify(results));
"""

BOOTSTRAP_JS = (
    "let d='';process.stdin.setEncoding('utf8');process.stdin.on('data',c=>{d+=c}).on('end',async()=>{"
    "try{const p=JSON.parse(d);const fs=require('fs'),path=require('path');"
    "for(const [f,c] of Object.entries(p.files)){const t=path.join('/tmp/w',f);fs.mkdirSync(path.dirname(t),{recursive:true});fs.writeFileSync(t,c);}"
    "await import('file:///tmp/w/harness.mjs');}catch(e){console.error('HARNESS_ERROR '+e.message);process.exit(2);}});"
)

Runner = Callable[..., subprocess.CompletedProcess]


def docker_available(runner: Runner = subprocess.run) -> tuple[bool, str]:
    try:
        result = runner(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return False, "the docker CLI was not found"
    except subprocess.TimeoutExpired:
        return False, "docker did not answer within 20 s"
    if result.returncode != 0:
        return False, ((result.stderr or "docker daemon unreachable").strip()[-200:])
    return True, result.stdout.strip()


def run_sandbox(runner: Runner, files: dict[str, str], spec: dict[str, Any]) -> dict[str, Any]:
    """Execute one benchmark spec against ``files`` inside the locked-down container."""
    payload = {"files": {**files, "harness.mjs": HARNESS_MJS, "bench-runner.mjs": BENCH_RUNNER_MJS, "cases.json": json.dumps(spec)}}
    command = [
        "docker", "run", "--rm", "-i", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,nosuid,mode=1777",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--user", "1000:1000", "--memory", "128m",
        "--pids-limit", "64", "--cpus", "0.5", SANDBOX_IMAGE, "node", "-e", BOOTSTRAP_JS,
    ]
    try:
        result = runner(command, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
                        timeout=SANDBOX_TIMEOUT_SECONDS)
    except FileNotFoundError:
        return {"executed": False, "reason": "DOCKER_UNAVAILABLE: docker CLI not found"}
    except subprocess.TimeoutExpired:
        return {"executed": False, "reason": f"SANDBOX_TIMEOUT: exceeded {SANDBOX_TIMEOUT_SECONDS}s (the module may loop forever)"}
    line = next((entry for entry in (result.stdout or "").splitlines() if entry.startswith("RESULTS ")), None)
    if result.returncode != 0 or line is None:
        tail = ((result.stderr or "") + (result.stdout or "")).strip().splitlines()[-4:]
        return {"executed": False, "reason": f"SANDBOX_FAILED (exit {result.returncode}): {' | '.join(tail)}"}
    results = json.loads(line[len("RESULTS "):])
    return {"executed": True, "results": results, "passed": sum(r["passed"] for r in results), "total": len(results)}


def failures_as_findings(outcome: dict[str, Any], label: str) -> list[str]:
    """Exact, model-text-free findings for a repair attempt (or [] when every case passed)."""
    if not outcome["executed"]:
        return [f"SANDBOX_NOT_EXECUTED: {outcome['reason']}"]
    return [f"BENCHMARK_CASE_FAILED[{label}] {r['id']}: {r['observed']}" for r in outcome["results"] if not r["passed"]]
