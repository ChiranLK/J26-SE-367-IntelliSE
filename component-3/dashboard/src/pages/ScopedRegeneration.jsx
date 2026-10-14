import { useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { CodePreview } from "../components/CodePreview.jsx";
import { Badge, Button, Callout, Card, ErrorPanel, Hash, JsonView, KeyValues, Loading, ModeBadge, PageHeader, SimBanner, SimulatedBadge, Stat, StatusBadge, Table } from "../components/ui.jsx";
import { formatBytes, formatDuration, formatTime } from "../lib/format.js";
import { buildDefectReport, buildScopedRequest } from "../lib/requests.js";
import { useBackend } from "../state/backend.jsx";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";

const reasonList = (codes) => (codes?.length ? codes.map((code) => <div key={code}><code>{code}</code></div>) : "none");

function Impact({ impact }) {
  const excluded = impact.defects.flatMap((defect) => defect.exclusions.map((item) => ({ ...item, defect_id: defect.defect_id })));
  const excludedLinks = impact.defects.flatMap((defect) => defect.excluded_links.map((item) => ({ ...item, defect_id: defect.defect_id })));
  return (
    <div data-testid="impact-result">
      <div className="result-head">
        <StatusBadge status={impact.status} />
        <span className="small">Graph v{impact.graph_version} · automatic scope limit {impact.automatic_scope_limit} module(s)</span>
        <Badge tone="sim">expectations NOT independently reviewed</Badge>
      </div>
      <div className="small">Reason codes: {reasonList(impact.reason_codes)}</div>

      <h3 className="subhead">Selected modules ({impact.selected_modules.length})</h3>
      <Table
        dense
        empty="No module was selected automatically. The defect needs researcher review."
        rowKey={(row) => row.node_id}
        rows={impact.selected_modules}
        columns={[
          { key: "relative_path", header: "Module", render: (row) => <code>{row.relative_path}</code> },
          { key: "evidence_channels", header: "Evidence", render: (row) => row.evidence_channels.map((item) => <div key={item}><code>{item}</code></div>) },
          { key: "location_corroborated", header: "Location corroborated", render: (row) => (row.location_corroborated ? "yes" : "no") },
          { key: "reason_codes", header: "Reasons", render: (row) => reasonList(row.reason_codes) },
          { key: "defect_ids", header: "Defects", render: (row) => row.defect_ids.join(", ") },
        ]}
      />
      {impact.selected_modules.length ? (
        <details className="json-view">
          <summary>Typed graph paths that justify the selection</summary>
          {impact.selected_modules.map((module) => (
            <div key={module.node_id} className="path-block">
              <strong>{module.relative_path}</strong>
              {module.paths.map((path, index) => (
                <ol key={`${path.channel}-${index}`} className="small">
                  <li><em>{path.channel}</em></li>
                  {path.steps.map((step) => (
                    <li key={step.link_id}><code>{step.source_node_id}</code> —{step.relation_type}→ <code>{step.target_node_id}</code> <span className="muted">({step.mapping_rule_id})</span></li>
                  ))}
                </ol>
              ))}
            </div>
          ))}
        </details>
      ) : null}

      <h3 className="subhead">Excluded modules</h3>
      <Table
        dense
        empty="No exclusions recorded."
        rowKey={(row) => `${row.defect_id}-${row.node_id}`}
        rows={excluded}
        columns={[
          { key: "defect_id", header: "Defect" },
          { key: "relative_path", header: "Module", render: (row) => <code>{row.relative_path}</code> },
          { key: "reason_codes", header: "Why excluded", render: (row) => reasonList(row.reason_codes) },
        ]}
      />
      {excludedLinks.length ? (
        <>
          <h3 className="subhead">Links excluded because they need review</h3>
          <Table
            dense
            rowKey={(row) => `${row.defect_id}-${row.link_id}`}
            rows={excludedLinks}
            columns={[
              { key: "link_id", header: "Link", render: (row) => <code>{row.link_id}</code> },
              { key: "relation_type", header: "Relation" },
              { key: "details", header: "Details" },
            ]}
          />
        </>
      ) : null}
    </div>
  );
}

function PatchedView({ result }) {
  const [runs, setRuns] = useState(null);
  const [path, setPath] = useState(result.patches[0]?.relative_path ?? null);
  const load = useAction(async () => {
    const versioning = result.artifact_versioning;
    const before = await api.workspaceRun(versioning.source_workspace_relative_path);
    const after = await api.workspaceRun(versioning.new_workspace_relative_path);
    setRuns({ before, after });
  });
  if (!result.artifact_versioning || result.patches.length === 0) return null;
  return (
    <Card title="Before and after (safe read-only preview)" subtitle="Both workspaces are verified against their manifests before display. Nothing is executed.">
      <div className="chip-row">
        {result.patches.map((patch) => (
          <button key={patch.relative_path} type="button" className={`chip chip-button${path === patch.relative_path ? " chip-active" : ""}`} onClick={() => setPath(patch.relative_path)}>
            {patch.relative_path}
          </button>
        ))}
      </div>
      {!runs ? (
        <div className="button-row">
          <Button variant="secondary" onClick={() => load.run()} loading={load.loading}>Load both workspaces for preview</Button>
        </div>
      ) : null}
      <ErrorPanel error={load.error} context="Workspace preview" />
      {runs ? (
        <div className="grid grid-2">
          <CodePreview run={runs.before} path={path} title="Before (source run, preserved)" />
          <CodePreview run={runs.after} path={path} title="After (new run)" />
        </div>
      ) : null}
    </Card>
  );
}

function Result({ entry }) {
  const { result } = entry;
  const versioning = result.artifact_versioning;
  const graph = result.graph_versioning;
  const preservation = result.preservation;
  const handoff = result.c4_retest_handoff;
  const mode = result.model_evidence_class === "MOCKED_TEST_DOUBLE" ? "MOCK" : "REAL_LOCAL_OLLAMA";
  return (
    <div data-testid="regeneration-result">
      <div className="result-head">
        <StatusBadge status={result.status} />
        <ModeBadge mode={mode} />
        <span className="muted small">{formatTime(entry.at)} · {formatDuration(entry.durationMs)}</span>
      </div>
      {result.status !== "PATCHED_PENDING_INDEPENDENT_RETEST" ? (
        <Callout tone={result.status === "FAILED" ? "bad" : "warn"} title={result.status === "FAILED" ? "The service reported FAILED" : "Review required"}>
          Nothing was changed in the source run. Reasons: {reasonList(result.reason_codes)}
          {result.escalation ? <div className="small">Required action: {result.escalation.required_action} ({result.escalation.attempts_made}/{result.escalation.attempt_limit} attempts)</div> : null}
        </Callout>
      ) : (
        <div className="small">Reasons: {reasonList(result.reason_codes)}</div>
      )}
      <Callout tone="sim" title="Repair success: NOT EVALUATED">
        {result.metrics.repair_success.replaceAll("_", " ")}. C3 can only claim that a scoped patch was applied and
        structurally inspected; it has not run any test. c4_testing_claim = {String(result.c4_testing_claim)}.
      </Callout>

      <div className="stats">
        <Stat label="Patched modules" value={result.patches.length} />
        <Stat label="Unchanged files" value={preservation ? preservation.unchanged_file_count : "–"} tone="ok" />
        <Stat label="Collateral edits" value={preservation ? preservation.collateral_edit_count : "–"} tone={preservation?.collateral_edit_count ? "bad" : undefined} />
        <Stat label="Model calls" value={result.metrics.llm_call_count} />
        <Stat label="Rejected attempts" value={result.metrics.rejected_attempt_count} />
      </div>

      {versioning ? (
        <div className="grid grid-2">
          <Card title="Artifact versions (old → new)">
            <KeyValues
              items={[
                { label: "Source run", value: <code>{versioning.source_generation_run_id}</code> },
                { label: "New run", value: <code>{versioning.new_generation_run_id}</code> },
                { label: "Old artifact digest", value: <Hash value={versioning.source_artifact_digest_sha256} length={24} /> },
                { label: "New artifact digest", value: <Hash value={versioning.new_artifact_digest_sha256} length={24} /> },
                { label: "Digests differ", value: versioning.source_artifact_digest_sha256 !== versioning.new_artifact_digest_sha256 ? "yes" : "NO" },
                { label: "Source run preserved", value: String(versioning.source_run_preserved) },
              ]}
            />
          </Card>
          {graph ? (
            <Card title={`Graph v${graph.base_graph_version} → v${graph.new_graph_version}`}>
              <KeyValues
                items={[
                  { label: `v${graph.base_graph_version} digest`, value: <Hash value={graph.base_graph_content_digest_sha256} length={24} /> },
                  { label: `v${graph.new_graph_version} digest`, value: <Hash value={graph.new_graph_content_digest_sha256} length={24} /> },
                  { label: "Changed artifacts", value: graph.change_report.artifacts.changed.join(", ") || "none" },
                  { label: "Unchanged artifacts", value: graph.change_report.artifacts.unchanged.length },
                  { label: "Links preserved / revalidated", value: `${graph.change_report.preserved_link_ids.length} / ${graph.change_report.revalidated_link_ids.length}` },
                  { label: "Links added / retired", value: `${graph.change_report.added_link_ids.length} / ${graph.change_report.retired_link_ids.length}` },
                ]}
              />
            </Card>
          ) : null}
        </div>
      ) : null}

      {preservation ? (
        <Card title="Unchanged-file preservation" subtitle={preservation.all_unselected_files_byte_identical ? "Every unselected file is byte-identical to the source run." : "VIOLATION: an unselected file changed."}>
          <Table
            dense
            rowKey={(row) => row.relative_path}
            rows={preservation.entries}
            columns={[
              { key: "relative_path", header: "File", render: (row) => <code>{row.relative_path}</code> },
              { key: "selected", header: "Selected for patch", render: (row) => (row.selected ? <Badge tone="warn">patched</Badge> : "no") },
              { key: "byte_identical", header: "Byte identical", render: (row) => <StatusBadge status={row.byte_identical ? "PASS" : row.selected ? "REVIEW_REQUIRED" : "FAIL"} label={row.byte_identical ? "identical" : "changed"} /> },
              { key: "source_sha256", header: "Old hash", render: (row) => <Hash value={row.source_sha256} /> },
              { key: "new_sha256", header: "New hash", render: (row) => <Hash value={row.new_sha256} /> },
            ]}
          />
        </Card>
      ) : null}

      <div className="grid grid-2">
        <Card title="Patches">
          <Table
            dense
            empty="No patch was accepted."
            rowKey={(row) => row.relative_path}
            rows={result.patches}
            columns={[
              { key: "relative_path", header: "Module", render: (row) => <code>{row.relative_path}</code> },
              { key: "diff", header: "Lines", render: (row) => `+${row.lines_added} / −${row.lines_removed}` },
              { key: "size", header: "Size", render: (row) => `${formatBytes(row.source_size_bytes)} → ${formatBytes(row.new_size_bytes)}` },
              { key: "attempts_used", header: "Attempts" },
            ]}
          />
        </Card>
        <Card title="Patch attempts">
          <Table
            dense
            empty="No model attempt was made."
            rowKey={(row) => `${row.relative_path}-${row.attempt_number}`}
            rows={result.patch_attempts}
            columns={[
              { key: "attempt_number", header: "#" },
              { key: "relative_path", header: "Module", render: (row) => <code>{row.relative_path}</code> },
              { key: "accepted", header: "Result", render: (row) => (row.accepted ? <StatusBadge status="PASS" label="accepted" /> : <StatusBadge status="FAIL" label={row.rejection_code ?? "rejected"} />) },
              { key: "model_identifier", header: "Model" },
              { key: "client_inference_latency_ms", header: "Latency", render: (row) => formatDuration(row.client_inference_latency_ms) },
            ]}
          />
          <p className="muted small">Prompt template: {result.patch_attempts[0]?.prompt_template_version ?? "n/a"}</p>
        </Card>
      </div>

      {result.structural_verification ? (
        <Card title="C3 structural verification of the new run (static, not C4)">
          <div className="result-head">
            <StatusBadge status={result.structural_verification.overall_status} />
            <span className="small">
              {result.structural_verification.summary.pass_count} pass · {result.structural_verification.summary.fail_count} fail · {result.structural_verification.summary.review_required_count} review required
            </span>
          </div>
        </Card>
      ) : null}

      <Card title="C4 re-test handoff" tone="sim">
        {handoff ? (
          <>
            <div className="result-head">
              <StatusBadge status="PENDING" label={`C4 retest ${handoff.retest_status}`} />
              <Badge tone="neutral">independent C4 evidence: {handoff.independent_c4_evidence}</Badge>
              <Badge tone="neutral">{handoff.repair_verification.replaceAll("_", " ")}</Badge>
            </div>
            <KeyValues
              items={[
                { label: "Requirements to retest", value: handoff.requirement_ids_to_retest.join(", ") },
                { label: "Failing tests to rerun", value: handoff.failing_tests_to_rerun.join(", ") },
                { label: "Changed modules", value: handoff.changed_modules.join(", ") },
                { label: "Unchanged modules", value: handoff.unchanged_module_count },
                { label: "Required C4 actions", value: handoff.required_c4_actions.map((item) => <div key={item}>{item}</div>) },
              ]}
            />
          </>
        ) : (
          <p className="muted small">No handoff was produced because the run did not reach a patched, verified state. C4 retest is still PENDING.</p>
        )}
      </Card>

      <PatchedView key={result.artifact_versioning?.new_generation_run_id ?? "none"} result={result} />
      <JsonView value={result} summary="Full regeneration result as returned by the API" />
    </div>
  );
}

export default function ScopedRegeneration() {
  const { session, set, update } = useSession();
  const { overview } = useBackend();
  const scoped = session.scoped;
  const scenarios = session.fixtures.defectScenarios?.payload?.scenarios ?? [];
  const scenario = scenarios.find((item) => item.scenario_id === scoped.scenarioId) ?? null;
  const baseline = scoped.baseline;
  const [viewIndex, setViewIndex] = useState(null);
  const [lastRunMode, setLastRunMode] = useState(null);
  const ollama = overview?.ollama;
  const ollamaOk = ollama?.reachable && ollama?.model_installed;

  const patchScoped = (changes) => update("scoped", (current) => ({ ...current, ...changes }));

  const loadScenarios = useAction(async () => {
    const envelope = await api.fixture("defect-scenarios");
    set("fixtures", { ...session.fixtures, defectScenarios: envelope });
    if (!scoped.scenarioId) patchScoped({ scenarioId: envelope.payload.scenarios[0]?.scenario_id ?? null });
  });

  const createBaseline = useAction(async () => {
    const created = await api.createBaseline();
    patchScoped({ baseline: created, impact: null });
    setViewIndex(null);
  });

  const baselineRunId = baseline?.generation_run.manifest.generation_run_id;
  const reportRef = useMemo(() => `SIM-DEFECT-REPORT-${Date.now()}`, [scoped.scenarioId, baselineRunId]);
  const request = useMemo(() => {
    if (!scenario || !baseline) return null;
    const defectReport = buildDefectReport({
      scenario,
      manifest: baseline.generation_run.manifest,
      graphVersion: baseline.graph_snapshot.graph_version,
      reportId: reportRef,
    });
    return buildScopedRequest({ defectReport, baseline });
  }, [scenario, baseline, reportRef]);

  const consumed = scoped.runs.some((entry) => entry.baselineRunId === baselineRunId && entry.result.graph_versioning);

  const previewImpact = useAction(async () => {
    const report = await api.impactSelection(request);
    patchScoped({ impact: { scenarioId: scenario.scenario_id, baselineRunId, report } });
  });

  const regenerate = useAction(async (mode) => {
    setLastRunMode(mode);
    const started = Date.now();
    const result = await api.scopedRegeneration(mode, request);
    update("scoped", (current) => ({
      ...current,
      runs: [
        ...current.runs,
        { mode, result, durationMs: Date.now() - started, at: new Date().toISOString(), baselineRunId, scenarioId: scenario.scenario_id },
      ],
    }));
    setViewIndex(null);
  });

  const runs = scoped.runs;
  const shownIndex = viewIndex ?? runs.length - 1;
  const shown = runs[shownIndex] ?? null;
  const impact = scoped.impact && scoped.impact.scenarioId === scoped.scenarioId && scoped.impact.baselineRunId === baselineRunId ? scoped.impact.report : null;

  return (
    <div className="page">
      <PageHeader
        title="Scoped Regeneration"
        subtitle="Defect feedback to graph-selected patch scope, using the real FR-C3-06/07 services."
        badges={
          <>
            <SimulatedBadge>SIMULATED C4 DEFECT</SimulatedBadge>
            <Badge tone="neutral">C4 retest PENDING</Badge>
          </>
        }
      />
      <SimBanner>
        Component 4 is not integrated. Defects below are authored fixtures, and the baseline code contains a deliberately
        injected defect generated by a test-double model. No real test has failed or passed.
      </SimBanner>

      <Card
        title="1 · Simulated C4 defect scenarios"
        subtitle="GET /api/v1/demo/fixtures/defect-scenarios"
        actions={<Button onClick={() => loadScenarios.run()} loading={loadScenarios.loading}>{scenarios.length ? "Reload scenarios" : "Load SIMULATED defect fixture"}</Button>}
      >
        <ErrorPanel error={loadScenarios.error} context="Load defect scenarios" />
        {scenarios.length ? (
          <>
            <p className="small">{session.fixtures.defectScenarios.notice}</p>
            <Table
              dense
              rowKey={(row) => row.scenario_id}
              selectedKey={scoped.scenarioId}
              onRowClick={(row) => patchScoped({ scenarioId: row.scenario_id, impact: null })}
              rows={scenarios}
              columns={[
                { key: "scenario_id", header: "Scenario", render: (row) => <code>{row.scenario_id}</code> },
                { key: "description", header: "Description" },
                { key: "expected_status", header: "Simulated expectation", render: (row) => <StatusBadge status={row.expected_status} /> },
                { key: "defects", header: "Category", render: (row) => row.defects.map((item) => item.category).join(", ") },
              ]}
            />
          </>
        ) : (
          <p className="muted small">Not loaded.</p>
        )}
        {scenario ? (
          <details className="json-view" open>
            <summary>Selected defect (SIMULATED)</summary>
            {scenario.defects.map((defect) => (
              <KeyValues
                key={defect.defect_id}
                items={[
                  { label: "Defect", value: `${defect.defect_id} · ${defect.severity}` },
                  { label: "Title", value: defect.title },
                  { label: "Requirements", value: defect.affected_requirement_ids.join(", ") },
                  { label: "Failing tests (simulated)", value: defect.failing_tests.map((test) => test.test_case_id).join(", ") },
                  { label: "API operations", value: defect.api_operation_ids?.join(", ") },
                  { label: "Claimed location", value: defect.location ? `${defect.location.relative_path} · ${defect.location.symbol ?? ""}` : "none supplied" },
                  { label: "Explanation", value: defect.explanation },
                ]}
              />
            ))}
          </details>
        ) : null}
      </Card>

      <Card
        title="2 · Simulated defective baseline"
        subtitle="POST /api/v1/demo/scoped-regeneration/baseline · real generation run and real graph; the service module is a defective test-double output"
        actions={<Button onClick={() => createBaseline.run()} loading={createBaseline.loading}>{baseline ? "Create a fresh baseline" : "Create baseline"}</Button>}
      >
        {createBaseline.loading ? <Loading label="Generating baseline run and graph" startedAt={createBaseline.startedAt} /> : null}
        <ErrorPanel error={createBaseline.error} context="Baseline" />
        {baseline ? (
          <>
            <div className="result-head">
              <Badge tone="sim">{baseline.classification}</Badge>
              <Badge tone="sim">{baseline.model_evidence_class}</Badge>
            </div>
            <p className="small">{baseline.notice}</p>
            <KeyValues
              items={[
                { label: "Generation run ID", value: <code>{baselineRunId}</code> },
                { label: "Artifact digest", value: <Hash value={baseline.generation_run.manifest.artifact_digest_sha256} length={24} /> },
                { label: "Graph version", value: `v${baseline.graph_snapshot.graph_version}` },
                { label: "Graph digest", value: <Hash value={baseline.graph_snapshot.graph_content_digest_sha256} length={24} /> },
                { label: "Injected defect module", value: <code>{baseline.injected_defect_module}</code> },
              ]}
            />
            <CodePreview run={baseline.generation_run} path={baseline.injected_defect_module} title="Injected defective module (read-only)" />
          </>
        ) : (
          <p className="muted small">Not created.</p>
        )}
      </Card>

      <Card
        title="3 · Impact selection"
        subtitle="POST /api/v1/impact-selections · read-only, no model call"
        actions={<Button onClick={() => previewImpact.run()} loading={previewImpact.loading} disabled={!request}>Preview impact selection</Button>}
      >
        {!request ? <p className="muted small">Load the defect fixture and create a baseline first.</p> : null}
        {request ? <p className="small">Defect report <code>{request.defect_report.defect_report_id}</code> is built from the real baseline: run <Hash value={request.defect_report.source_generation_run_id} length={8} />, graph v{request.defect_report.source_graph_version}.</p> : null}
        {previewImpact.loading ? <Loading label="Selecting scope" startedAt={previewImpact.startedAt} /> : null}
        <ErrorPanel error={previewImpact.error} context="Impact selection" />
        {impact ? <Impact impact={impact} /> : null}
      </Card>

      <Card title="4 · Scoped regeneration" subtitle="Two clearly separated modes. Both call the same pipeline; only the model differs.">
        <div className="mode-grid">
          <div className="mode-card">
            <div>
              <strong>MOCK model</strong> <ModeBadge mode="MOCK" />
              <p className="muted small">POST /api/v1/demo/scoped-regenerations/mock. A fixed repaired service file stands in for the model. It checks the pipeline only and repairs just the service scenario; other scenarios fail visibly.</p>
              <Button onClick={() => regenerate.run("MOCK")} loading={regenerate.loading && lastRunMode === "MOCK"} disabled={!request || regenerate.loading || consumed}>Run MOCK regeneration</Button>
            </div>
          </div>
          <div className="mode-card">
            <div>
              <strong>REAL local Ollama</strong> <ModeBadge mode="REAL_LOCAL_OLLAMA" />
              <p className="muted small">POST /api/v1/scoped-regenerations. The configured local model proposes the patch. Output quality is unknown and may be rejected by the guards.</p>
              <Button onClick={() => regenerate.run("REAL_LOCAL_OLLAMA")} loading={regenerate.loading && lastRunMode === "REAL_LOCAL_OLLAMA"} disabled={!request || regenerate.loading || consumed}>Run REAL Ollama regeneration</Button>
              {!ollamaOk ? <div className="text-warn small">Ollama is not ready: {ollama?.detail ?? "status unknown"}</div> : null}
            </div>
          </div>
        </div>
        {consumed ? (
          <Callout tone="info" title="This baseline has been repaired">
            Its graph version advanced, so the defect report is now stale by design. Create a fresh baseline to run another mode.
          </Callout>
        ) : null}
        {regenerate.loading ? (
          <Loading
            label={`Running ${lastRunMode} regeneration`}
            startedAt={regenerate.startedAt}
            note={lastRunMode === "REAL_LOCAL_OLLAMA" ? "Synchronous call. Local inference can take from tens of seconds to several minutes." : undefined}
          />
        ) : null}
        <ErrorPanel error={regenerate.error} context={`${lastRunMode ?? ""} regeneration`} />
      </Card>

      {runs.length ? (
        <>
          <Card title="Runs in this session">
            <Table
              dense
              rowKey={(_, index) => index}
              selectedKey={shownIndex}
              onRowClick={(row) => setViewIndex(runs.indexOf(row))}
              rows={runs}
              columns={[
                { key: "n", header: "#", render: (row) => runs.indexOf(row) + 1 },
                { key: "mode", header: "Model", render: (row) => <ModeBadge mode={row.mode} /> },
                { key: "scenario", header: "Scenario", render: (row) => <code>{row.scenarioId.slice(0, 11)}</code> },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={row.result.status} /> },
                { key: "dur", header: "Time", render: (row) => formatDuration(row.durationMs) },
              ]}
            />
          </Card>
          {shown ? <Result entry={shown} /> : null}
        </>
      ) : null}
    </div>
  );
}
