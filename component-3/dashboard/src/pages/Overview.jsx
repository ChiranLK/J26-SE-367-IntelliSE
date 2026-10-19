import { useState } from "react";
import { api } from "../api/endpoints.js";
import { Badge, Button, Callout, Card, ErrorPanel, KeyValues, Loading, PageHeader, StatusBadge, Table } from "../components/ui.jsx";
import { formatTime } from "../lib/format.js";
import { useBackend } from "../state/backend.jsx";
import { useSession } from "../state/session.jsx";

const WORKFLOW = [
  { id: "inputs", label: "1. C1/C2 inputs validated", done: (s) => Boolean(s.validation?.ok) },
  { id: "design", label: "2. Design parsed, stack selected and approved", done: (s) => s.approval?.status === "APPROVED_FOR_MVP_GENERATION" },
  { id: "generation", label: "3. Code generated (not executed)", done: (s) => Boolean(s.generationRun) },
  { id: "traceability", label: "4. Living traceability graph built", done: (s) => Boolean(s.graph) },
  { id: "scoped", label: "5. Scoped regeneration from a SIMULATED defect", done: (s) => s.scoped.runs.length > 0 },
  { id: "readiness", label: "6. Readiness (C4 retest PENDING, deployment BLOCKED)", done: () => false },
];

export default function Overview({ navigate }) {
  const { health, overview, error, loading, refresh, checkedAt } = useBackend();
  const { session } = useSession();
  const ollama = overview?.ollama;

  const [switching, setSwitching] = useState(false);
  const [colabUrl, setColabUrl] = useState(() => localStorage.getItem("colab_tunnel_url") || "");
  const [showColabInput, setShowColabInput] = useState(false);
  const [switchError, setSwitchError] = useState(null);

  const isColabActive = Boolean(ollama?.base_url && String(ollama.base_url).includes("11435"));

  const handleSwitch = async (engine) => {
    setSwitching(true);
    setSwitchError(null);
    try {
      if (engine === "COLAB") {
        const urlToUse = colabUrl.trim();
        if (!urlToUse) {
          setShowColabInput(true);
          setSwitching(false);
          return;
        }
        localStorage.setItem("colab_tunnel_url", urlToUse);
        await api.engineSwitch("COLAB", urlToUse);
      } else {
        await api.engineSwitch("LOCAL");
      }
      await refresh();
      setShowColabInput(false);
    } catch (err) {
      console.error(err);
      setSwitchError(err.message || "Failed to switch engine");
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        title="Overview"
        subtitle="InteliSE Component 3: living requirement traceability and defect-feedback-driven scoped regeneration."
        badges={
          <>
            <Badge tone="sim">C1/C2 SIMULATED</Badge>
            <Badge tone="sim">C4 defects SIMULATED</Badge>
          </>
        }
      />

      <Callout tone="info" title="What this dashboard is">
        This is the C3 research demo interface. Every button calls the real Component 3 FastAPI
        service. It is not the application that Component 3 generates. Generated source stays
        read-only in this UI unless you explicitly start its restricted local Docker preview.
      </Callout>

      {loading ? <Loading label="Checking the Component 3 API and local Ollama" /> : null}
      <ErrorPanel error={error} context="API status" />

      <div className="grid grid-2">
        <Card
          title="Backend and local model"
          subtitle={checkedAt ? `Last checked ${formatTime(new Date(checkedAt).toISOString())}` : undefined}
          actions={<Button variant="secondary" onClick={refresh} loading={loading}>Re-check</Button>}
        >
          <KeyValues
            items={[
              { label: "FastAPI service", value: loading ? <StatusBadge status="NOT_RUN" label="checking…" /> : health ? <StatusBadge status="SATISFIED" label={`${health.service_name} · ${health.status}`} /> : <StatusBadge status="BLOCKED" label="unreachable" /> },
              { label: "API version", value: health?.api_version },
              { label: "Ollama endpoint", value: ollama?.base_url },
              { label: "Configured local model", value: ollama ? <code>{ollama.configured_model}</code> : undefined },
              {
                label: "Ollama status",
                value: ollama ? (
                  <StatusBadge
                    status={ollama.reachable && ollama.model_installed ? "SATISFIED" : "BLOCKED"}
                    label={ollama.reachable ? (ollama.model_installed ? "reachable · model installed" : "reachable · model missing") : "unreachable"}
                  />
                ) : undefined,
              },
              { label: "Probe detail", value: ollama?.detail },
              { label: "Workspace root", value: overview?.generated_workspace_root_name },
              { label: "Graph store file", value: overview?.traceability_store_name },
            ]}
          />
          <div style={{ marginTop: "1rem", paddingTop: "0.75rem", borderTop: "1px solid var(--line)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
              <span className="small muted"><strong>Inference Engine:</strong></span>
              <Badge tone={isColabActive ? "llm" : "info"}>
                {isColabActive ? "Google Colab GPU (7B)" : "Local Machine (3B Offline)"}
              </Badge>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
              <Button
                variant={!isColabActive ? "primary" : "secondary"}
                onClick={() => handleSwitch("LOCAL")}
                loading={switching}
                disabled={switching || !isColabActive}
              >
                Use Local 3B Model
              </Button>
              <Button
                variant={isColabActive ? "primary" : "secondary"}
                onClick={() => {
                  if (showColabInput && colabUrl.trim()) {
                    handleSwitch("COLAB");
                  } else {
                    setShowColabInput(!showColabInput);
                  }
                }}
                loading={switching}
                disabled={switching}
              >
                {showColabInput ? "Connect Colab" : "Use Google Colab GPU"}
              </Button>
            </div>
            {showColabInput ? (
              <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.5rem" }}>
                <input
                  type="text"
                  placeholder="Colab Tunnel URL (e.g. https://...trycloudflare.com)"
                  value={colabUrl}
                  onChange={(e) => setColabUrl(e.target.value)}
                  style={{ flex: 1, padding: "0.35rem 0.5rem", fontSize: "0.85rem", borderRadius: "6px", border: "1px solid var(--line)" }}
                />
                <Button variant="primary" onClick={() => handleSwitch("COLAB")} loading={switching} disabled={!colabUrl.trim()}>
                  Connect
                </Button>
              </div>
            ) : null}
            {switchError ? (
              <div style={{ marginTop: "0.5rem" }}>
                <Callout tone="bad" title="Engine switch failed">
                  {switchError}
                </Callout>
              </div>
            ) : null}
          </div>
          {ollama && !(ollama.reachable && ollama.model_installed) ? (
            <Callout tone="warn" title="Local-model steps are unavailable">
              LOCAL_LLM generation and REAL_LOCAL_OLLAMA repair need Ollama running with the
              configured model. TEMPLATE and MOCK modes still work.
            </Callout>
          ) : null}
        </Card>

        <Card title="Workflow progress" subtitle="Ticks come from real responses received in this session.">
          <ol className="workflow">
            {WORKFLOW.map((step) => (
              <li key={step.id}>
                <button type="button" className="link-button" onClick={() => navigate(step.id)}>
                  {step.label}
                </button>
                <StatusBadge status={step.done(session) ? "SATISFIED" : "NOT_RUN"} label={step.done(session) ? "done" : "not run"} />
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <Card title="Component integration status" subtitle="Reported by the API. Upstream and C4 evidence is not real.">
        <Table
          rowKey={(row) => row.component}
          rows={overview?.integrations ?? []}
          empty={error ? "Unavailable while the API is unreachable." : "Waiting for the API."}
          columns={[
            { key: "component", header: "Component" },
            { key: "state", header: "State", render: (row) => <StatusBadge status={row.state === "LOCAL_REAL" ? "SATISFIED" : row.state === "SIMULATED_FIXTURE" ? "SIMULATED" : row.state} label={row.state.replaceAll("_", " ")} /> },
            { key: "note", header: "Note" },
          ]}
        />
      </Card>
    </div>
  );
}
