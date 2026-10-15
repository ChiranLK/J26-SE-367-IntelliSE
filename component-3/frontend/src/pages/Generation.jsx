import { useState } from "react";
import { api } from "../api/endpoints.js";
import { CodePreview } from "../components/CodePreview.jsx";
import { Badge, Button, Callout, Card, ErrorPanel, Hash, JsonView, KeyValues, Loading, OriginBadge, PageHeader, SimulatedBadge, Stat, StatusBadge, Table } from "../components/ui.jsx";
import { formatBytes, formatDuration } from "../lib/format.js";
import { buildGenerationRequest, buildStructuralRequest } from "../lib/requests.js";
import { useBackend } from "../state/backend.jsx";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";

const MODES = [
  { id: "TEMPLATE_ONLY", label: "TEMPLATE_ONLY", help: "Deterministic C3 templates only. No model call." },
  { id: "LOCAL_LLM", label: "LOCAL_LLM", help: "The business-logic module is written by the local Ollama model; everything else stays templated." },
];

export default function Generation({ navigate }) {
  const { session, set } = useSession();
  const { overview } = useBackend();
  const [mode, setMode] = useState("TEMPLATE_ONLY");
  const [workspaceName, setWorkspaceName] = useState("demo-task-management");
  const [previewPath, setPreviewPath] = useState(null);

  const generationContext = session.validation?.ok ? session.validation.generationContext : null;
  const approved = session.approval?.status === "APPROVED_FOR_MVP_GENERATION";
  const ready = Boolean(generationContext && session.designContext && session.stackReport && approved);
  const stored = session.generationRun;
  const run = stored?.run;
  const ollama = overview?.ollama;
  const ollamaOk = ollama?.reachable && ollama?.model_installed;

  const generate = useAction(async () => {
    const request = buildGenerationRequest({
      generationContext,
      designContext: session.designContext,
      stackReport: session.stackReport,
      approval: session.approval,
      mode,
      workspaceName,
    });
    const started = Date.now();
    const result = await api.generate(request);
    set("generationRun", { run: result, mode, durationMs: Date.now() - started, at: new Date().toISOString() });
    set("structural", null);
    set("graph", null);
    setPreviewPath(null);
  });

  const structural = useAction(async () => {
    const report = await api.structuralVerification(buildStructuralRequest({ run, designContext: session.designContext }));
    set("structural", report);
  });

  const files = run?.manifest.files ?? [];
  const templateCount = files.filter((file) => file.origin === "TEMPLATE").length;
  const llmCount = files.filter((file) => file.origin === "LOCAL_LLM").length;
  const manifest = run?.manifest;
  const llm = manifest?.llm_inference;

  return (
    <div className="page">
      <PageHeader
        title="Code Generation"
        subtitle="Generate the React + Node.js MVP workspace with the real FR-C3-03/04 service. Generated code is only written and displayed; it is never installed or run."
        badges={<SimulatedBadge>SIMULATED C1/C2 INPUT</SimulatedBadge>}
      />

      {!ready ? (
        <Callout tone="warn" title="Approved stack required">
          Generation needs validated input, a design context, a stack selection, and an explicit approval.
          The backend enforces the same gate.{" "}
          <button type="button" className="link-button" onClick={() => navigate(generationContext ? "design" : "inputs")}>
            Open the previous step
          </button>
        </Callout>
      ) : null}

      <Card title="Generation settings" subtitle="POST /api/v1/generation-runs">
        <div className="mode-grid">
          {MODES.map((item) => (
            <label key={item.id} className={`mode-card${mode === item.id ? " mode-active" : ""}`}>
              <input type="radio" name="mode" checked={mode === item.id} onChange={() => setMode(item.id)} />
              <div>
                <strong>{item.label}</strong> {item.id === "LOCAL_LLM" ? <Badge tone="llm">uses local Ollama</Badge> : <Badge tone="info">templates</Badge>}
                <div className="muted small">{item.help}</div>
              </div>
            </label>
          ))}
        </div>
        {mode === "LOCAL_LLM" && !ollamaOk ? (
          <Callout tone="warn" title="Ollama is not ready">
            {ollama ? ollama.detail : "The Ollama status is unknown because the API has not answered."} The request will
            still be sent so you can see the real backend error.
          </Callout>
        ) : null}
        <div className="form-grid">
          <label>
            Workspace name
            <input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} pattern="^[a-z0-9][a-z0-9._-]*$" />
          </label>
        </div>
        <div className="button-row">
          <Button onClick={() => generate.run()} loading={generate.loading} disabled={!ready}>
            Generate with {mode}
          </Button>
        </div>
        {generate.loading ? (
          <Loading
            label={`Generating (${mode})`}
            startedAt={generate.startedAt}
            note={mode === "LOCAL_LLM" ? "The API call is synchronous, so no incremental progress is reported. Local model inference commonly takes tens of seconds." : "The API call is synchronous and normally finishes in under a second."}
          />
        ) : null}
        <ErrorPanel error={generate.error} context="Generation" />
      </Card>

      {run ? (
        <>
          <div className="stats">
            <Stat label="Files generated" value={files.length} />
            <Stat label="TEMPLATE origin" value={templateCount} tone="info" />
            <Stat label="LOCAL_LLM origin" value={llmCount} tone="llm" />
            <Stat label="Execution status" value={manifest.execution_status.replaceAll("_", " ")} hint="Generated code was never run" />
            <Stat label="Request time" value={formatDuration(stored.durationMs)} />
          </div>

          <div className="grid grid-2">
            <Card title="Run evidence">
              <KeyValues
                items={[
                  { label: "Generation run ID", value: <code>{manifest.generation_run_id}</code> },
                  { label: "Mode", value: <Badge tone={manifest.generation_mode === "LOCAL_LLM" ? "llm" : "info"}>{manifest.generation_mode}</Badge> },
                  { label: "Artifact digest", value: <Hash value={manifest.artifact_digest_sha256} length={24} /> },
                  { label: "Evidence digest", value: <Hash value={manifest.run_evidence.evidence_digest_sha256} length={24} /> },
                  { label: "Workspace", value: <code>{run.workspace_relative_path}</code> },
                  { label: "Selected stack", value: `${manifest.selected_frontend} + ${manifest.selected_backend}` },
                  { label: "Stack approval", value: `${manifest.stack_approval.classification} (authenticity verified: ${String(manifest.stack_approval.authenticity_verified)})` },
                  { label: "Generated at", value: manifest.generated_at_utc },
                ]}
              />
              <Callout tone="info">{manifest.trust_boundary}</Callout>
            </Card>
            <Card title="Local model evidence" subtitle={llm ? "Recorded by the Ollama client" : undefined}>
              {llm ? (
                <KeyValues
                  items={[
                    { label: "Provider", value: llm.provider },
                    { label: "Configured model", value: <code>{llm.configured_model_identifier}</code> },
                    { label: "Response model", value: <code>{llm.response_model_identifier}</code> },
                    { label: "Prompt template", value: llm.prompt_template_version },
                    { label: "Client latency", value: formatDuration(llm.client_inference_latency_ms) },
                    { label: "Eval tokens", value: llm.response.eval_count },
                    { label: "Temperature / ctx", value: `${llm.generation_parameters.temperature} / ${llm.generation_parameters.num_ctx}` },
                  ]}
                />
              ) : (
                <p className="muted small">No model was called. All files come from deterministic templates.</p>
              )}
            </Card>
          </div>

          <Card title="Generated files and origins" subtitle="Click a row to preview. Origin shows who wrote the file.">
            <Table
              dense
              rowKey={(row) => row.relative_path}
              selectedKey={previewPath}
              onRowClick={(row) => setPreviewPath(row.relative_path)}
              rows={files}
              columns={[
                { key: "relative_path", header: "Path", render: (row) => <code>{row.relative_path}</code> },
                { key: "artifact_type", header: "Type" },
                { key: "origin", header: "Origin", render: (row) => <OriginBadge origin={row.origin} /> },
                { key: "size_bytes", header: "Size", render: (row) => formatBytes(row.size_bytes) },
                { key: "sha256", header: "SHA-256", render: (row) => <Hash value={row.sha256} /> },
                { key: "requirement_ids", header: "Requirements", render: (row) => row.requirement_ids.join(", ") },
              ]}
            />
          </Card>

          <Card title="Safe read-only preview">
            <CodePreview run={run} path={previewPath} />
          </Card>

          <Card
            title="C3 structural verification (static)"
            subtitle="POST /api/v1/structural-verifications · inspects files without executing them. This is not Component 4 testing."
            actions={<Button variant="secondary" onClick={() => structural.run()} loading={structural.loading}>Run structural verification</Button>}
          >
            {structural.loading ? <Loading label="Inspecting generated structure" startedAt={structural.startedAt} /> : null}
            <ErrorPanel error={structural.error} context="Structural verification" />
            {session.structural ? (
              <>
                <div className="result-head">
                  <StatusBadge status={session.structural.overall_status} />
                  <span className="small">
                    {session.structural.summary.pass_count} pass · {session.structural.summary.fail_count} fail · {session.structural.summary.review_required_count} review required
                  </span>
                </div>
                <Table
                  dense
                  rowKey={(row) => row.finding_id}
                  rows={session.structural.findings}
                  columns={[
                    { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
                    { key: "rule_id", header: "Rule", render: (row) => <code>{row.rule_id}</code> },
                    { key: "category", header: "Category" },
                    { key: "message", header: "Message" },
                  ]}
                />
              </>
            ) : null}
          </Card>

          <Card
            title="Isolated runtime preview (optional)"
            subtitle="Runs a manifest-verified generated workspace only inside Docker, never inside this Research UI."
          >
            <p className="small">
              After starting the documented preview, open{" "}
              <a href="http://127.0.0.1:5180" target="_blank" rel="noreferrer">
                generated Task Manager
              </a>
              {" "}or inspect its{" "}
              <a
                href="http://127.0.0.1:3001/api/v1/tasks"
                target="_blank"
                rel="noreferrer"
              >
                local API
              </a>
              . The operator must first follow <code>docs/generated-app-preview.md</code>;
              these links do not start or execute generated code.
            </p>
          </Card>

          <div className="button-row">
            <Button onClick={() => navigate("traceability")}>Continue to Living Traceability</Button>
          </div>
          <JsonView value={manifest} summary="Full generation manifest" />
        </>
      ) : null}
    </div>
  );
}
