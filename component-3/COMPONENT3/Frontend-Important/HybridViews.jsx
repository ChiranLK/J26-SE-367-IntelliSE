/*
 * HYBRID RESULT VIEWS
 * Displays hybrid preview, living traceability, regeneration and readiness results.
 * Original: component-3/dashboard/src/components/HybridViews.jsx
 */

import { useEffect, useState } from "react";
import { formatSriLankaTime } from "../lib/format.js";
import { friendlyMessage, describeChange, moduleLabel, nodeLabels, SUPPORT_MODULES } from "../lib/hybridFriendly.js";
import { ragRows, traceChains, verificationCounts } from "../lib/hybrid.js";
import { useHybridRun } from "../state/useHybridRun.js";
import { Badge, Button, Callout, Card, ErrorPanel, Hash, JsonView, KeyValues, Loading, PageHeader, Stat, StatusBadge, Table, TechnicalDetails } from "./ui.jsx";

// Human-friendly views of the Hybrid GPA run for the workflow pages. They only restate what the API returned.

const chipRow = { display: "flex", flexWrap: "wrap", gap: 6 };
const statsRow = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 };

function Chips({ items, tone = "neutral" }) {
  if (!items.length) return <span className="muted">—</span>;
  return (
    <div style={chipRow}>
      {items.map((item) => <Badge key={item} tone={tone}>{item}</Badge>)}
    </div>
  );
}

function RunBanner({ run }) {
  const mode = run?.manifest?.generation_mode ?? "TEMPLATE";
  return (
    <Callout tone="info" title="Showing your GPA project run">
      Run <code>{run.generation_run_id}</code>
      {mode !== "TEMPLATE" ? <> · generated in <strong>{mode}</strong> mode</> : null} · from the C1/C2 test fixtures.
    </Callout>
  );
}

// The report text carries a "SIMULATED:" marker; the source line under the report already says where it comes from.
const withoutPrefix = (text) => (text ? String(text).replace(/^SIMULATED:\s*/i, "") : "—");

function FriendlyError({ error, context, onGenerate }) {
  if (!error) return null;
  const message = friendlyMessage(error);
  const stale = (error.errors ?? []).some((item) => item.code === "STALE_BASE_RUN");
  return (
    <>
      {message ? (
        <Callout tone="warn" title="What happened">
          {message}
          {stale && onGenerate ? (
            <div className="button-row">
              <Button onClick={onGenerate}>Go to Code Generation</Button>
            </div>
          ) : null}
        </Callout>
      ) : null}
      <ErrorPanel error={error} context={context} />
    </>
  );
}

// ------------------------------------------------------------------ Traceability
export function HybridTraceView() {
  const { hybrid, run, loadTrace } = useHybridRun();
  const trace = hybrid.trace;
  const graph = trace?.graph;
  const labels = nodeLabels(graph);
  const chains = traceChains(graph);
  const label = (type, key) => labels[`${type}:${key}`] ?? key;
  const coverage = trace?.coverage;
  const lineage = (hybrid.defect ?? hybrid.change)?.manifest?.lineage;

  return (
    <div className="page">
      <PageHeader
        title="Living Traceability"
        subtitle="Every client requirement, followed through the design to the generated code, API, database and test hooks."
      />
      <RunBanner run={run} />

      {!trace ? (
        <Card title="Load the traceability graph" subtitle="The graph was built when the run was generated.">
          <Button onClick={() => loadTrace.run()} loading={loadTrace.loading}>Load traceability graph</Button>
          <FriendlyError error={loadTrace.error} context="Traceability graph" />
        </Card>
      ) : (
        <>
          <div style={statsRow}>
            <Stat label="Requirements traced" value={`${coverage?.traced_count ?? 0} / ${coverage?.total ?? 0}`} tone={coverage?.traced_count === coverage?.total ? "ok" : "warn"} hint="each has a full chain below" />
            <Stat label="Graph version" value={graph?.version ?? "—"} hint="goes up after every change" />
            <Stat label="Orphan artifacts" value={coverage?.orphan_artifacts?.length ?? 0} tone={coverage?.orphan_artifacts?.length ? "warn" : "ok"} hint="generated files with no requirement" />
            <Stat label="Files generated" value={run.manifest?.files?.length ?? "—"} />
          </div>

          {lineage ? (
            <Callout tone="ok" title={`Updated after a ${hybrid.defect ? "defect repair" : "requirement change"}`}>
              The graph is now version {graph?.version}. Only {lineage.impact_set.length} module{lineage.impact_set.length === 1 ? "" : "s"} were
              regenerated; the links of the untouched modules were carried over.
            </Callout>
          ) : null}

          <Card title="From requirement to test hook" subtitle="Read each row from left to right. Nothing appears here unless the generator really linked it.">
            <Table
              dense
              rows={chains}
              rowKey={(chain) => chain.requirementId}
              empty="No requirements in the graph."
              columns={[
                {
                  key: "requirementId",
                  header: "Requirement",
                  render: (chain) => (
                    <div>
                      <strong>{chain.requirementId}</strong> <span className="muted">v{chain.version} · {chain.type}</span>
                      <div>{label("REQUIREMENT", chain.requirementId)}</div>
                    </div>
                  ),
                },
                { key: "uml", header: "Design (UML class)", render: (chain) => <Chips items={chain.uml.map((item) => item.split("#")[1] ?? item)} /> },
                { key: "modules", header: "Code", render: (chain) => <Chips tone="info" items={chain.modules.filter((module) => !SUPPORT_MODULES.has(module)).map(moduleLabel)} /> },
                { key: "support", header: "Contracts and checks", render: (chain) => <Chips items={chain.modules.filter((module) => SUPPORT_MODULES.has(module)).map(moduleLabel)} /> },
                { key: "api", header: "API", render: (chain) => <Chips items={chain.api.map((key) => label("API_OPERATION", key))} /> },
                { key: "db", header: "Database", render: (chain) => <Chips items={chain.db} /> },
                { key: "seams", header: "Test hooks", render: (chain) => <Chips tone="ok" items={chain.seams} /> },
              ]}
            />
            <p className="muted small">
              Traced means linked, not tested: this shows that the code exists for each requirement, not that it has been independently tested (C4).
            </p>
          </Card>

          <TechnicalDetails summary="Raw graph (for the report)">
            <JsonView value={graph} summary="Open the full graph JSON" />
          </TechnicalDetails>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Application preview
export function HybridPreviewView() {
  const { hybrid, run, latestRunId, checkPreviews, startPreview, stopPreview, gpaCheck } = useHybridRun();
  const preview = hybrid.preview;
  const running = preview?.status === "RUNNING";
  // A preview started from an earlier run shows an earlier version of the app.
  const olderVersion = running && preview.generation_run_id !== latestRunId;
  const check = hybrid.gpaCheck;
  const [docker, setDocker] = useState(null);
  const dockerDown = docker?.available === false;

  useEffect(() => {
    checkPreviews.run().then((result) => setDocker(result?.docker ?? null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page">
      <PageHeader title="Application Preview" />
      <RunBanner run={run} />

      {dockerDown ? (
        <Callout tone="warn" title="Docker is not running">
          The preview runs in Docker containers. Start Docker Desktop, wait until it says it is running, then press Start.
        </Callout>
      ) : null}

      {olderVersion && !startPreview.loading ? (
        <Callout tone="info" title="This preview shows an earlier version of the app">
          It was started from run <code>{preview.generation_run_id}</code>; the current run is <code>{latestRunId}</code>. Replace it to see the current version.
          <div className="button-row">
            <Button onClick={() => startPreview.run()}>Replace with the current version</Button>
          </div>
        </Callout>
      ) : null}

      {running ? (
        <Card title={olderVersion ? "An older version is running" : "Your app is running"} subtitle="Open it in a new tab and use it like a normal website.">
          <div className="button-row">
            <a className="btn btn-primary" href={preview.frontend_url} target="_blank" rel="noreferrer" data-testid="open-generated-app">Open the GPA Calculator</a>
            <Button variant="secondary" onClick={() => gpaCheck.run()} loading={gpaCheck.loading}>Run known GPA check</Button>
            <Button variant="ghost" onClick={() => stopPreview.run()} loading={stopPreview.loading}>Stop</Button>
          </div>
          {check ? (
            <Callout tone={check.passed ? "ok" : "bad"} title={check.passed ? "The app gives the right answer" : "The app gave a different answer"}>
              A known example (4 credits A, 3 credits B+, 2 credits C, 3 credits A-) should give <strong>{check.expected_gpa_text}</strong>;
              the app returned <strong>{check.observed_gpa_text}</strong> ({check.derivation}).
            </Callout>
          ) : null}
          <KeyValues
            items={[
              { label: "App address", value: <a href={preview.frontend_url} target="_blank" rel="noreferrer" data-testid="preview-frontend-url">{preview.frontend_url}</a> },
              { label: "API health", value: <a href={preview.api_health_url} target="_blank" rel="noreferrer" data-testid="preview-api-url">{preview.api_health_url}</a> },
              { label: "Database", value: "PostgreSQL inside Docker, not reachable from outside. Saved calculations disappear when the preview stops." },
              { label: "Started", value: formatSriLankaTime(preview.started_at_utc) },
            ]}
          />
        </Card>
      ) : (
        <Card title="Start the app" subtitle="Builds the generated frontend, backend and database in three disposable Docker containers.">
          <ul className="plain-list">
            <li>The first start takes about a minute.</li>
            <li>Everything stays on this computer (a free local port is picked automatically).</li>
            <li>Nothing is deployed anywhere.</li>
          </ul>
          <div className="button-row">
            <Button onClick={() => startPreview.run()} loading={startPreview.loading}>Start preview</Button>
          </div>
          {startPreview.loading ? (
            <Loading label="Starting the app" startedAt={startPreview.startedAt} note="Docker is building and starting the containers." />
          ) : null}
        </Card>
      )}
      <FriendlyError error={startPreview.error ?? stopPreview.error ?? gpaCheck.error} context="Preview" />

      {running ? (
        <Card title="Things to try">
          <ol className="plain-list">
            <li>Enter modules such as <code>IT1010</code>, 4 credits, grade A, and add a few more.</li>
            <li>Press <strong>Calculate GPA</strong>. The result and the history list update.</li>
            <li>Enter an invalid grade or a credit value that is too large and see the error messages.</li>
            <li>If this run includes the Clear history change, use the <strong>Clear history</strong> button.</li>
          </ol>
        </Card>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ Scoped regeneration (C4 feedback)
// How the project's files fared in one regeneration: changed, re-checked and identical, or not touched at all.
function FileOutcomeBar({ summary }) {
  const total = summary.changedFiles + summary.identicalFiles + summary.untouchedFiles;
  if (!total) return null;
  const parts = [
    ["changed", summary.changedFiles, "Changed"],
    ["identical", summary.identicalFiles, "Regenerated, same content"],
    ["untouched", summary.untouchedFiles, "Not touched"],
  ];
  return (
    <div className="outcome" data-testid="file-outcome">
      <div className="outcome-bar" role="img" aria-label={parts.map(([, count, text]) => `${count} ${text}`).join(", ")}>
        {parts.map(([key, count]) => (count ? <span key={key} className={`outcome-${key}`} style={{ flexGrow: count }}>{count}</span> : null))}
      </div>
      <div className="outcome-legend">
        {parts.map(([key, count, text]) => <span key={key}><i className={`outcome-dot outcome-${key}`} /> {count} {text.toLowerCase()}</span>)}
      </div>
    </div>
  );
}

function ChangeResult({ title, result }) {
  if (!result) return null;
  const summary = describeChange(result);
  return (
    <Callout tone="ok" title={title}>
      <p>
        A new version of the app was created: run <code>{summary.runId}</code>. Only{" "}
        <strong>{summary.modules.length} part{summary.modules.length === 1 ? "" : "s"}</strong> of the project {summary.modules.length === 1 ? "was" : "were"} regenerated; the rest was kept exactly as it was.
      </p>
      <FileOutcomeBar summary={summary} />
      <KeyValues
        items={[
          { label: "Requirements involved", value: <Chips items={summary.requirements} /> },
          { label: "Parts regenerated", value: <Chips tone="info" items={summary.modules} /> },
          { label: "Files whose content changed", value: summary.changedFiles },
          { label: "Files re-checked and identical", value: summary.identicalFiles },
          { label: "Files left untouched (byte for byte)", value: summary.untouchedFiles },
          { label: "Unexpected changes", value: summary.unexpected === 0 ? "none" : summary.unexpected },
          { label: "Independent re-test (C4)", value: summary.retest ?? "—" },
        ]}
      />
      {summary.changedPaths.length ? (
        <TechnicalDetails summary="Which files changed">
          <ul>{summary.changedPaths.map((path) => <li key={path}><code>{path}</code></li>)}</ul>
        </TechnicalDetails>
      ) : null}
    </Callout>
  );
}

const SAMPLE_PROJECT_ID = "PROJECT-GPA-HYBRID-001";

// The changed requirement version, chosen as two C1/C2 files; a package only when both are released 2.x JSON documents.
function changedPackage(files) {
  try {
    const c1 = JSON.parse(files.c1?.text ?? "");
    const c2 = JSON.parse(files.c2?.text ?? "");
    if (!String(c1?.contract_version).startsWith("2.") || !String(c2?.contract_version).startsWith("2.")) return null;
    return { contract_version: c1.contract_version, input_classification: "VALIDATED_CONTRACT_INPUT", c1, c2 };
  } catch {
    return null;
  }
}

function ChangeFilePicker({ label, file, onFile }) {
  return (
    <label className="file-pick-block">
      <span className="muted small">{label}</span>
      <span className="file-pick">
        <span className="btn btn-secondary">{file ? "Choose another file" : "Choose a file"}</span>
        <input
          aria-label={label}
          type="file"
          accept=".json"
          onChange={async (event) => {
            const chosen = event.target.files?.[0];
            event.target.value = "";
            if (chosen) onFile({ name: chosen.name, text: await chosen.text() });
          }}
        />
      </span>
      <span className={`source-file-name${file ? " source-file-ready" : ""}`}>{file?.name ?? "No file selected yet"}</span>
    </label>
  );
}

export function HybridChangeView({ navigate }) {
  const { hybrid, run, overviewReady, applyChange, defectFlow } = useHybridRun({ needOverview: true });
  const [changeFiles, setChangeFiles] = useState({ c1: null, c2: null });
  const changed = changedPackage(changeFiles);
  const sampleProject = run?.manifest?.input?.project_id === SAMPLE_PROJECT_ID;
  return (
    <div className="page">
      <PageHeader
        title="Scoped Regeneration"
        subtitle="When a requirement changes or a tester reports a defect, only the affected parts are regenerated."
      />
      <RunBanner run={run} />

      <Card title="1 · A requirement changes" subtitle="The client approves a new version of one requirement; the design is updated to match.">
        {sampleProject ? (
          <>
            <div className="button-row">
              <Button onClick={() => applyChange.run("gpa-input-req103-v2")} loading={applyChange.loading} disabled={!overviewReady}>
                Change REQ-GPA-103: module code must look like IT1010
              </Button>
              <Button variant="secondary" onClick={() => applyChange.run("gpa-input-req104-v2")} loading={applyChange.loading} disabled={!overviewReady}>
                Change REQ-GPA-104: let the user clear the history
              </Button>
            </div>
            <ul className="what-it-does">
              <li><strong>REQ-GPA-103</strong>: adds a rule that a module code must look like IT1010. Only the parts linked to that requirement are regenerated: the input checks, the form, the API contract and the tests.</li>
              <li><strong>REQ-GPA-104</strong>: adds a Clear history feature. It reaches the service, storage, routes and the history list, so more parts are regenerated.</li>
            </ul>
          </>
        ) : null}
        <p className="small">
          {sampleProject ? "Or use your own changed version:" : "Choose the changed version of your C1 and C2 files (same project, a newer SRS and design version):"}
        </p>
        <div className="grid grid-2" data-testid="change-files">
          <ChangeFilePicker label="Changed C1 file" file={changeFiles.c1} onFile={(file) => setChangeFiles((current) => ({ ...current, c1: file }))} />
          <ChangeFilePicker label="Changed C2 file" file={changeFiles.c2} onFile={(file) => setChangeFiles((current) => ({ ...current, c2: file }))} />
        </div>
        <div className="button-row">
          <Button onClick={() => applyChange.run(changed)} loading={applyChange.loading} disabled={!overviewReady || !changed}>
            Apply the changed version
          </Button>
        </div>
        <p className="muted small">Each change builds on the latest version of the run, so try one change per generated run.</p>
        {applyChange.loading ? <Loading label="Regenerating the affected parts" startedAt={applyChange.startedAt} /> : null}
        <FriendlyError error={applyChange.error} context="Requirement change" onGenerate={() => navigate?.("generation")} />
        <ChangeResult title="Requirement change applied" result={hybrid.change} />
      </Card>

      <Card title="2 · A tester reports a defect" subtitle="A defect report in the C4 format points at one module of the current version; only that module is repaired.">
        <div className="button-row">
          <Button variant="secondary" onClick={() => defectFlow.run()} loading={defectFlow.loading}>Inject a fault and repair it</Button>
        </div>
        <ol className="what-it-does what-it-does-steps">
          <li>A known fault is injected into one module of the current version (controlled fault injection).</li>
          <li>A defect report in the C4 contract format names the failing test, the module and the requirement it traces to.</li>
          <li>Only that module is regenerated and checked again; the rest stays exactly as it was. C4 then re-tests the new version.</li>
        </ol>
        {defectFlow.loading ? <Loading label="Injecting the fault and repairing it" startedAt={defectFlow.startedAt} /> : null}
        <FriendlyError error={defectFlow.error} context="Defect repair" onGenerate={() => navigate?.("generation")} />
        {hybrid.defect ? (
          <Callout tone="info" title="Defect report (C4 contract format)">
            <KeyValues
              items={[
                { label: "Failing test", value: hybrid.defect.report?.failing_test_id ?? "—" },
                { label: "What the tester saw", value: withoutPrefix(hybrid.defect.report?.observed_evidence) },
                { label: "Likely cause", value: withoutPrefix(hybrid.defect.report?.inferred_cause) },
                { label: "Module", value: moduleLabel(hybrid.defect.report?.module_id) },
                { label: "Test hook", value: hybrid.defect.report?.test_seam_id ?? "—" },
                { label: "Traces to", value: <Chips items={hybrid.defect.report?.traceability_refs ?? []} /> },
                { label: "Severity", value: hybrid.defect.report?.severity ?? "—" },
              ]}
            />
            <p className="muted small">Source: a test input written in the C4 report format, because the C4 component is not connected yet.</p>
          </Callout>
        ) : null}
        <ChangeResult title="Defect repaired" result={hybrid.defect} />
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Readiness
function GateRow({ title, status, label, detail }) {
  return { id: title, title, status, label, detail };
}

export function HybridReadinessView() {
  const { hybrid, run, overview, latestRunId } = useHybridRun({ needOverview: true });
  const previewCurrent = hybrid.preview?.status === "RUNNING" && hybrid.preview.generation_run_id === latestRunId;
  const contract = hybrid.contract;
  const design = verificationCounts(run?.verification?.design_to_code);
  const architecture = verificationCounts(run?.verification?.architecture);
  const rows = [
    GateRow({ title: "Inputs accepted", status: run?.status === "ACCEPTED" ? "SATISFIED" : "BLOCKED", label: run?.status ?? "—", detail: "Client-approved requirements and a released design that match each other." }),
    GateRow({ title: "Code matches the design", status: design.fail ? "BLOCKED" : design.review ? "REVIEW_REQUIRED" : "SATISFIED", label: `${design.pass} pass · ${design.review} review · ${design.fail} fail`, detail: "Classes, methods, fields, endpoints and tables compared with the released UML." }),
    GateRow({ title: "Architecture rules", status: architecture.fail ? "BLOCKED" : architecture.review ? "REVIEW_REQUIRED" : "SATISFIED", label: `${architecture.pass} pass · ${architecture.review} review · ${architecture.fail} fail`, detail: "Route → controller → service → repository layering and allowed dependencies." }),
    GateRow({ title: "Traceability", status: hybrid.trace ? "SATISFIED" : "PENDING", label: hybrid.trace ? `graph v${hybrid.trace.graph?.version}` : "not loaded", detail: "Every requirement linked to design, code, API, database and test hooks." }),
    GateRow({ title: "Local preview", status: previewCurrent ? "SATISFIED" : "PENDING", label: previewCurrent ? "RUNNING" : hybrid.preview?.status === "RUNNING" ? "older version running" : "not started", detail: "The current version of the app was started in Docker on this computer." }),
    GateRow({ title: "Independent testing (C4)", status: "PENDING", label: "not integrated", detail: "Only the independent testing component can say the app is ready." }),
    GateRow({ title: "Deployment", status: "BLOCKED", label: "blocked", detail: "Needs an independent sign-off (readiness signal) for this exact version of the app." }),
  ];

  return (
    <div className="page">
      <PageHeader title="Readiness" />

      <Card title="Run evidence" subtitle="What this run was generated from and with.">
        <KeyValues
          items={[
            { label: "Input contract", value: contract ? <span><StatusBadge status={contract.status === "ACCEPTED" ? "PASS" : "FAIL"} label={contract.status} /> {contract.classification ?? contract.input_classification}</span> : "—" },
            { label: "Project", value: contract ? `${contract.project_id} · ${contract.srs_version} / ${contract.uml_version}` : run.manifest.input.project_id },
            { label: "Knowledge Base", value: overview ? <span>{overview.knowledge_base.kb_version} <Hash value={overview.knowledge_base.kb_digest_sha256} /></span> : "—" },
            { label: "Rule set", value: overview ? <span>{overview.rule_set.rule_set_version} · {overview.rule_set.rules.length} rules</span> : "—" },
            { label: "Grading policy", value: overview?.knowledge_base?.gpa_policy ? `${overview.knowledge_base.gpa_policy.policy_id} v${overview.knowledge_base.gpa_policy.policy_version}` : "—" },
            { label: "Stack", value: `${run.manifest.stack.stack_id} (${run.manifest.stack.frontend} + ${run.manifest.stack.backend} + ${run.manifest.stack.database})` },
            { label: "Stack reason", value: `${run.manifest.stack.reason} [${run.manifest.stack.criteria_source}]` },
            { label: "Generation run", value: run.generation_run_id },
            { label: "Artifact digest", value: <Hash value={run.manifest.artifact_digest_sha256} length={20} /> },
          ]}
        />
        <TechnicalDetails summary={`Selected rule IDs (${run.manifest.rule_set.selected_rules.length})`}>
          <p className="mono">{run.manifest.rule_set.selected_rules.join("  ")}</p>
        </TechnicalDetails>
        <TechnicalDetails summary={`RAG best-practice chunks (${ragRows(run.manifest).length}) — guidance only, cannot override requirements, UML or policy`}>
          <Table
            dense
            columns={[
              { key: "module", header: "Module" },
              { key: "chunk", header: "Chunk" },
              { key: "version", header: "Version" },
              { key: "score", header: "Score" },
              { key: "applied", header: "In prompt", render: (row) => (row.applied ? "yes" : "no") },
            ]}
            rows={ragRows(run.manifest)}
            rowKey={(row) => row.key}
          />
        </TechnicalDetails>
        <div className="button-row">
          <a className="btn btn-secondary" href={`/api/v1/hybrid/runs/${latestRunId}/audit`} target="_blank" rel="noreferrer noopener" data-testid="audit-report">
            Open audit report
          </a>
        </div>
      </Card>

      <Card title="Checklist">
        <Table
          dense
          rows={rows}
          rowKey={(row) => row.id}
          columns={[
            { key: "title", header: "Check", render: (row) => <strong>{row.title}</strong> },
            { key: "status", header: "Result", render: (row) => <StatusBadge status={row.status} label={row.label} /> },
            { key: "detail", header: "What it means" },
          ]}
        />
      </Card>
    </div>
  );
}
