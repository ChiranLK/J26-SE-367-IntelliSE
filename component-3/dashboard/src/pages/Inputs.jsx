import { useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { Button, Callout, Card, ErrorPanel, JsonView, KeyValues, Loading, PageHeader, SimBanner, SimulatedBadge, StatusBadge, Table } from "../components/ui.jsx";
import { FAULT_PRESETS, applyFault } from "../lib/requests.js";
import { formatTime } from "../lib/format.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";

function parseJson(text) {
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
  const [crudDomains, setCrudDomains] = useState([]);

  const parsedC1 = useMemo(() => parseJson(session.c1InputText ?? ""), [session.c1InputText]);
  const parsedC2 = useMemo(() => parseJson(session.c2InputText ?? ""), [session.c2InputText]);
  const pkg = useMemo(() => {
    if (!parsedC1.value || !parsedC2.value) return null;
    return {
      contract_version: session.inputContractVersion || "1.0",
      c1: parsedC1.value,
      c2: parsedC2.value,
    };
  }, [parsedC1.value, parsedC2.value, session.inputContractVersion]);

  useEffect(() => {
    api.crudDomains().then((catalog) => setCrudDomains(catalog.domains ?? [])).catch(() => setCrudDomains([]));
  }, []);
  const load = useAction(async (fixtureId = "input-package") => {
    const envelope = await api.fixture(fixtureId);
    set("fixtures", { ...session.fixtures, inputPackage: envelope });
    set("inputText", JSON.stringify(envelope.payload, null, 2));
    set("inputContractVersion", envelope.payload.contract_version ?? "1.0");
    set("c1InputText", JSON.stringify(envelope.payload.c1 ?? {}, null, 2));
    set("c2InputText", JSON.stringify(envelope.payload.c2 ?? {}, null, 2));
    set("inputSources", { c1: "SIMULATED_FIXTURE", c2: "SIMULATED_FIXTURE" });
    set("validation", null);
    set("applicationProfile", "SCHEMA_DRIVEN_CRUD");
    set("generationRun", null);
    set("preview", null);
    set("structural", null);
    set("graph", null);
    setInjected(null);
  });

  const validate = useAction(async () => {
    const at = new Date().toISOString();
    try {
      const generationContext = await api.validateInput(pkg);
      // New accepted input invalidates everything derived from the old one.
      set("designContext", null);
      set("applicationProfile", "SCHEMA_DRIVEN_CRUD");
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
    set("c1InputText", JSON.stringify(faulty.c1 ?? {}, null, 2));
    set("c2InputText", JSON.stringify(faulty.c2 ?? {}, null, 2));
    set("validation", null);
    setInjected(FAULT_PRESETS.find((item) => item.id === presetId));
  };

  const restore = () => {
    if (!session.fixtures.inputPackage) return;
    set("inputText", JSON.stringify(session.fixtures.inputPackage.payload, null, 2));
    set("inputContractVersion", session.fixtures.inputPackage.payload.contract_version ?? "1.0");
    set("c1InputText", JSON.stringify(session.fixtures.inputPackage.payload.c1 ?? {}, null, 2));
    set("c2InputText", JSON.stringify(session.fixtures.inputPackage.payload.c2 ?? {}, null, 2));
    set("inputSources", { c1: "SIMULATED_FIXTURE", c2: "SIMULATED_FIXTURE" });
    set("validation", null);
    setInjected(null);
  };

  const validation = session.validation;
  const context = validation?.ok ? validation.generationContext : null;
  const inputReady = Boolean(pkg && !parsedC1.error && !parsedC2.error);
  const simulated = session.inputSources?.c1 === "SIMULATED_FIXTURE" || session.inputSources?.c2 === "SIMULATED_FIXTURE";

  const updateInput = (component, value, source = "PASTED_OR_EDITED") => {
    set(component === "c1" ? "c1InputText" : "c2InputText", value);
    set("inputSources", { ...(session.inputSources ?? {}), [component]: source });
    set("inputText", "");
    set("validation", null);
  };

  const uploadInput = async (component, file) => {
    if (!file) return;
    const text = await file.text();
    const parsed = parseJson(text);
    if (parsed.error) {
      updateInput(component, text, "UPLOADED_FILE");
      return;
    }
    const value = parsed.value?.[component] ?? parsed.value;
    updateInput(component, JSON.stringify(value, null, 2), "UPLOADED_FILE");
    if (parsed.value?.contract_version) set("inputContractVersion", parsed.value.contract_version);
  };

  return (
    <div className="page">
      <PageHeader
        title="C1/C2 Inputs"
        subtitle="Upload or paste separate upstream JSON outputs, then run the real FR-C3-01 validation API."
        badges={simulated ? <SimulatedBadge>SIMULATED C1/C2 FIXTURE</SimulatedBadge> : <StatusBadge status="REVIEW_REQUIRED" label="PROVISIONAL CONTRACT" />}
      />
      <SimBanner>
        Direct Component 1 and Component 2 integration is not yet verified. Uploaded or pasted JSON
        uses C3&apos;s provisional contract; approval reference strings are preserved but not authenticated.
      </SimBanner>

      {/* ---- Quick Load Presentation Fixtures ------------------------- */}
      <Card
        title="Load fixture"
        subtitle="Quickly load pre-validated requirements and architecture outputs for presentation."
        actions={
          <Button onClick={() => load.run("input-package")} loading={load.loading}>
            {session.fixtures.inputPackage ? "Reload Task fixture" : "Load Task Management fixture"}
          </Button>
        }
      >
        <div className="fault-row">
          <span className="muted small">Dynamic CRUD demo domains (SIMULATED C1/C2):</span>
          {crudDomains.map((domain) => (
            <Button
              key={domain.domain_id}
              variant="secondary"
              onClick={() => load.run(domain.fixture_id)}
              loading={load.loading}
              title={domain.notice}
            >
              {domain.title}
            </Button>
          ))}
        </div>
        {session.fixtures.inputPackage ? (
          <p className="small">{session.fixtures.inputPackage.notice}</p>
        ) : (
          <p className="muted small">No package loaded. The fixture is read from GET /api/v1/demo/fixtures/input-package.</p>
        )}
        {load.loading ? <Loading label="Loading fixture" startedAt={load.startedAt} /> : null}
        <ErrorPanel error={load.error} context="Load fixture" />
      </Card>

      {/* ---- Primary C1 & C2 Input Areas ----------------------------- */}
      <div className="grid grid-2 upstream-input-grid">
        <Card
          title="Component 1 output"
          subtitle="Approved SRS package, stable requirement IDs, versions and provenance references."
          actions={<span className="badge badge-neutral">{session.inputSources?.c1 ?? "NONE"}</span>}
        >
          <label className="file-input-label">
            Upload C1 JSON
            <input
              aria-label="Upload C1 JSON"
              type="file"
              accept="application/json,.json"
              onChange={(event) => uploadInput("c1", event.target.files?.[0])}
            />
          </label>
          <textarea
            className="json-editor upstream-json-editor"
            spellCheck={false}
            placeholder='Paste the C1 object here, for example {"contract_version":"1.0", ...}'
            value={session.c1InputText ?? ""}
            onChange={(event) => updateInput("c1", event.target.value)}
            aria-label="Component 1 JSON"
          />
          {parsedC1.error ? <Callout tone="bad" title="C1 JSON is not valid">{parsedC1.error}</Callout> : null}
        </Card>

        <Card
          title="Component 2 output"
          subtitle="Validated UML release, UI references and requirement-to-UML anchors."
          actions={<span className="badge badge-neutral">{session.inputSources?.c2 ?? "NONE"}</span>}
        >
          <label className="file-input-label">
            Upload C2 JSON
            <input
              aria-label="Upload C2 JSON"
              type="file"
              accept="application/json,.json"
              onChange={(event) => uploadInput("c2", event.target.files?.[0])}
            />
          </label>
          <textarea
            className="json-editor upstream-json-editor"
            spellCheck={false}
            placeholder='Paste the C2 object here, for example {"contract_version":"1.0", ...}'
            value={session.c2InputText ?? ""}
            onChange={(event) => updateInput("c2", event.target.value)}
            aria-label="Component 2 JSON"
          />
          {parsedC2.error ? <Callout tone="bad" title="C2 JSON is not valid">{parsedC2.error}</Callout> : null}
        </Card>
      </div>

      <Card title="Input envelope" subtitle="C3 combines the two objects only for the existing validation endpoint.">
        <label className="contract-version-field">
          Provisional contract version
          <input
            type="text"
            aria-label="Input contract version"
            value={session.inputContractVersion ?? "1.0"}
            onChange={(event) => {
              set("inputContractVersion", event.target.value);
              set("validation", null);
            }}
          />
        </label>
        <p className="muted small">
          Both inputs are required. C3 does not create missing approvals, requirements, UML elements or anchors.
        </p>
      </Card>

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
              <Button onClick={() => validate.run()} loading={validate.loading} disabled={!inputReady}>
                Validate C1/C2 inputs
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
                <Button onClick={() => navigate("design")} style={{ marginTop: "0.5rem" }}>
                  Proceed to Step 2: Tech Stack Selection →
                </Button>
              </div>
            ) : null}
          </Card>
          <JsonView value={pkg} summary="Combined package JSON sent to the validation API" />
        </>
      ) : (
        <Callout tone="info" title="Waiting for both upstream inputs">
          Supply valid JSON for Component 1 and Component 2. No downstream generation can start until both are present and accepted by the backend.
        </Callout>
      )}
    </div>
  );
}
