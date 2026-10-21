import { useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { Button, Card, ErrorPanel, PageHeader, Table } from "../components/ui.jsx";
import { buildProvisionalPackageFromSourceDocuments, inspectC1SrsDocument, inspectC2PlantUmlDocument } from "../lib/sourceDocumentIntake.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";
import { pace } from "../components/RunningSteps.jsx";

const SOURCE_DOCUMENT_ACCEPT = ".txt,.puml,.json";

// Demo pacing: the checking steps stay on screen for a moment so the work is visible (none in tests).
// Reading a chosen file takes a moment on screen too, so the details appear after it instead of all at once.
const FILE_READ_MS = import.meta.env.MODE === "test" ? 0 : 1500;
const MIN_VALIDATION_MS = import.meta.env.MODE === "test" ? 0 : 3200;
const wait = (ms) => (ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve());

const STEPS = [
  "Reading the requirements",
  "Reading the design",
  "Linking requirements to the design",
  "Checking everything with C3",
];

const plural = (count, word) => `${count} ${count === 1 ? word : word.endsWith("s") ? `${word}es` : `${word}s`}`;
const shortHash = (hash) => (hash ? `${hash.slice(0, 10)}…` : "Not supplied");

function CheckingSteps({ startedAt }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 300);
    return () => clearInterval(timer);
  }, []);
  const active = Math.min(STEPS.length - 1, Math.floor((now - startedAt) / 800));
  return (
    <ol className="gen-steps val-steps" aria-label="Validation progress">
      {STEPS.map((step, index) => (
        <li key={step} className={index < active ? "step-done" : index === active ? "step-active" : "step-wait"}>
          {index < active ? "✓" : index === active ? "…" : "○"} {step}
        </li>
      ))}
    </ol>
  );
}

function DocumentPanel({ id, title, hint, uploadLabel, fileName, text, textLabel, onFile, onText, reading, children }) {
  return (
    <div className={`source-document-panel source-document-panel-${id}`}>
      <div className="source-panel-heading">
        <span className="source-panel-id">{id.toUpperCase()}</span>
        <div>
          <h3>{title}</h3>
          <p>{hint}</p>
        </div>
      </div>
      <label className="file-pick">
        <span className="btn btn-secondary">{fileName ? "Choose another file" : "Choose a file"}</span>
        <input aria-label={uploadLabel} type="file" accept={SOURCE_DOCUMENT_ACCEPT} onChange={(event) => {
          const file = event.target.files?.[0];
          // Forget the chosen file right away: choosing the same file again (for example after Reset session) must still count.
          event.target.value = "";
          onFile(file);
        }}
      />
      </label>
      {reading ? (
        <p className="file-reading" role="status"><span className="spinner spinner-dark" aria-hidden="true" /> Reading {reading}…</p>
      ) : (
        <>
          <p className={`source-file-name${fileName ? " source-file-ready" : ""}`}>{fileName || "No file selected yet"}</p>
          {children}
        </>
      )}
      <details className="source-edit">
        <summary>Show or edit the text</summary>
        <textarea
          className="json-editor upstream-json-editor"
          aria-label={textLabel}
          spellCheck={false}
          placeholder="Paste the text here, or choose a file above."
          value={text}
          onChange={(event) => onText(event.target.value)}
        />
      </details>
    </div>
  );
}

export default function Inputs({ navigate }) {
  const { session, set, update } = useSession();
  const [reading, setReading] = useState({ c1: "", c2: "" });
  const sourceDocuments = session.sourceDocuments ?? { c1Name: "", c1Text: "", c2Name: "", c2Text: "" };
  const c1Document = useMemo(() => inspectC1SrsDocument(sourceDocuments.c1Text), [sourceDocuments.c1Text]);
  const c2Document = useMemo(() => inspectC2PlantUmlDocument(sourceDocuments.c2Text), [sourceDocuments.c2Text]);
  const validation = session.validation;
  const context = validation?.ok ? validation.generationContext : null;
  const bothFiles = Boolean(sourceDocuments.c1Text && sourceDocuments.c2Text);
  const canValidate = bothFiles && c1Document.requirements.length > 0 && c2Document.valid_envelope;

  // Anything derived from the previous input must not outlive it: a changed or failed-to-validate
  // input may never keep showing the old design, stack, approval or generated runs.
  const clearDerived = () => {
    for (const key of ["validation", "designCoverage", "designContext", "stackReport", "stackCompare", "generationAttempted", "approval", "generationRun", "behaviourRun", "behaviourApp", "structural", "graph", "preview"]) {
      set(key, null);
    }
    set("applicationProfile", "SCHEMA_DRIVEN_CRUD");
  };

  const updateSourceDocument = (component, value, name = "") => {
    // Built from the latest stored value: two files chosen one after the other must not overwrite each other.
    update("sourceDocuments", (current) => ({ ...(current ?? { c1Name: "", c1Text: "", c2Name: "", c2Text: "" }), [`${component}Name`]: name, [`${component}Text`]: value }));
    clearDerived();
  };

  const uploadSourceDocument = async (component, file) => {
    if (!file) return;
    const started = Date.now();
    setReading((current) => ({ ...current, [component]: file.name }));
    try {
      const text = await file.text();
      await pace(started, FILE_READ_MS);
      updateSourceDocument(component, text, file.name);
    } finally {
      setReading((current) => ({ ...current, [component]: "" }));
    }
  };

  // One button: builds the provisional contract from the two documents and validates it with C3.
  const validate = useAction(async () => {
    const started = Date.now();
    const packageFromDocuments = buildProvisionalPackageFromSourceDocuments(sourceDocuments.c1Text, sourceDocuments.c2Text);
    set("inputContractVersion", packageFromDocuments.contract_version);
    set("c1InputText", JSON.stringify(packageFromDocuments.c1, null, 2));
    set("c2InputText", JSON.stringify(packageFromDocuments.c2, null, 2));
    set("c2ValidationReportRef", packageFromDocuments.c2.validation_report_ref);
    set("inputSources", { c1: "C3_DOCUMENT_ADAPTER", c2: "C3_DOCUMENT_ADAPTER" });
    set("inputText", JSON.stringify(packageFromDocuments, null, 2));
    set("designCoverage", null);
    const at = new Date().toISOString();
    try {
      const generationContext = await api.validateInput(packageFromDocuments);
      await wait(MIN_VALIDATION_MS - (Date.now() - started));
      for (const key of ["designContext", "stackReport", "stackCompare", "approval", "generationRun", "behaviourRun", "behaviourApp", "structural", "graph"]) set(key, null);
      set("applicationProfile", "SCHEMA_DRIVEN_CRUD");
      set("validation", { ok: true, at, generationContext });
      return generationContext;
    } catch (error) {
      set("validation", {
        ok: false,
        at,
        error: { kind: error.kind, status: error.status, errors: error.errors ?? [], message: error.message, path: error.path },
      });
      throw error;
    }
  });

  const requirements = c1Document.requirements;

  return (
    <div className="page">
      <PageHeader title="C1/C2 Inputs" subtitle="Add the requirements document (C1) and the design (C2), then validate them in one step." />

      <Card title="Your documents" subtitle="Choose a .txt, .puml or .json file for each. Nothing is changed: the originals stay as they are.">
        <div className="grid grid-2 upstream-input-grid">
          <DocumentPanel
            id="c1"
            title="Requirements"
            hint="What the app must do (C1)"
            uploadLabel="Upload C1 SRS document"
            fileName={sourceDocuments.c1Name}
            text={sourceDocuments.c1Text}
            reading={reading.c1}
            textLabel="C1 finalized SRS text"
            onFile={(file) => uploadSourceDocument("c1", file)}
            onText={(value) => updateSourceDocument("c1", value, "pasted text")}
          >
            {sourceDocuments.c1Text ? (
              <p className="doc-summary" data-testid="c1-summary">
                <strong>{plural(requirements.length, "requirement")}</strong> found{c1Document.title ? <> in <em>{c1Document.title}</em></> : null}
              </p>
            ) : null}
          </DocumentPanel>
          <DocumentPanel
            id="c2"
            title="Design"
            hint="How the app is designed (C2)"
            uploadLabel="Upload C2 PlantUML document"
            fileName={sourceDocuments.c2Name}
            text={sourceDocuments.c2Text}
            reading={reading.c2}
            textLabel="C2 finalized PlantUML source"
            onFile={(file) => uploadSourceDocument("c2", file)}
            onText={(value) => updateSourceDocument("c2", value, "pasted text")}
          >
            {sourceDocuments.c2Text ? (
              <p className="doc-summary" data-testid="c2-summary">
                {c2Document.valid_envelope ? (
                  <>
                    <strong>{plural(c2Document.concrete_classes.length + c2Document.abstract_classes.length, "class")}</strong>
                    {c2Document.enums.length ? <>, {plural(c2Document.enums.length, "enum")}</> : null} found
                  </>
                ) : (
                  <span className="text-bad">This does not look like a complete PlantUML diagram (it needs @startuml and @enduml).</span>
                )}
              </p>
            ) : null}
          </DocumentPanel>
        </div>

        {requirements.length && !reading.c1 ? (
          <section className="requirements-section">
            <div className="requirements-heading">
              <div>
                <h3>What the app must do</h3>
                <p>{plural(requirements.length, "requirement")} read from your document.</p>
              </div>
              <div className="requirement-legend">
                <span className="requirement-type requirement-type-fr">FR</span> does something
                <span className="requirement-type requirement-type-nfr">NFR</span> quality rule
              </div>
            </div>
            <ol className="req-list">
              {requirements.map((row, index) => (
                <li key={row.requirement_id} className="req-row" style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }} title={row.requirement_id}>
                  <span className="req-number">{index + 1}</span>
                  <span className={`requirement-type requirement-type-${row.kind.toLowerCase()}`}>{row.kind}</span>
                  <span className="req-text">{row.statement}</span>
                </li>
              ))}
            </ol>
            <details className="finding-details">
              <summary>Technical details (requirement IDs, file fingerprint)</summary>
              <Table
                dense
                rowKey={(row) => row.requirement_id}
                rows={requirements}
                columns={[
                  { key: "label", header: "Source" },
                  { key: "requirement_id", header: "Requirement ID", render: (row) => <code>{row.requirement_id}</code> },
                  { key: "kind", header: "Type" },
                ]}
              />
              <p className="muted small">File fingerprint (SHA-256): <code>{shortHash(c1Document.source_sha256)}</code></p>
            </details>
          </section>
        ) : null}

        <div className="validate-row">
          <Button onClick={() => validate.run()} loading={validate.loading} disabled={!canValidate}>
            Validate inputs
          </Button>
          <span className="muted small">
            {canValidate
              ? "Pressing this accepts a provisional demo contract built from these two documents."
              : "Choose both files first."}
          </span>
        </div>
        {validate.loading ? <CheckingSteps startedAt={validate.startedAt} /> : null}
        <ErrorPanel error={validate.error} context="Validation" />
        {validation && !validation.ok && !validate.error ? <ErrorPanel error={validation.error} context="Validation" /> : null}

        {context && !validate.loading ? (
          <div className="val-success" role="status">
            <span className="val-check" aria-hidden="true">✓</span>
            <div>
              <strong>Inputs accepted</strong>
              <p className="muted small">
                {plural(context.requirements.length, "requirement")} and {plural(context.uml_elements.length, "design element")} passed C3 validation. Both documents match each other.
              </p>
            </div>
            <Button onClick={() => navigate("design")}>Continue to Design &amp; Stack →</Button>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
