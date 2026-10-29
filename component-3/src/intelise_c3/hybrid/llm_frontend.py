"""LLM-written frontend (UI) generation with a real compile + behaviour gate.

Only the UI files are model-written. The trusted scaffold (package pins, index.html, vite config, main.jsx, the
API client that is the one module allowed to use the network, and the grade table) stays template-rendered.

Two independent file groups are generated **in parallel** (one bounded call each, so wall time is one call, not two):

* ``form``  - GpaCalculatorForm.jsx, ModuleRow.jsx, moduleValidation.js, form.css
* ``view``  - App.jsx, GpaResult.jsx, PolicyDisclosure.jsx, [HistoryList.jsx], styles.css

Acceptance is not the model's say-so: the union of the files must pass the frontend lexical policy, then a gate
image (``vite build`` + jsdom UI tests, run with no network, read-only root and no mounts) must build the project and pass
the benchmark cases. Failing cases go back, verbatim, to the group(s) that own them; at most two calls per group.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
import json
import subprocess
from typing import Any

from intelise_c3.hybrid.gpa_spec import GpaSpec
from intelise_c3.hybrid.gpa_templates import constraint_payload
from intelise_c3.hybrid.llm_gateway import BoundedModuleContext, OpenRouterModuleGateway

FRONTEND_GATE_VERSION = "gpa-ui-gate-1"
GATE_TIMEOUT_SECONDS = 300
GATE_BUILD_TIMEOUT_SECONDS = 900
TRUSTED_PATHS = ("frontend/src/api/gpaApi.js", "frontend/src/policy/gradingPolicy.js")
FORM_FILES = (
    "frontend/src/components/GpaCalculatorForm.jsx",
    "frontend/src/components/ModuleRow.jsx",
    "frontend/src/validation/moduleValidation.js",
    "frontend/src/components/form.css",
)


def view_files(spec: GpaSpec) -> tuple[str, ...]:
    files = ("frontend/src/App.jsx", "frontend/src/styles.css", "frontend/src/components/GpaResult.jsx",
             "frontend/src/components/PolicyDisclosure.jsx")
    return files + (("frontend/src/components/HistoryList.jsx",) if spec.persistence_required else ())


def group_files(spec: GpaSpec) -> dict[str, tuple[str, ...]]:
    return {"form": FORM_FILES, "view": view_files(spec)}


#: Which group(s) own each gate case, so a failure only re-prompts the code that can have caused it.
CASE_OWNERS: dict[str, tuple[str, ...]] = {
    "ui-has-page-heading": ("view",),
    "ui-shows-policy-disclosure": ("view",),
    "ui-lists-history": ("view",),
    "ui-renders-labelled-form": ("form",),
    "ui-grade-selector-lists-policy-grades": ("form",),
    "ui-add-and-remove-rows": ("form",),
    "ui-blocks-invalid-credits": ("form",),
    "ui-blocks-missing-fields": ("form",),
    "ui-counts-toward-gpa-flag-is-sent": ("form",),
    "ui-shows-server-review-error": ("form",),
    "ui-shows-network-failure": ("form",),
    "ui-posts-valid-request-and-shows-gpa": ("form", "view"),
}

GATE_DOCKERFILE = """
# Trusted C3 gate image: toolchain only. Candidate code is piped in at run time; this image is never given network.
FROM node:24-bookworm-slim
WORKDIR /gate
RUN npm init -y > /dev/null 2>&1 \\
 && npm install --ignore-scripts --no-audit --no-fund react@18.3.1 react-dom@18.3.1 vite@8.3.4 @vitejs/plugin-react@5.2.0 \\
    vitest@2.1.9 jsdom@25.0.1 @testing-library/react@16.1.0 @testing-library/dom@10.4.0 \\
    @testing-library/user-event@14.5.2 @testing-library/jest-dom@6.6.3
USER node
"""
GATE_IMAGE = "intelise-c3-ui-gate:" + FRONTEND_GATE_VERSION

VITEST_CONFIG = """
export default {
  root: '/tmp/w',
  cacheDir: '/tmp/vite-cache',
  esbuild: { jsx: 'automatic' },
  test: { environment: 'jsdom', globals: true, include: ['test/ui.gate.test.jsx'], setupFiles: ['./test/setup.mjs'], css: false, testTimeout: 20000 },
};
"""
SETUP_MJS = """
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
afterEach(() => cleanup());
"""

UI_TEST_JSX = """
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../src/App.jsx';
import spec from './gate-spec.json';

const json = (status, body) => Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });
let fetchMock;

beforeEach(() => {
  fetchMock = vi.fn((url, init) => (init && init.method === 'POST' ? json(201, spec.sample.response) : json(200, { items: spec.sample.history })));
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

const posts = () => fetchMock.mock.calls.filter(([, init]) => init && init.method === 'POST');
const rows = () => screen.getAllByTestId('module-row');

async function fillRow(user, index, code, credits, grade) {
  const row = within(rows()[index]);
  await user.clear(row.getByTestId('module-code'));
  await user.type(row.getByTestId('module-code'), code);
  await user.clear(row.getByTestId('module-credits'));
  await user.type(row.getByTestId('module-credits'), String(credits));
  await user.selectOptions(row.getByTestId('module-grade'), grade);
}

test('ui-has-page-heading', () => {
  render(<App />);
  expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
});

test('ui-shows-policy-disclosure', () => {
  render(<App />);
  const text = screen.getByTestId('policy-disclosure').textContent;
  expect(text).toContain(spec.policy.policyId);
  expect(text).toContain(spec.policy.policyVersion);
  expect(text).toContain(spec.policy.authorityStatus);
});

test('ui-renders-labelled-form', () => {
  render(<App />);
  expect(screen.getByTestId('gpa-form')).toBeInTheDocument();
  expect(rows()).toHaveLength(1);
  const row = within(rows()[0]);
  expect(row.getByLabelText(/module code/i)).toBeInTheDocument();
  expect(row.getByLabelText(/credits/i)).toBeInTheDocument();
  expect(row.getByLabelText(/grade/i)).toBeInTheDocument();
  expect(row.getByLabelText(/counts toward gpa/i)).toBeChecked();
  expect(screen.getByRole('button', { name: /calculate/i })).toBeInTheDocument();
});

test('ui-grade-selector-lists-policy-grades', () => {
  render(<App />);
  const select = within(rows()[0]).getByTestId('module-grade');
  const options = Array.from(select.options).map((option) => option.value);
  expect(options[0]).toBe('');
  expect(options.filter(Boolean).sort()).toEqual([...spec.grades].sort());
});

test('ui-add-and-remove-rows', async () => {
  const user = userEvent.setup();
  render(<App />);
  expect(within(rows()[0]).getByTestId('remove-module')).toBeDisabled();
  await user.click(screen.getByTestId('add-module'));
  expect(rows()).toHaveLength(2);
  await user.click(within(rows()[1]).getByTestId('remove-module'));
  expect(rows()).toHaveLength(1);
});

test('ui-blocks-invalid-credits', async () => {
  const user = userEvent.setup();
  render(<App />);
  await fillRow(user, 0, 'IT1010', spec.limits.creditsMax + 1, 'A');
  await user.click(screen.getByTestId('calculate-gpa'));
  expect(posts()).toHaveLength(0);
  const credits = within(rows()[0]).getByTestId('module-credits');
  expect(credits).toHaveAttribute('aria-invalid', 'true');
  const describedBy = credits.getAttribute('aria-describedby');
  expect(describedBy).toBeTruthy();
  expect(document.getElementById(describedBy.split(' ')[0]).textContent.trim().length).toBeGreaterThan(0);
  expect(screen.getByTestId('form-error').textContent.trim().length).toBeGreaterThan(0);
});

test('ui-blocks-missing-fields', async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByTestId('calculate-gpa'));
  expect(posts()).toHaveLength(0);
  expect(screen.getByTestId('form-error')).toBeInTheDocument();
});

test('ui-posts-valid-request-and-shows-gpa', async () => {
  const user = userEvent.setup();
  render(<App />);
  await fillRow(user, 0, 'IT1010', 4, 'A');
  await user.click(screen.getByTestId('add-module'));
  await fillRow(user, 1, 'IT1020', 3, 'B+');
  await user.click(screen.getByTestId('calculate-gpa'));
  await waitFor(() => expect(posts()).toHaveLength(1));
  const [url, init] = posts()[0];
  expect(String(url)).toContain('/api/v1/gpa/calculations');
  const body = JSON.parse(init.body);
  expect(body.modules).toHaveLength(2);
  expect(body.modules[0]).toMatchObject({ moduleCode: 'IT1010', credits: 4, grade: 'A', countsTowardGpa: true });
  expect(body.modules[1]).toMatchObject({ moduleCode: 'IT1020', credits: 3, grade: 'B+', countsTowardGpa: true });
  await waitFor(() => expect(screen.getByTestId('gpa-value')).toHaveTextContent(spec.sample.response.gpaText));
  expect(fetchMock.mock.calls.every(([target]) => String(target).startsWith(spec.apiBase))).toBe(true);
});

test('ui-counts-toward-gpa-flag-is-sent', async () => {
  const user = userEvent.setup();
  render(<App />);
  await fillRow(user, 0, 'IT1010', 4, 'A');
  await user.click(within(rows()[0]).getByTestId('module-counts'));
  await user.click(screen.getByTestId('add-module'));
  await fillRow(user, 1, 'IT1020', 3, 'B');
  await user.click(screen.getByTestId('calculate-gpa'));
  await waitFor(() => expect(posts()).toHaveLength(1));
  const body = JSON.parse(posts()[0][1].body);
  expect(body.modules[0].countsTowardGpa).toBe(false);
  expect(body.modules[1].countsTowardGpa).toBe(true);
});

test('ui-shows-server-review-error', async () => {
  const user = userEvent.setup();
  fetchMock.mockImplementation((url, init) => (init && init.method === 'POST' ? json(422, spec.sample.reviewError) : json(200, { items: [] })));
  render(<App />);
  await fillRow(user, 0, 'IT1010', 4, 'A');
  await user.click(screen.getByTestId('calculate-gpa'));
  await waitFor(() => expect(screen.getByTestId('form-error')).toHaveTextContent(spec.sample.reviewError.error.message));
  expect(screen.queryByTestId('gpa-value')).toBeNull();
});

test('ui-shows-network-failure', async () => {
  const user = userEvent.setup();
  fetchMock.mockImplementation((url, init) => (init && init.method === 'POST' ? Promise.reject(new TypeError('Failed to fetch')) : json(200, { items: [] })));
  render(<App />);
  await fillRow(user, 0, 'IT1010', 4, 'A');
  await user.click(screen.getByTestId('calculate-gpa'));
  await waitFor(() => expect(screen.getByTestId('form-error').textContent.trim().length).toBeGreaterThan(0));
});

__HISTORY_TEST__
"""

HISTORY_TEST = """
test('ui-lists-history', async () => {
  render(<App />);
  await waitFor(() => expect(screen.getByTestId('gpa-history')).toHaveTextContent(spec.sample.history[0].gpaText));
});
"""

GATE_BOOTSTRAP = (
    "let d='';process.stdin.setEncoding('utf8');process.stdin.on('data',c=>{d+=c}).on('end',()=>{"
    "const fs=require('fs'),path=require('path'),cp=require('child_process');"
    "try{const p=JSON.parse(d);"
    "for(const [f,c] of Object.entries(p.files)){const t=path.join('/tmp/w',f);fs.mkdirSync(path.dirname(t),{recursive:true});fs.writeFileSync(t,c);}"
    # node_modules must be a real (writable) directory of symlinks: vite writes its temp config bundle inside it.
    "fs.mkdirSync('/tmp/w/node_modules',{recursive:true});"
    "for(const n of fs.readdirSync('/gate/node_modules')){fs.symlinkSync('/gate/node_modules/'+n,'/tmp/w/node_modules/'+n);}"
    "const env=Object.assign({},process.env,{HOME:'/tmp',CI:'1',NO_COLOR:'1'});"
    "const run=(a)=>cp.spawnSync(process.execPath,a,{cwd:'/tmp/w',encoding:'utf8',env,timeout:200000,maxBuffer:20000000});"
    "const b=run(['/gate/node_modules/vite/bin/vite.js','build','--outDir','/tmp/out','--emptyOutDir']);"
    "const t=run(['/gate/node_modules/vitest/vitest.mjs','run','--config','/tmp/w/vitest.gate.config.mjs','--reporter=json','--outputFile=/tmp/vitest.json']);"
    "let tests=[];try{const j=JSON.parse(fs.readFileSync('/tmp/vitest.json','utf8'));"
    "for(const r of j.testResults){for(const a of r.assertionResults){tests.push({id:a.title,passed:a.status==='passed',observed:(a.failureMessages||[]).join(' ').slice(0,400)});}"
    "if(r.message&&!r.assertionResults.length){tests.push({id:'suite',passed:false,observed:String(r.message).slice(0,600)});}}}catch(e){tests.push({id:'suite',passed:false,observed:'vitest produced no result: '+String((t.stderr||'')+(t.stdout||'')).slice(-600)});}"
    "console.log('RESULTS '+JSON.stringify({build:{ok:b.status===0,tail:String((b.stderr||'')+(b.stdout||'')).slice(-900)},tests}));"
    "}catch(e){console.error('GATE_ERROR '+e.message);process.exit(2);}});"
)

Runner = Any


def ui_spec(spec: GpaSpec) -> dict[str, Any]:
    policy = spec.policy
    credits = spec.constraint("ModuleResult.credits")
    return {
        "apiBase": "http://127.0.0.1:3001",
        "policy": {"policyId": policy.policy_id, "policyVersion": policy.policy_version, "authorityStatus": policy.authority_status},
        "grades": [g.grade for g in policy.grades],
        "limits": {"creditsMin": credits.minimum, "creditsMax": credits.maximum},
        "persistence": spec.persistence_required,
        "sample": {
            "response": {"id": "id-1", "gpaText": "3.71", "gpa": 3.71, "totalCredits": 7, "weightedGradePoints": 25.9,
                         "policyId": policy.policy_id, "policyVersion": policy.policy_version,
                         "policyAuthorityStatus": policy.authority_status, "createdAt": "2026-01-01T00:00:00.000Z", "modules": []},
            "history": [{"id": "h-1", "gpaText": "3.55", "gpa": 3.55, "totalCredits": 12, "policyId": policy.policy_id,
                         "policyVersion": policy.policy_version, "createdAt": "2026-01-01T00:00:00.000Z", "modules": []}],
            "reviewError": {"error": {"code": "UNKNOWN_GRADE", "status": "REVIEW_REQUIRED",
                                      "message": "Grade 'Z' is not defined by the accepted grading policy; no grade point is guessed.",
                                      "details": [{"index": 0, "field": "grade", "code": "UNKNOWN_GRADE",
                                                   "message": "Grade 'Z' is not defined by the accepted grading policy."}]}},
        },
    }


def gate_files(spec: GpaSpec) -> dict[str, str]:
    """Trusted gate-side files (tests, setup, config, case data)."""
    history = HISTORY_TEST if spec.persistence_required else ""
    return {
        "test/ui.gate.test.jsx": UI_TEST_JSX.replace("__HISTORY_TEST__", history).strip("\n") + "\n",
        "test/setup.mjs": SETUP_MJS.strip("\n") + "\n",
        "vitest.gate.config.mjs": VITEST_CONFIG.strip("\n") + "\n",
        "test/gate-spec.json": json.dumps(ui_spec(spec)),
    }


def ensure_gate_image(runner: Any = subprocess.run) -> tuple[bool, str]:
    """Build the trusted gate image once (needs network for npm); it is cached under a versioned tag afterwards."""
    try:
        inspect = runner(["docker", "image", "inspect", GATE_IMAGE], capture_output=True, text=True, timeout=30)
        if inspect.returncode == 0:
            return True, "cached"
        built = runner(["docker", "build", "-t", GATE_IMAGE, "-"], input=GATE_DOCKERFILE, capture_output=True, text=True,
                       timeout=GATE_BUILD_TIMEOUT_SECONDS)
    except FileNotFoundError:
        return False, "the docker CLI was not found"
    except subprocess.TimeoutExpired:
        return False, f"building the gate image exceeded {GATE_BUILD_TIMEOUT_SECONDS}s"
    if built.returncode != 0:
        return False, "building the gate image failed (it needs network access for npm): " + " | ".join((built.stderr or "").strip().splitlines()[-3:])
    return True, "built"


def run_ui_gate(runner: Any, ui_files: dict[str, str], spec: GpaSpec) -> dict[str, Any]:
    """Compile and test ``ui_files`` (``frontend/``-prefixed paths, trusted + candidate) in the locked-down gate container."""
    project = {path.removeprefix("frontend/"): content for path, content in ui_files.items()}
    payload = {"files": {**project, **gate_files(spec)}}
    command = [
        "docker", "run", "--rm", "-i", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,nosuid,mode=1777,size=512m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--user", "1000:1000", "--memory", "1g",
        "--pids-limit", "512", "--cpus", "2", GATE_IMAGE, "node", "-e", GATE_BOOTSTRAP,
    ]
    try:
        result = runner(command, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=GATE_TIMEOUT_SECONDS)
    except FileNotFoundError:
        return {"executed": False, "reason": "DOCKER_UNAVAILABLE: docker CLI not found"}
    except subprocess.TimeoutExpired:
        return {"executed": False, "reason": f"GATE_TIMEOUT: exceeded {GATE_TIMEOUT_SECONDS}s"}
    line = next((entry for entry in (result.stdout or "").splitlines() if entry.startswith("RESULTS ")), None)
    if result.returncode != 0 or line is None:
        tail = ((result.stderr or "") + (result.stdout or "")).strip().splitlines()[-4:]
        return {"executed": False, "reason": f"GATE_FAILED (exit {result.returncode}): {' | '.join(tail)}"}
    data = json.loads(line[len("RESULTS "):])
    tests = data["tests"]
    return {"executed": True, "build": data["build"], "results": tests, "passed": sum(t["passed"] for t in tests) + (1 if data["build"]["ok"] else 0),
            "total": len(tests) + 1, "ok": data["build"]["ok"] and all(t["passed"] for t in tests)}


def gate_findings(outcome: dict[str, Any]) -> tuple[list[str], set[str]]:
    """Exact findings plus the groups that own them (both groups when the build itself failed)."""
    if not outcome["executed"]:
        return [f"GATE_NOT_EXECUTED: {outcome['reason']}"], {"form", "view"}
    findings: list[str] = []
    groups: set[str] = set()
    if not outcome["build"]["ok"]:
        findings.append(f"BUILD_FAILED: vite build failed: {outcome['build']['tail'][-500:]}")
        groups |= {"form", "view"}
    for test in outcome["results"]:
        if not test["passed"]:
            findings.append(f"UI_CASE_FAILED[{test['id']}]: {test['observed'][:300]}")
            groups |= set(CASE_OWNERS.get(test["id"], ("form", "view")))
    return findings, groups


def shared_contract(spec: GpaSpec, ui_specification: Any) -> str:
    limits = json.dumps(constraint_payload(spec), sort_keys=True)
    history = spec.persistence_required
    lines = [
        "TRUSTED MODULES YOU MAY IMPORT (already written, do not write them):",
        "- src/api/gpaApi.js: export class ApiError extends Error { status, code, details }; export function calculateGpa(modules) -> Promise of the calculation (POST /api/v1/gpa/calculations); it rejects with ApiError whose details = [{ index, field, code, message }] and status 0 when the service is unreachable; export function listCalculations() -> Promise of an array of calculations, newest first.",
        "- src/policy/gradingPolicy.js: export const POLICY = { policyId, policyVersion, policyName, authorityStatus, institution, rounding: { decimalPlaces, mode } }; export const GRADE_OPTIONS = [{ grade: 'A+', gradePoint: 4 }, ...] (the accepted grading policy; never hard-code grades or grade points).",
        "FILE CONTRACTS (React function components, named exports, JSX, no TypeScript, no PropTypes):",
        "- src/App.jsx: export function App(). Renders one <h1>, <PolicyDisclosure />, <GpaCalculatorForm onCalculated={...} />, <GpaResult result={...} />" + (" and <HistoryList items={...} error={...} />. Loads history on mount with listCalculations() and again after every successful calculation (catch failures and pass error.message)." if history else ".") + " Do not import styles.css; the trusted main.jsx does.",
        "- src/components/GpaCalculatorForm.jsx: export function GpaCalculatorForm({ onCalculated }). Owns the rows state and submission. Import './form.css'.",
        "- src/components/ModuleRow.jsx: export function ModuleRow({ row, position, errors, onChange, onRemove, canRemove }); row = { rowId, moduleCode, credits (string), grade, countsTowardGpa (boolean) }; errors = { moduleCode?, credits?, grade? } (message strings); onChange(rowId, field, value); onRemove(rowId). Renders one table row or equivalent element.",
        "- src/validation/moduleValidation.js: export const CONSTRAINTS (the limits below, as data) and export function validateRows(rows) -> { errors: { [rowId]: { [field]: message } }, formErrors: string[], modules: [{ moduleCode, credits (number), grade, countsTowardGpa }] }. Pure function.",
        "- src/components/GpaResult.jsx: export function GpaResult({ result }); result is null before the first calculation (show a short empty-state hint).",
        "- src/components/PolicyDisclosure.jsx: export function PolicyDisclosure(). Shows POLICY.policyId, POLICY.policyVersion and POLICY.authorityStatus, the rounding rule, and when authorityStatus is SAMPLE_RESEARCH_POLICY says plainly that this is a research transcription, not an official institutional calculation.",
    ]
    if history:
        lines.append("- src/components/HistoryList.jsx: export function HistoryList({ items, error }); one <li> per calculation showing gpaText and totalCredits; show the error text when error is set; an empty-state hint when there are no items.")
    lines += [
        "- src/components/form.css: all styles for the form and rows. src/styles.css: page layout and global styles. Plain CSS, no @import, no url(), responsive down to 360px wide, visible focus styles, sufficient colour contrast.",
        "REQUIRED data-testid ATTRIBUTES (independent testers rely on them): gpa-form (the <form>, noValidate), module-row (each row), module-code, module-credits (type number), module-grade (<select>: first option value '' then one option per GRADE_OPTIONS with value = grade), module-counts (checkbox, checked by default), remove-module (one per row, disabled when only one row remains), add-module (button), calculate-gpa (submit button), form-error (role='alert', rendered only when there is a form-level message), gpa-result (always rendered, aria-live='polite'), gpa-value (only when a result exists; its text is result.gpaText), policy-disclosure" + (", gpa-history" if history else "") + ".",
        "ACCESSIBILITY: every control has an accessible name (label htmlFor or aria-label) containing 'Module code', 'Credits', 'Grade' or 'Counts toward GPA'; invalid controls get aria-invalid='true' and aria-describedby pointing at the element that contains the message; use a real <button> for actions.",
        f"LIMITS (approved C1 constraints plus Knowledge Base defaults; use exactly these values): {limits}",
        "BEHAVIOUR: start with one empty row; 'Add module' appends an empty row with a unique stable rowId (never use the array index as key). Submit never calls the API when validateRows reports problems: show the field messages and a form-level message in form-error. When valid call calculateGpa(modules) once; on success call onCalculated(result); on ApiError (or any error) show its message in form-error (for a 422 prefix it with 'Review required: ') and map error.details[i] with { index, field, message } onto that row's field. Disable the submit button while the request is in flight.",
        f"UI SPECIFICATION (released C2, follow its component list and labels): {json.dumps(ui_specification, sort_keys=True)}",
    ]
    return "\n".join(lines)


@dataclass
class FrontendOutcome:
    files: dict[str, str] = field(default_factory=dict)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    gate: dict[str, Any] | None = None
    repaired_groups: list[str] = field(default_factory=list)
    response_models: dict[str, str | None] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return not self.failures and bool(self.files)


async def generate_frontend(
    *, gateway: OpenRouterModuleGateway, contexts: dict[str, BoundedModuleContext], trusted_files: dict[str, str],
    spec: GpaSpec, runner: Any, use_cache: bool = True,
) -> FrontendOutcome:
    """Parallel group generation, then the compile+behaviour gate, then at most one targeted repair round."""
    outcome = FrontendOutcome()
    loop = asyncio.get_running_loop()
    names = list(contexts)
    results = await asyncio.gather(*(gateway.generate(contexts[name], use_cache=use_cache, max_attempts=2, write_cache=False) for name in names))
    group_content: dict[str, dict[str, str]] = {}
    cached = {}
    for name, result in zip(names, results):
        for entry in result.ledger:
            entry["module_id"] = f"fe.ui:{name}"
            entry["cache_key"] = result.cache_key
        outcome.ledger.extend(result.ledger)
        cached[name] = result.cache_hit
        outcome.response_models[name] = result.response_model
        if result.status == "ACCEPTED" and result.content is not None:
            group_content[name] = json.loads(result.content)
        else:
            outcome.failures.append({"module_id": f"fe.ui:{name}", "status": result.status, "reasons": result.reasons,
                                     "ledger": result.ledger, "rejected_outputs": result.outputs})
    if outcome.failures:
        return outcome

    def combined() -> dict[str, str]:
        files = dict(trusted_files)
        for content in group_content.values():
            files.update(content)
        return files

    gate = await loop.run_in_executor(None, run_ui_gate, runner, combined(), spec)
    outcome.gate = gate
    if gate["executed"] and gate["ok"]:
        _finish(outcome, gateway, contexts, group_content, cached, combined())
        return outcome

    findings, owners = gate_findings(gate)
    if not gate["executed"]:
        outcome.failures.append({"module_id": "fe.ui", "status": "GATE_NOT_EXECUTED", "reasons": findings, "ledger": [], "rejected_outputs": []})
        return outcome
    repair = []
    for name in sorted(owners & set(names)):
        used = sum(1 for e in outcome.ledger if e["module_id"] == f"fe.ui:{name}" and not e.get("cache_hit"))
        if used >= 2:
            outcome.failures.append({"module_id": f"fe.ui:{name}", "status": "ATTEMPT_LIMIT_REACHED",
                                     "reasons": [f"{name} already used {used} calls; the gate still reports: {'; '.join(findings)[:600]}"],
                                     "ledger": [e for e in outcome.ledger if e["module_id"] == f"fe.ui:{name}"], "rejected_outputs": []})
        else:
            repair.append(name)
    if outcome.failures or not repair:
        if not outcome.failures:
            outcome.failures.append({"module_id": "fe.ui", "status": "GATE_FAILED", "reasons": findings, "ledger": [], "rejected_outputs": []})
        return outcome
    repaired = await asyncio.gather(*(gateway.generate(
        replace(contexts[name], validator_findings=tuple(findings), current_source=json.dumps(group_content[name], sort_keys=True)),
        use_cache=False, max_attempts=1, write_cache=False) for name in repair))
    for name, result in zip(repair, repaired):
        for entry in result.ledger:
            entry["module_id"] = f"fe.ui:{name}"
            entry["cache_key"] = result.cache_key
        outcome.ledger.extend(result.ledger)
        outcome.response_models[name] = result.response_model or outcome.response_models.get(name)
        cached[name] = False
        if result.status == "ACCEPTED" and result.content is not None:
            group_content[name] = json.loads(result.content)
            outcome.repaired_groups.append(name)
        else:
            outcome.failures.append({"module_id": f"fe.ui:{name}", "status": result.status, "reasons": result.reasons,
                                     "ledger": result.ledger, "rejected_outputs": result.outputs})
    if outcome.failures:
        return outcome
    gate = await loop.run_in_executor(None, run_ui_gate, runner, combined(), spec)
    outcome.gate = gate
    if gate["executed"] and gate["ok"]:
        _finish(outcome, gateway, contexts, group_content, cached, combined())
        return outcome
    again, _ = gate_findings(gate)
    outcome.failures.append({"module_id": "fe.ui", "status": "GATE_FAILED_AFTER_REPAIR", "reasons": again, "ledger": [], "rejected_outputs": []})
    return outcome


def _finish(outcome: FrontendOutcome, gateway: OpenRouterModuleGateway, contexts: dict[str, BoundedModuleContext],
            group_content: dict[str, dict[str, str]], cached: dict[str, bool], files: dict[str, str]) -> None:
    for name, content in group_content.items():
        if not cached.get(name) or name in outcome.repaired_groups:
            gateway.remember(contexts[name], json.dumps(content, sort_keys=True), outcome.response_models.get(name))
    outcome.files = {path: text for path, text in files.items() if any(path in c for c in group_content.values())}
