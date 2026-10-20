import { useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { Button, Callout, Card, ErrorPanel, JsonView, KeyValues, Loading, PageHeader, SimulatedBadge, StatusBadge, Table } from "../components/ui.jsx";
import { FAULT_PRESETS, applyFault } from "../lib/requests.js";
import { formatTime } from "../lib/format.js";
import { inspectC1SrsDocument, inspectC2PlantUmlDocument } from "../lib/sourceDocumentIntake.js";
import { adaptUpstreamInputs } from "../lib/upstreamInputAdapter.js";
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
  const sourceDocuments = session.sourceDocuments ?? { c1Name: "", c1Text: "", c2Name: "", c2Text: "" };
  const c1Document = useMemo(() => inspectC1SrsDocument(sourceDocuments.c1Text), [sourceDocuments.c1Text]);
  const c2Document = useMemo(() => inspectC2PlantUmlDocument(sourceDocuments.c2Text), [sourceDocuments.c2Text]);
  const documentFindings = useMemo(
    () => [...c1Document.issues, ...c2Document.issues, ...(sourceDocuments.c2Text ? c2Document.missing_contract_evidence : [])],
    [c1Document, c2Document, sourceDocuments.c2Text],
  );

  const parsedC1 = useMemo(() => parseJson(session.c1InputText ?? ""), [session.c1InputText]);
  const parsedC2 = useMemo(() => parseJson(session.c2InputText ?? ""), [session.c2InputText]);
  const compatibility = useMemo(() => {
    if (!parsedC1.value || !parsedC2.value) return null;
    return adaptUpstreamInputs(parsedC1.value, parsedC2.value, {
      c2ValidationReportRef: session.c2ValidationReportRef ?? "",
    });
  }, [parsedC1.value, parsedC2.value, session.c2ValidationReportRef]);
  const pkg = useMemo(() => {
    if (!compatibility) return null;
    return {
      contract_version: session.inputContractVersion || "1.0",
      c1: compatibility.c1,
      c2: compatibility.c2,
    };
  }, [compatibility, session.inputContractVersion]);

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
    set("c2ValidationReportRef", envelope.payload.c2?.validation_report_ref ?? "");
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
    set("c2ValidationReportRef", session.fixtures.inputPackage.payload.c2?.validation_report_ref ?? "");
    set("inputSources", { c1: "SIMULATED_FIXTURE", c2: "SIMULATED_FIXTURE" });
    set("validation", null);
    setInjected(null);
  };

  const validation = session.validation;
  const context = validation?.ok ? validation.generationContext : null;
  const inputReady = Boolean(pkg && !parsedC1.error && !parsedC2.error && !compatibility?.errors.length);
  const simulated = session.inputSources?.c1 === "SIMULATED_FIXTURE" || session.inputSources?.c2 === "SIMULATED_FIXTURE";

  const updateInput = (component, value, source = "PASTED_OR_EDITED") => {
    set(component === "c1" ? "c1InputText" : "c2InputText", value);
    set("inputSources", { ...(session.inputSources ?? {}), [component]: source });
    set("inputText", "");
    set("validation", null);
  };

  const uploadInput = async (component, file) => {
    if (!file) return;
    try {
      set("uploading", true);
      const text = await file.text();
      const parsed = parseJson(text);
      if (parsed.error) {
        updateInput(component, text, "UPLOADED_FILE");
        return;
      }
      const value = parsed.value?.[component] ?? parsed.value;
      updateInput(component, JSON.stringify(value, null, 2), "UPLOADED_FILE");
      if (component === "c2") set("c2ValidationReportRef", value?.validation_report_ref ?? "");
      if (parsed.value?.contract_version) set("inputContractVersion", parsed.value.contract_version);
    } finally {
      set("uploading", false);
    }
  };

  const uploadSourceDocument = async (component, file) => {
    if (!file) return;
    try {
      set("uploading", true);
      const text = await file.text();
      set("sourceDocuments", {
        ...sourceDocuments,
        [`${component}Name`]: file.name,
        [`${component}Text`]: text,
      });
    } finally {
      set("uploading", false);
    }
  };

  return (
    <div className="page">
      {session.uploading ? <Loading label="Uploading file..." /> : null}
      <PageHeader
        title="C1/C2 Inputs"
        subtitle="Provide the finalized C1 SRS text and C2 PlantUML source, then inspect evidence readiness before C3 validation."
        badges={simulated ? <SimulatedBadge>SIMULATED C1/C2 FIXTURE</SimulatedBadge> : <StatusBadge status="REVIEW_REQUIRED" label="PP1 DOCUMENT INTAKE" />}
      />
      <Card
        title="PP1 finalized source documents"
        subtitle="Accepts the currently available C1 SRS .txt and C2 PlantUML .puml without pretending they are complete approved contracts."
        actions={<StatusBadge status={(sourceDocuments.c1Text && sourceDocuments.c2Text) ? "REVIEW_REQUIRED" : "PENDING"} label={(sourceDocuments.c1Text && sourceDocuments.c2Text) ? "ANALYZED · REVIEW REQUIRED" : "WAITING FOR FILES"} />}
      >
        <div className="grid grid-2 upstream-input-grid">
          <div className="source-document-panel source-document-panel-c1">
            <div className="source-panel-heading">
              <span className="source-panel-id">C1</span>
              <div>
                <h3>Finalized SRS</h3>
                <p>Requirements and source provenance</p>
              </div>
            </div>
            <label className="file-input-label">
              <span>Upload SRS document <small>.txt</small></span>
              <input aria-label="Upload C1 SRS document" type="file" accept="text/plain,.txt" onChange={(event) => uploadSourceDocument("c1", event.target.files?.[0])} />
            </label>
            <p className={`source-file-name${sourceDocuments.c1Name ? " source-file-ready" : ""}`}>{sourceDocuments.c1Name || "No file selected"}</p>
            <label className="source-text-label">
              <span>SRS source text</span>
              <textarea
                className="json-editor upstream-json-editor"
                aria-label="C1 finalized SRS text"
                spellCheck={false}
                placeholder="Paste the finalized Component 1 SRS text here, or choose a .txt file above."
                value={sourceDocuments.c1Text}
                onChange={(event) => set("sourceDocuments", { ...sourceDocuments, c1Name: "PASTED_TEXT", c1Text: event.target.value })}
              />
            </label>
            {sourceDocuments.c1Text ? (
              <div className="source-summary">
                <KeyValues items={[
                  { label: "Title", value: c1Document.title },
                  { label: "Project", value: c1Document.project_id },
                  { label: "Requirement IDs", value: c1Document.requirements.length },
                  { label: "Source SHA-256", value: c1Document.source_sha256 ? <code className="source-hash">{c1Document.source_sha256}</code> : "Not supplied" },
                ]} />
              </div>
            ) : <p className="muted small">The original text stays in this browser session; C3 does not rewrite it.</p>}
          </div>
          <div className="source-document-panel source-document-panel-c2">
            <div className="source-panel-heading">
              <span className="source-panel-id">C2</span>
              <div>
                <h3>Finalized PlantUML</h3>
                <p>Class design and relationships</p>
              </div>
            </div>
            <label className="file-input-label">
              <span>Upload UML document <small>.puml</small></span>
              <input aria-label="Upload C2 PlantUML document" type="file" accept="text/plain,.puml,.plantuml" onChange={(event) => uploadSourceDocument("c2", event.target.files?.[0])} />
            </label>
            <p className={`source-file-name${sourceDocuments.c2Name ? " source-file-ready" : ""}`}>{sourceDocuments.c2Name || "No file selected"}</p>
            <label className="source-text-label">
              <span>PlantUML source</span>
              <textarea
                className="json-editor upstream-json-editor"
                aria-label="C2 finalized PlantUML source"
                spellCheck={false}
                placeholder="Paste the finalized Component 2 PlantUML source here, or choose a .puml file above."
                value={sourceDocuments.c2Text}
                onChange={(event) => set("sourceDocuments", { ...sourceDocuments, c2Name: "PASTED_TEXT", c2Text: event.target.value })}
              />
            </label>
            {sourceDocuments.c2Text ? (
              <div className="source-summary">
                <KeyValues items={[
                  { label: "PlantUML envelope", value: <StatusBadge status={c2Document.valid_envelope ? "SATISFIED" : "BLOCKED"} label={c2Document.valid_envelope ? "VALID" : "INVALID"} /> },
                  { label: "Concrete classes", value: c2Document.concrete_classes.length },
                  { label: "Abstract classes", value: c2Document.abstract_classes.length },
                  { label: "Enums", value: c2Document.enums.length },
                ]} />
              </div>
            ) : <p className="muted small">The original PlantUML stays unchanged for deterministic inspection.</p>}
          </div>
        </div>

        {sourceDocuments.c1Text ? (
          <section className="requirements-section">
            <div className="requirements-heading">
              <div>
                <h3>Extracted requirements</h3>
                <p>Stable C1 identities preserved from the uploaded document.</p>
              </div>
              <div className="requirement-legend">
                <span className="requirement-type requirement-type-fr">FR</span>
                <span className="requirement-type requirement-type-nfr">NFR</span>
              </div>
            </div>
            <Table
              dense
              rowKey={(row) => row.requirement_id}
              rows={c1Document.requirements}
              columns={[
                { key: "label", header: "Source" },
                { key: "requirement_id", header: "Requirement ID", render: (row) => <code>{row.requirement_id}</code> },
                { key: "kind", header: "Type", render: (row) => <span className={`requirement-type requirement-type-${row.kind.toLowerCase()}`}>{row.kind}</span> },
                { key: "statement", header: "Requirement statement" },
              ]}
            />
          </section>
        ) : null}

        {(sourceDocuments.c1Text || sourceDocuments.c2Text) ? (
          <Callout tone="warn" title={`${documentFindings.length} evidence and compatibility finding${documentFindings.length === 1 ? "" : "s"}`}>
            Generation is not marked ready while these source-contract gaps remain.
            <details className="finding-details">
              <summary>Review findings</summary>
              {documentFindings.map((issue) => (
                <div key={issue.code}><strong>{issue.code}:</strong> {issue.message}</div>
              ))}
            </details>
          </Callout>
        ) : null}
        <p className="muted small">
          This document intake is format/evidence inspection only. Use the complete JSON contract section below after C1 approval and C2 release metadata are available; only then can the real validation API create a GenerationContext.
        </p>
      </Card>

      <details className="advanced-tools">
        <summary>Advanced JSON contracts and simulated test fixtures</summary>
        <div className="advanced-tools-body">

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
          {compatibility?.adapted && !parsedC2.value?.validation_report_ref ? (
            <label className="source-text-label">
              C2 validation report reference
              <input
                type="text"
                aria-label="C2 validation report reference"
                placeholder="Actual reference, or clearly labelled SIMULATED-... PP1 reference"
                value={session.c2ValidationReportRef ?? ""}
                onChange={(event) => {
                  set("c2ValidationReportRef", event.target.value);
                  set("validation", null);
                }}
              />
            </label>
          ) : null}
        </Card>
      </div>

      {compatibility?.adapted ? (
        <Callout tone={compatibility.errors.length ? "sim" : "info"} title="PP1 JSON compatibility mapping active">
          {compatibility.warnings.map((warning) => <div key={warning}>• {warning}</div>)}
          {compatibility.errors.map((error) => <div key={error.code}><strong>{error.code}:</strong> {error.message}</div>)}
        </Callout>
      ) : null}

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
      </details>
    </div>
  );
}
