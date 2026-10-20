import { useState } from "react";
import { api } from "../api/endpoints.js";
import { Badge, Button, Callout, Card, ErrorPanel, KeyValues, Loading, PageHeader, StatusBadge, Table, TechnicalDetails } from "../components/ui.jsx";
import { formatTime } from "../lib/format.js";
import { useBackend } from "../state/backend.jsx";
import { useSession } from "../state/session.jsx";

const WORKFLOW = [
  { id: "inputs", label: "Validated C1/C2 package", done: (s) => Boolean(s.validation?.ok) },
  { id: "design", label: "Design understood and stack approved", done: (s) => s.approval?.status === "APPROVED_FOR_MVP_GENERATION" },
  { id: "generation", label: "Application workspace generated", done: (s) => Boolean(s.generationRun) },
  { id: "traceability", label: "Living traceability graph created", done: (s) => Boolean(s.graph) },
  { id: "scoped", label: "RAG-grounded scoped repair demonstrated", done: (s) => s.scoped.runs.length > 0 },
  { id: "readiness", label: "Independent C4 re-test", done: () => false },
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
      setSwitchError(err.message || "Failed to switch engine");
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        title="Component 3 Research Dashboard"
        subtitle="Generate traceable software, maintain living requirement links, and repair only defect-impacted code."
        badges={<><Badge tone="sim">C1/C2 SIMULATED</Badge><Badge tone="sim">C4 DEFECTS SIMULATED</Badge></>}
      />

      <section className="research-hero">
        <div>
          <span className="eyebrow">INTELISE · COMPONENT 3</span>
          <h2>From approved design evidence to a verifiable application</h2>
          <p>The pipeline validates upstream evidence, understands the design, selects a supported stack, generates code, builds trace links, and prepares targeted repairs for independent re-verification.</p>
          <div className="button-row">
            <Button onClick={() => navigate("inputs")}>Start the guided demo</Button>
            <Button variant="secondary" onClick={() => navigate("scoped")}>Show RAG scoped repair</Button>
          </div>
        </div>
        <div className="hero-gate"><span>Deployment gate</span><strong>BLOCKED</strong><small>C4 re-testing is still pending</small></div>
      </section>

      <div className="novelty-grid">
        <Card className="novelty-card novelty-trace" title="Novelty 1 · Living Traceability" subtitle="Requirements → UML → code → API → database → test hooks">
          <p>Versioned graph snapshots preserve resolved, review-required, and retired evidence links across generation runs.</p>
          <Button variant="ghost" onClick={() => navigate("traceability")}>Explore traceability</Button>
        </Card>
        <Card className="novelty-card novelty-rag" title="Novelty 2 · RAG-Grounded Scoped Repair" subtitle="RAG A defect context + RAG B engineering rules">
          <p>Trigger C retrieves current, graph-scoped evidence and limits a model repair to the implicated module.</p>
          <Button variant="ghost" onClick={() => navigate("scoped")}>Inspect repair evidence</Button>
        </Card>
      </div>

      <Callout tone="info" title="Research boundary">Dashboard actions call the real Component 3 API. Generated code remains read-only here unless a restricted local Docker preview is explicitly started. Simulated upstream and C4 evidence is always labelled.</Callout>
      {loading ? <Loading label="Checking Component 3 services" /> : null}
      <ErrorPanel error={error} context="Service status" />

      <div className="grid grid-2">
        <Card title="Generation engine" subtitle={checkedAt ? `Last checked ${formatTime(new Date(checkedAt).toISOString())}` : undefined} actions={<Button variant="secondary" onClick={refresh} loading={loading}>Re-check</Button>}>
          <div className="engine-status"><div><span className={`dot dot-${health ? "ok" : "bad"}`} /><strong>Component 3 API</strong></div><StatusBadge status={health ? "SATISFIED" : "BLOCKED"} label={health ? "ONLINE" : "UNREACHABLE"} /></div>
          <div className="engine-status">
            <div><span className={`dot dot-${ollama?.reachable && ollama?.model_installed ? "ok" : "warn"}`} /><strong>{isColabActive ? "Colab Ollama" : "Local Ollama"}</strong>{ollama?.configured_model ? <code>{ollama.configured_model}</code> : null}</div>
            <StatusBadge
              status={ollama?.reachable && ollama?.model_installed ? "SATISFIED" : "BLOCKED"}
              label={ollama?.reachable ? (ollama.model_installed ? "reachable · model installed" : "reachable · model missing") : "unreachable"}
            />
          </div>
          <div className="button-row">
            <Button variant={!isColabActive ? "primary" : "secondary"} onClick={() => handleSwitch("LOCAL")} loading={switching} disabled={switching || !isColabActive}>Use local engine</Button>
            <Button variant={isColabActive ? "primary" : "secondary"} onClick={() => showColabInput && colabUrl.trim() ? handleSwitch("COLAB") : setShowColabInput(!showColabInput)} loading={switching} disabled={switching}>{showColabInput ? "Connect Colab" : "Use Colab GPU"}</Button>
          </div>
          {showColabInput ? <div className="inline-field"><input type="text" aria-label="Colab tunnel URL" placeholder="HTTPS tunnel URL" value={colabUrl} onChange={(event) => setColabUrl(event.target.value)} /><Button onClick={() => handleSwitch("COLAB")} loading={switching} disabled={!colabUrl.trim()}>Connect</Button></div> : null}
          {switchError ? <Callout tone="bad" title="Engine switch failed">{switchError}</Callout> : null}
          {ollama && !(ollama.reachable && ollama.model_installed) ? (
            <Callout tone="warn" title="Local-model steps are unavailable">
              Start Ollama with the configured model, or connect the approved Colab Ollama endpoint. No cloud fallback is selected automatically.
            </Callout>
          ) : null}
          <TechnicalDetails summary="Service and storage details">
            <KeyValues items={[
              { label: "FastAPI service", value: loading ? "checking…" : health ? `${health.service_name} · ${health.status}` : "unreachable" },
              { label: "API version", value: health?.api_version },
              { label: "Ollama endpoint", value: ollama?.base_url },
              { label: "Probe detail", value: ollama?.detail },
              { label: "Workspace root", value: overview?.generated_workspace_root_name },
              { label: "Graph store", value: overview?.traceability_store_name },
            ]} />
          </TechnicalDetails>
        </Card>

        <Card title="Guided research workflow" subtitle="Progress is based only on responses received in this browser session.">
          <ol className="workflow">
            {WORKFLOW.map((step) => <li key={step.id}><button type="button" className="link-button" onClick={() => navigate(step.id)}>{step.label}</button><StatusBadge status={step.done(session) ? "SATISFIED" : step.id === "readiness" ? "PENDING" : "NOT_RUN"} label={step.done(session) ? "DONE" : step.id === "readiness" ? "PENDING" : "NOT RUN"} /></li>)}
          </ol>
        </Card>
      </div>

      <TechnicalDetails summary="Cross-component integration status">
        <Table rowKey={(row) => row.component} rows={overview?.integrations ?? []} empty={error ? "Unavailable while the API is unreachable." : "Waiting for the API."} columns={[
          { key: "component", header: "Component" },
          { key: "state", header: "State", render: (row) => <StatusBadge status={row.state === "LOCAL_REAL" ? "SATISFIED" : row.state === "SIMULATED_FIXTURE" ? "SIMULATED" : row.state} label={row.state.replaceAll("_", " ")} /> },
          { key: "note", header: "Evidence boundary" },
        ]} />
      </TechnicalDetails>
    </div>
  );
}
