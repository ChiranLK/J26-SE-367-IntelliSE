import { useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { Button, Callout, Card, ErrorPanel, JsonView, KeyValues, Loading, PageHeader, SimBanner, SimulatedBadge, StatusBadge, Table } from "../components/ui.jsx";
import { FAULT_PRESETS, applyFault } from "../lib/requests.js";
import { formatTime } from "../lib/format.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";

function parsePackage(text) {
  if (!text.trim()) return { value: null, error: null };
  try {
    return { value: JSON.parse(text), error: null };
  } catch (error) {
    return { value: null, error: error.message };
  }
}

export default function Inputs({ navigate }) {
  const { session, set } = useSession();
  const [injected, setInjected] = useState(null);
  const parsed = useMemo(() => parsePackage(session.inputText), [session.inputText]);
  const pkg = parsed.value;

  const load = useAction(async () => {
    const envelope = await api.fixture("input-package");
    set("fixtures", { ...session.fixtures, inputPackage: envelope });
    set("inputText", JSON.stringify(envelope.payload, null, 2));
    set("validation", null);
    setInjected(null);
  });

  const validate = useAction(async () => {
    const at = new Date().toISOString();
    try {
      const generationContext = await api.validateInput(pkg);
      // New accepted input invalidates everything derived from the old one.
      set("designContext", null);
      set("stackReport", null);
      set("approval", null);
      set("generationRun", null);
      set("structural", null);
      set("graph", null);
      set("validation", { ok: true, at, generationContext });
    } catch (error) {
      set("validation", {
        ok: false,
        at,
        error: { kind: error.kind, status: error.status, errors: error.errors ?? [], message: error.message, path: error.path },
      });
      throw error;
    }
  });

  const inject = (presetId) => {
    if (!pkg) return;
    const faulty = applyFault(pkg, presetId);
    set("inputText", JSON.stringify(faulty, null, 2));
    set("validation", null);
    setInjected(FAULT_PRESETS.find((item) => item.id === presetId));
  };

  const restore = () => {
    if (!session.fixtures.inputPackage) return;
    set("inputText", JSON.stringify(session.fixtures.inputPackage.payload, null, 2));
    set("validation", null);
    setInjected(null);
  };

  const validation = session.validation;
  const context = validation?.ok ? validation.generationContext : null;

  return (
    <div className="page">
      <PageHeader
        title="C1/C2 Inputs"
        subtitle="Load the simulated upstream package and run the real FR-C3-01 validation API."
        badges={<SimulatedBadge>SIMULATED C1/C2 FIXTURE</SimulatedBadge>}
      />
      <SimBanner>
        Component 1 and Component 2 are not integrated. This package is a simulated fixture; passing
        validation does not mean it was approved by C1 or C2.
      </SimBanner>

      <Card
        title="Load fixture"
        actions={
          <Button onClick={() => load.run()} loading={load.loading}>
            {session.fixtures.inputPackage ? "Reload simulated fixture" : "Load simulated fixture"}
          </Button>
        }
      >
        {session.fixtures.inputPackage ? (
          <p className="small">{session.fixtures.inputPackage.notice}</p>
        ) : (
          <p className="muted small">No package loaded. The fixture is read from GET /api/v1/demo/fixtures/input-package.</p>
        )}
        {load.loading ? <Loading label="Loading fixture" startedAt={load.startedAt} /> : null}
        <ErrorPanel error={load.error} context="Load fixture" />
      </Card>

      {parsed.error ? <Callout tone="bad" title="Package JSON is not valid">{parsed.error}</Callout> : null}

      {pkg ? (
        <>
          <div className="grid grid-2">
            <Card title="C1 requirements" subtitle={`${pkg.c1?.project_id ?? ""} · ${pkg.c1?.srs_version ?? ""} · ${pkg.c1?.approval_status ?? ""}`}>
              <Table
                dense
                rowKey={(row, index) => `${row.requirement_id ?? "missing"}-${index}`}
                rows={pkg.c1?.requirements ?? []}
                columns={[
                  { key: "requirement_id", header: "ID", render: (row) => row.requirement_id ?? <em className="text-bad">missing</em> },
                  { key: "title", header: "Title" },
                  { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status === "APPROVED" ? "SATISFIED" : "BLOCKED"} label={row.status} /> },
                ]}
              />
            </Card>
            <Card title="C2 UML elements" subtitle={`${pkg.c2?.uml_version ?? ""} · ${pkg.c2?.release_status ?? ""} · ${pkg.c2?.validation_state ?? ""}`}>
              <Table
                dense
                rowKey={(row) => row.uml_id}
                rows={pkg.c2?.uml_elements ?? []}
                columns={[
                  { key: "uml_id", header: "UML ID" },
                  { key: "element_type", header: "Type" },
                  { key: "name", header: "Name" },
                ]}
              />
              <h3 className="subhead">UI artifacts</h3>
              <Table
                dense
                rowKey={(row) => row.ui_id}
                rows={pkg.c2?.ui_artifacts ?? []}
                columns={[
                  { key: "ui_id", header: "UI ID" },
                  { key: "artifact_type", header: "Type" },
                  { key: "source_ref", header: "Source ref" },
                ]}
              />
            </Card>
          </div>
          <Card title="Requirement to UML anchors" subtitle="C2-declared references that C3 later turns into traceability links.">
            <Table
              dense
              rowKey={(row, index) => `${row.anchor_id}-${index}`}
              rows={pkg.c2?.requirement_uml_anchors ?? []}
              columns={[
                { key: "anchor_id", header: "Anchor" },
                { key: "requirement_id", header: "Requirement" },
                { key: "uml_id", header: "UML element" },
              ]}
            />
          </Card>

          <Card
            title="Validate with the real API"
            subtitle="POST /api/v1/validate-input"
            actions={
              <Button onClick={() => validate.run()} loading={validate.loading} disabled={Boolean(parsed.error)}>
                Run validation
              </Button>
            }
          >
            <div className="fault-row">
              <span className="muted small">Optional fault injection (edits the local copy only):</span>
              {FAULT_PRESETS.map((preset) => (
                <Button key={preset.id} variant="secondary" onClick={() => inject(preset.id)} title={preset.description}>
                  {preset.label}
                </Button>
              ))}
              <Button variant="ghost" onClick={restore} disabled={!session.fixtures.inputPackage}>
                Restore fixture
              </Button>
            </div>
            {injected ? (
              <Callout tone="sim" title={`Fault injected: ${injected.label}`}>
                {injected.description} The result below is the backend's real verdict.
              </Callout>
            ) : null}
            {validate.loading ? <Loading label="Validating package" startedAt={validate.startedAt} /> : null}
            {validation && !validation.ok ? <ErrorPanel error={validation.error} context="Validation" /> : null}
            {context ? (
              <div className="result">
                <div className="result-head">
                  <StatusBadge status="SATISFIED" label="ACCEPTED by C3 validation" />
                  <span className="muted small">{formatTime(validation.at)}</span>
                </div>
                <KeyValues
                  items={[
                    { label: "Project", value: context.project_id },
                    { label: "SRS / UML", value: `${context.srs_version} / ${context.uml_version}` },
                    { label: "Requirements", value: context.requirements.length },
                    { label: "UML elements", value: context.uml_elements.length },
                    { label: "UI artifacts", value: context.ui_artifacts.length },
                    { label: "Anchors", value: context.requirement_uml_anchors.length },
                    { label: "C1 approval ref", value: <code>{context.upstream_provenance.c1_approval_provenance_ref}</code> },
                    { label: "C2 validation ref", value: <code>{context.upstream_provenance.c2_validation_report_ref}</code> },
                  ]}
                />
                <Callout tone="info">Approval references are recorded as opaque strings. C3 does not verify that they are authentic.</Callout>
                <Button variant="secondary" onClick={() => navigate("design")}>Continue to Design &amp; Stack</Button>
              </div>
            ) : null}
          </Card>
          <JsonView value={pkg} summary="Package JSON as sent to the API" />
          <details className="json-view">
            <summary>Edit package JSON</summary>
            <textarea
              className="json-editor"
              spellCheck={false}
              value={session.inputText}
              onChange={(event) => {
                set("inputText", event.target.value);
                set("validation", null);
              }}
              aria-label="Package JSON editor"
            />
          </details>
        </>
      ) : null}
    </div>
  );
}
