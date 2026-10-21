"""Static, reviewed runtime files for behaviour-generated applications (Stage 0).

These files are identical for every run; per-run content lives only in
``backend/behaviour-spec.json`` (deterministic, from UML) and
``backend/src/domain.mjs`` (model-written). The backend has no npm dependencies,
so it starts with plain ``node`` on a loopback port; the React (Vite) frontend is
built once into static files that the same server serves. ``server.mjs`` and
``probe.mjs`` legitimately use Node built-ins and are therefore not subject to the
generated-module lexical policy; they never evaluate strings and only call public
facade methods that the spec declares.
"""

from __future__ import annotations

BEHAVIOUR_TEMPLATE_SET_VERSION = "c3-behaviour-templates-v1"

# Shared by server and probe: JSON-safe view of an object graph that keeps
# undefined / NaN visible instead of silently dropping them.
_SNAPSHOT_JS = r"""
export function snapshot(value, depth = 0, seen = new WeakSet()) {
  if (value === undefined) return { $undefined: true };
  if (typeof value === "number" && !Number.isFinite(value)) return { $nonFinite: String(value) };
  if (value === null || typeof value !== "object") return value;
  if (seen.has(value) || depth > 6) return { $ref: true };
  seen.add(value);
  if (Array.isArray(value)) return value.map((item) => snapshot(item, depth + 1, seen));
  const out = { $class: value.constructor && value.constructor.name ? value.constructor.name : "Object" };
  for (const [key, item] of Object.entries(value)) out[key] = snapshot(item, depth + 1, seen);
  return out;
}

export function findProblems(view, path, problems = []) {
  if (view && typeof view === "object") {
    if (view.$undefined) problems.push(`${path} is undefined`);
    else if (view.$nonFinite) problems.push(`${path} is ${view.$nonFinite}`);
    else if (Array.isArray(view)) view.forEach((item, index) => findProblems(item, `${path}.${index}`, problems));
    else for (const [key, item] of Object.entries(view)) if (key !== "$class") findProblems(item, `${path}.${key}`, problems);
  }
  return problems;
}

export function convertArgs(spec, method, args) {
  const classes = new Map(spec.classes.map((item) => [item.name, item]));
  return method.params.map((param, index) => {
    const raw = Array.isArray(args) && index < args.length ? args.at(index) : undefined;
    if (param.kind === "NUMBER") {
      const value = Number(raw);
      if (raw === "" || raw === null || raw === undefined || !Number.isFinite(value)) throw new Error(`${param.name} must be a number`);
      return value;
    }
    if (param.kind === "BOOLEAN") return raw === true || raw === "true";
    if (param.kind === "ENUM") {
      if (!param.choices.includes(raw)) throw new Error(`${param.name} must be one of ${param.choices.join(", ")}`);
      return raw;
    }
    if (param.kind === "CLASS") {
      if (!param.choices.includes(raw)) throw new Error(`${param.name} must be one of ${param.choices.join(", ")}`);
      return { $construct: classes.get(raw).name };
    }
    return raw === undefined || raw === null ? "" : String(raw);
  });
}
"""

SERVER_MJS = r"""// InteliSE C3 behaviour runtime (static template). Loopback only, no dependencies.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import * as domain from "./src/domain.mjs";
import { snapshot, convertArgs } from "./runtime.mjs";

const root = fileURLToPath(new URL(".", import.meta.url));
const spec = JSON.parse(await readFile(join(root, "behaviour-spec.json"), "utf8"));
const portIndex = process.argv.indexOf("--port");
const port = Number(portIndex > 0 ? process.argv.at(portIndex + 1) : 5310);
const staticIndex = process.argv.indexOf("--static");
const staticRoot = resolve(staticIndex > 0 ? process.argv.at(staticIndex + 1) : join(root, "..", "frontend", "dist"));
const exportsByName = new Map(Object.entries(domain));
const facadeSpec = spec.classes.find((item) => item.name === spec.facade);
const publicMethods = new Map(facadeSpec.methods.filter((m) => m.public).map((m) => [m.name, m]));
const construct = (name) => new (exportsByName.get(name))();
let facade = construct(spec.facade);
const log = [];

const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml" };
const send = (res, code, body, type = "application/json") => {
  res.writeHead(code, { "content-type": type, "cache-control": "no-store" });
  res.end(type === "application/json" ? JSON.stringify(body) : body);
};
const readBody = (req) => new Promise((resolve, reject) => {
  let data = "";
  req.on("data", (chunk) => { data += chunk; if (data.length > 65536) reject(new Error("body too large")); });
  req.on("end", () => { try { resolve(data ? JSON.parse(data) : {}); } catch { reject(new Error("invalid JSON")); } });
});

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://127.0.0.1");
    if (req.method === "GET" && url.pathname === "/api/spec") return send(res, 200, spec);
    if (req.method === "GET" && url.pathname === "/api/state") return send(res, 200, { state: snapshot(facade), log });
    if (req.method === "POST" && url.pathname === "/api/reset") {
      facade = construct(spec.facade);
      log.length = 0;
      return send(res, 200, { state: snapshot(facade), log });
    }
    if (req.method === "POST" && url.pathname === "/api/invoke") {
      const body = await readBody(req);
      const method = publicMethods.get(body.method);
      if (!method) return send(res, 400, { error: `unknown public method ${String(body.method)}` });
      const entry = { method: method.name, args: body.args ?? [], at: new Date().toISOString() };
      try {
        const args = convertArgs(spec, method, body.args).map((arg) => (arg && arg.$construct ? construct(arg.$construct) : arg));
        const result = await facade[method.name](...args);
        entry.ok = true;
        entry.result = snapshot(result);
      } catch (error) {
        entry.ok = false;
        entry.error = String(error && error.message ? error.message : error).slice(0, 300);
      }
      log.push(entry);
      return send(res, entry.ok ? 200 : 422, { entry, state: snapshot(facade), log });
    }
    if (req.method === "GET") {
      const relative = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
      const file = normalize(join(staticRoot, relative));
      if (!file.startsWith(staticRoot)) return send(res, 403, { error: "forbidden" });
      const content = await readFile(file).catch(() => null);
      if (content === null) return send(res, 404, { error: "not found" });
      return send(res, 200, content, types[extname(file)] ?? "application/octet-stream");
    }
    return send(res, 405, { error: "method not allowed" });
  } catch (error) {
    return send(res, 500, { error: String(error && error.message ? error.message : error).slice(0, 300) });
  }
});
server.listen(port, "127.0.0.1", () => console.log(`behaviour app listening on http://127.0.0.1:${port}`));
"""

RUNTIME_MJS = "// InteliSE C3 behaviour runtime helpers (static template).\n" + _SNAPSHOT_JS

# Sandboxed smoke probe used during generation. It calls the facade's public
# methods like a user would, with fixed sample inputs, and reports crashes,
# undefined/NaN fields and the absence of any observable effect. It does not
# know the expected answers: passing it is not a correctness claim.
PROBE_MJS = r"""import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import * as domain from "./domain.mjs";
import { snapshot, findProblems, convertArgs } from "./runtime.mjs";

console.log = () => {}; // keep stdout for the probe report only
const root = fileURLToPath(new URL(".", import.meta.url));
const spec = JSON.parse(await readFile(join(root, "behaviour-spec.json"), "utf8"));
const exportsByName = new Map(Object.entries(domain));
const findings = [];
const warnings = [];
const facadeSpec = spec.classes.find((item) => item.name === spec.facade);
const byName = new Map(facadeSpec.methods.filter((m) => m.public).map((m) => [m.name, m]));
const Facade = exportsByName.get(spec.facade);
const text = (error) => String(error && error.message ? error.message : error).slice(0, 120);
const callText = (step) => `${step.method}(${step.args.map((v) => JSON.stringify(v)).join(", ")})`;

// Run a plan (list of {method, args}) on a fresh facade; returns per-step state views.
function runPlan(plan) {
  const steps = [];
  const problems = [];
  let facade;
  try { facade = new Facade(); } catch (error) {
    problems.push({ code: "PROBE_CONSTRUCTOR_THREW", message: `new ${spec.facade}() threw: ${text(error)}` });
    return { steps, problems, initial: null };
  }
  const initial = JSON.stringify(snapshot(facade));
  for (const step of plan) {
    const method = byName.get(step.method);
    const call = callText(step);
    try {
      const args = convertArgs(spec, method, step.args).map((arg) => (arg && arg.$construct ? new (exportsByName.get(arg.$construct))() : arg));
      const result = facade[method.name](...args);
      const view = snapshot(facade);
      steps.push({ call, ok: true, result: snapshot(result), state: view });
      const bad = findProblems(view, spec.facade);
      for (const problem of bad) problems.push({ code: "PROBE_INVALID_FIELD", message: `after ${call}, ${problem}` });
      if (bad.length) break;
    } catch (error) {
      steps.push({ call, ok: false, error: text(error) });
      problems.push({ code: "PROBE_CALL_THREW", message: `${call} threw on valid sample input: ${text(error)}` });
      break;
    }
  }
  return { steps, problems, initial };
}

let steps = [];
if (typeof Facade !== "function") {
  findings.push({ code: "PROBE_FACADE_NOT_EXPORTED", message: `${spec.facade} is not exported as a class` });
} else {
  const plan = spec.probe_plan;
  const base = runPlan(plan);
  steps = base.steps;
  findings.push(...base.problems);
  if (!findings.length) {
    if (base.steps.every((s) => JSON.stringify(s.state) === base.initial)) {
      findings.push({ code: "PROBE_NO_OBSERVABLE_EFFECT", message: `no public ${spec.facade} method changed any field` });
    }
    // Metamorphic check: every input given before the first no-argument (compute) step must
    // influence the state right after that step. Generic: no expected values are used.
    const computeIndex = plan.findIndex((s, i) => i > 0 && byName.get(s.method).params.length === 0);
    // Outputs of the compute step = the facade fields that step changed in the baseline run.
    // Comparing only those catches an input that is stored but not used by the computation.
    const before = computeIndex > 0 ? base.steps.at(computeIndex - 1).state : null;
    const computed = computeIndex > 0 ? base.steps.at(computeIndex).state : null;
    const outputKeys = computed ? Object.keys(computed).filter((k) => k !== "$class" && JSON.stringify(computed[k]) !== JSON.stringify(before[k])) : [];
    const pick = (state) => JSON.stringify(outputKeys.map((k) => state[k]));
    if (computeIndex > 0 && outputKeys.length) {
      const after = pick(computed);
      for (let i = 0; i < computeIndex; i += 1) {
        const method = byName.get(plan.at(i).method);
        method.params.forEach((param, j) => {
          const original = plan.at(i).args.at(j);
          let changed;
          if (param.kind === "NUMBER") changed = original + 8;
          else if ((param.kind === "CLASS" || param.kind === "ENUM") && param.choices.length > 1) changed = param.choices.find((c) => c !== original);
          else return;
          const variant = plan.map((s, k) => (k === i ? { method: s.method, args: s.args.map((a, m) => (m === j ? changed : a)) } : s));
          const run = runPlan(variant);
          const view = run.steps.at(computeIndex);
          if (view && view.ok && pick(view.state) === after) {
            warnings.push({
              code: "PROBE_INPUT_IGNORED",
              message: `changing ${param.name} in step ${i + 1} ${callText(plan.at(i))} from ${JSON.stringify(original)} to ${JSON.stringify(changed)} did not change the result fields (${outputKeys.join(", ")}) of step ${computeIndex + 1} ${callText(plan.at(computeIndex))}: that input is ignored by the computation`,
            });
          }
        });
      }
    }
  }
}
process.stdout.write(JSON.stringify({ findings, warnings, steps }) + "\n");
"""

# --------------------------------------------------------------------------- React (Vite) frontend
# Deterministic template, identical for every run. It is a generic method runner over /api/spec:
# one form per public facade method, the facade state, the call log and the requirement table.

FRONTEND_PACKAGE_JSON = """{
  "name": "generated-behaviour-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "build": "vite build",
    "dev": "vite --host 127.0.0.1"
  },
  "dependencies": {
    "react": "18.3.1",
    "react-dom": "18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "5.2.0",
    "vite": "8.3.4"
  }
}
"""

FRONTEND_INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Generated application</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>
"""

FRONTEND_VITE_CONFIG = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({ plugins: [react()] });
"""

FRONTEND_MAIN_JSX = """import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
"""

FRONTEND_API_JS = """// Same-origin client for the generated Node server (see backend/server.mjs).
async function call(path, options) {
  const response = await fetch(path, options);
  return response.json();
}

export const getSpec = () => call('/api/spec');
export const getState = () => call('/api/state');
export const resetState = () => call('/api/reset', { method: 'POST' });
export const invokeMethod = (method, args) =>
  call('/api/invoke', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ method, args }) });
"""

FRONTEND_VALUE_VIEW_JSX = """// Renders the server's JSON-safe snapshot. undefined and NaN stay visible instead of being dropped.
export function ValueView({ value }) {
  if (value === null || typeof value !== 'object') return <code>{JSON.stringify(value)}</code>;
  if (value.$undefined) return <code className="bad">undefined</code>;
  if (value.$nonFinite) return <code className="bad">{value.$nonFinite}</code>;
  if (Array.isArray(value)) {
    if (!value.length) return <code>[]</code>;
    return (
      <ul>
        {value.map((item, index) => (
          <li key={index}><ValueView value={item} /></li>
        ))}
      </ul>
    );
  }
  return (
    <table className="kv">
      {value.$class && <caption>{value.$class}</caption>}
      <tbody>
        {Object.entries(value)
          .filter(([key]) => key !== '$class')
          .map(([key, item]) => (
            <tr key={key}>
              <th>{key}</th>
              <td><ValueView value={item} /></td>
            </tr>
          ))}
      </tbody>
    </table>
  );
}
"""

FRONTEND_METHOD_FORM_JSX = """import { useState } from 'react';

// One form per public method of the facade class; parameters come from the UML (choices = enum / class names).
export function MethodForm({ method, onRun }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(method.params.map((param) => [param.name, param.choices.length ? param.choices[0] : ''])),
  );
  const submit = (event) => {
    event.preventDefault();
    onRun(method, method.params.map((param) => values[param.name]));
  };
  return (
    <form className="action" data-method={method.name} onSubmit={submit}>
      <strong>{method.name}()</strong>
      {method.params.map((param) => (
        <label key={param.name}>
          {param.name} : {param.type}
          {param.choices.length ? (
            <select
              name={param.name}
              aria-label={`${method.name} ${param.name}`}
              value={values[param.name]}
              onChange={(event) => setValues({ ...values, [param.name]: event.target.value })}
            >
              {param.choices.map((choice) => (
                <option key={choice} value={choice}>{choice}</option>
              ))}
            </select>
          ) : (
            <input
              name={param.name}
              aria-label={`${method.name} ${param.name}`}
              type={param.kind === 'NUMBER' ? 'number' : 'text'}
              step="any"
              required
              value={values[param.name]}
              onChange={(event) => setValues({ ...values, [param.name]: event.target.value })}
            />
          )}
        </label>
      ))}
      <button type="submit">Run {method.name}</button>
    </form>
  );
}
"""

FRONTEND_APP_JSX = """import { useEffect, useState } from 'react';
import { getSpec, getState, invokeMethod, resetState } from './api.js';
import { MethodForm } from './components/MethodForm.jsx';
import { ValueView } from './components/ValueView.jsx';

export function App() {
  const [spec, setSpec] = useState(null);
  const [payload, setPayload] = useState({ state: null, log: [] });
  const [error, setError] = useState('');

  useEffect(() => {
    getSpec().then(setSpec);
    getState().then(setPayload);
  }, []);

  if (!spec) return <p className="loading">Loading...</p>;

  const facade = spec.classes.find((item) => item.name === spec.facade);
  const run = async (method, args) => {
    const result = await invokeMethod(method.name, args);
    setError(result.entry && !result.entry.ok ? `${method.name} failed: ${result.entry.error}` : result.error ?? '');
    if (result.state) setPayload(result);
  };
  const reset = async () => {
    setPayload(await resetState());
    setError('');
  };

  return (
    <>
      <header>
        <div>
          <p className="eyebrow">InteliSE C3 · behaviour generator (Stage 0)</p>
          <h1>{spec.facade} · {spec.project_id}</h1>
          <p className="labels">
            <span className="label det">Structure + UI: deterministic from C2 UML</span>
            <span className="label llm">Logic: model-written (provider and model in behaviour-manifest.json), statically validated and smoke-probed</span>
            <span className="label warn">Not independently tested (C4 not integrated)</span>
          </p>
        </div>
        <button type="button" onClick={reset}>Reset state</button>
      </header>
      <main>
        <section>
          <h2>Actions</h2>
          {facade.methods.filter((method) => method.public).map((method) => (
            <MethodForm key={method.name} method={method} onRun={run} />
          ))}
        </section>
        <section>
          <h2>State of {spec.facade}</h2>
          {payload.state && <ValueView value={payload.state} />}
          <p className="error" role="alert">{error}</p>
        </section>
        <section>
          <h2>Call log</h2>
          <ol className="log">
            {payload.log.map((entry, index) => (
              <li key={index} className={entry.ok ? 'ok' : 'fail'}>
                <code>{entry.method}({entry.args.map((arg) => JSON.stringify(arg)).join(', ')})</code>
                <span>{entry.ok ? ' ✓' : ` ✗ ${entry.error}`}</span>
              </li>
            ))}
          </ol>
        </section>
        <section>
          <h2>Requirements (C1) and anchored classes (C2)</h2>
          <table>
            <thead>
              <tr><th>ID</th><th>Type</th><th>Requirement</th><th>UML class</th></tr>
            </thead>
            <tbody>
              {spec.requirements.map((req) => {
                const classes = spec.anchors
                  .filter((anchor) => anchor.requirement_id === req.requirement_id)
                  .map((anchor) => anchor.class_name ?? anchor.uml_id);
                return (
                  <tr key={req.requirement_id}>
                    <td><code>{req.requirement_id.slice(0, 8)}</code></td>
                    <td>{req.requirement_type ?? ''}</td>
                    <td>{req.title}</td>
                    <td>{classes.join(', ') || 'not anchored'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      </main>
    </>
  );
}
"""

FRONTEND_STYLES_CSS = r""":root { color-scheme: light; --ink: #172033; --muted: #5b6b85; --line: #dbe3f0; --accent: #2457d6; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.45 system-ui, "Segoe UI", Arial, sans-serif; color: var(--ink); background: #f4f7fc; }
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding: 20px 28px; background: #0f1b3d; color: #fff; }
header h1 { margin: 2px 0 8px; font-size: 1.6rem; }
.eyebrow { margin: 0; font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; color: #a9b8e0; }
.labels { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; }
.label { padding: 3px 9px; border-radius: 999px; font-size: .75rem; font-weight: 600; }
.label.det { background: #dff3e6; color: #17603a; } .label.llm { background: #ece6ff; color: #4b2aa8; } .label.warn { background: #fde7e7; color: #a12020; }
header button { padding: 8px 14px; border: 1px solid #ffffff55; border-radius: 8px; background: transparent; color: #fff; cursor: pointer; }
main { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; padding: 20px 28px; }
section { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 14px 18px; }
h2 { margin: 0 0 10px; font-size: 1.05rem; }
.action { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--line); }
.action strong { flex-basis: 100%; font-family: ui-monospace, Consolas, monospace; }
label { display: grid; gap: 3px; font-size: .8rem; color: var(--muted); }
input, select { min-width: 140px; padding: 7px 9px; border: 1px solid #c8d2e4; border-radius: 7px; font: inherit; }
.action button { padding: 8px 14px; border: 0; border-radius: 8px; background: var(--accent); color: #fff; font-weight: 600; cursor: pointer; }
table { width: 100%; border-collapse: collapse; } th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid var(--line); vertical-align: top; font-size: .9rem; }
.kv caption { text-align: left; font-weight: 700; color: var(--muted); font-size: .8rem; padding-bottom: 2px; }
.kv th { width: 35%; color: var(--muted); font-weight: 600; }
code { font-family: ui-monospace, Consolas, monospace; } .bad { color: #b42318; font-weight: 700; }
.log li.ok { color: #17603a; } .log li.fail { color: #b42318; } .error { color: #b42318; font-weight: 600; min-height: 1.2em; }
.loading { padding: 20px 28px; color: var(--muted); }
"""

FRONTEND_FILES = {
    "frontend/package.json": FRONTEND_PACKAGE_JSON,
    "frontend/index.html": FRONTEND_INDEX_HTML,
    "frontend/vite.config.js": FRONTEND_VITE_CONFIG,
    "frontend/src/main.jsx": FRONTEND_MAIN_JSX,
    "frontend/src/App.jsx": FRONTEND_APP_JSX,
    "frontend/src/api.js": FRONTEND_API_JS,
    "frontend/src/components/MethodForm.jsx": FRONTEND_METHOD_FORM_JSX,
    "frontend/src/components/ValueView.jsx": FRONTEND_VALUE_VIEW_JSX,
    "frontend/src/styles.css": FRONTEND_STYLES_CSS,
}


def readme(project_id: str, facade: str, model: str, provider: str = "ollama-local") -> str:
    return (
        f"# Generated behaviour application: {facade} ({project_id})\n\n"
        "Produced by the InteliSE Component 3 behaviour generator (Stage 0).\n\n"
        "- `backend/` - Node.js, no npm dependencies. `behaviour-spec.json`, `server.mjs`, `runtime.mjs`:\n"
        "  deterministic (TEMPLATE). `src/domain.mjs`: written by "
        f"`{model}` via `{provider}`, then checked by the\n"
        "  conservative lexical safety policy, the UML interface check, `node --check` and a sandboxed\n"
        "  smoke probe. Passing these is not a correctness claim; independent testing (C4) is pending.\n"
        "- `frontend/` - React + Vite UI (deterministic TEMPLATE): a form per public method of the facade class,\n"
        "  its state, a call log and the requirement table.\n\n"
        "Run:\n\n"
        "```\n"
        "cd frontend && npm install && npm run build && cd ..\n"
        "node --permission --allow-fs-read=<this folder>/* backend/server.mjs --port 5310\n"
        "```\n\n"
        "The server serves `frontend/dist` and the JSON API (`/api/spec`, `/api/state`, `/api/invoke`, `/api/reset`).\n"
    )
