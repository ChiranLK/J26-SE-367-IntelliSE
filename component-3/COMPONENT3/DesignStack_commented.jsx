import { useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { Badge, Button, Callout, Card, JsonView, KeyValues, Loading, PageHeader, SimulatedBadge, Stat, StatusBadge, Table } from "../components/ui.jsx";
import { CoverageRing, EvidenceChip } from "../components/visuals.jsx";
import { RunningSteps, pace, randomPaceMs } from "../components/RunningSteps.jsx";
import { BUILD_WEIGHT, DEFAULT_COMFORT, buildStackCriteria, deriveArchitecture, finalMarks, fitMarks, formatMarks, marksReason, unbuildableTechnologies, plainFailures, stackName, technologiesNamedIn } from "../lib/stackCriteria.js";
import { APPROVAL_STATUS, buildStackSelectionRequest } from "../lib/requests.js";
import { inspectC1SrsDocument, inspectC2PlantUmlDocument, normalizeDesignContextPlantUml } from "../lib/sourceDocumentIntake.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";

// Show a simple recovery message when design analysis or stack selection fails.
function FriendlyDesignError({ error, action, onReviewInputs }) {
  if (!error) return null;
  const details = Array.isArray(error.errors) ? error.errors : [];
  const repeatedEnvelope = details.some((item) =>
    item.code === "UNSUPPORTED_PLANTUML_CONSTRUCT" && /nested|repeated\s+@startuml/i.test(item.message ?? ""));
  const unavailable = error.kind === "network" || error.kind === "timeout" || (error.status ?? 0) >= 500;

  let title = `${action} could not be completed`;
  let message = details[0]?.message ?? error.message ?? "Please review the design input and try again.";
  if (repeatedEnvelope) {
    title = "The UML document contains more than one diagram";
    message = "Use one class diagram for design analysis. Keep use-case diagrams as separate UML artifacts, then rebuild the input contract.";
  } else if (unavailable) {
    title = "The design service is temporarily unavailable";
    message = "Wait a moment and try again. Your uploaded files have not been changed.";
  }

  return (
    <Callout tone="warn" title={title}>
      <div data-testid="error-panel">
        <p>{message}</p>
        <button type="button" className="link-button" onClick={onReviewInputs}>Review C1/C2 inputs</button>
      </div>
    </Callout>
  );
}

// The connector symbols of the diagram, in words. The symbol stays available as a tooltip.
// Translate PlantUML relationship types into words used by the Design page.
const CONNECTOR_WORDS = {
  "<|--": "is the parent of",
  "--|>": "is a kind of",
  "*--": "contains",
  "o--": "has",
  "-->": "uses",
  "..>": "depends on",
  "--": "is linked to",
};

// Notes about the way C3 itself split the uploaded file (one element per class) are not about the user's design.
const ADAPTER_NOISE = /was preserved but not parsed|were preserved\.|^Parsed \d+ classes/;

// Display parsed classes, fields, methods, relationships and useful diagnostics.
function Classes({ design }) {
  const notes = (design.diagnostics ?? []).filter((row) => !ADAPTER_NOISE.test(row.message ?? ""));
  return (
    <div className="grid grid-2">
      <Card title="Classes in the design" subtitle="Fields and actions read from the released class diagram.">
        {design.classes.length === 0 ? <p className="muted small">No class diagram parsed.</p> : null}
        {design.classes.map((cls) => (
          <div key={cls.name} className="class-box">
            <div className="class-name">{cls.name}</div>
            <div className="class-members">
              {cls.attributes.map((attribute) => (
                <div key={`a-${attribute.name}`}><code>{attribute.name}: {attribute.type_name}</code></div>
              ))}
              {cls.methods.map((method) => (
                <div key={`m-${method.name}`}>
                  <code>{method.name}({method.parameters.map((parameter) => `${parameter.name}: ${parameter.type_name}`).join(", ")}){method.return_type ? `: ${method.return_type}` : ""}</code>
                </div>
              ))}
            </div>
          </div>
        ))}
      </Card>
      <Card title="How the classes connect" subtitle="Read from the relationship lines of the class diagram.">
        <Table
          dense
          rowKey={(row, index) => `${row.source_class}-${row.target_class}-${index}`}
          rows={design.relationships}
          empty="No relationships found."
          columns={[
            { key: "source_class", header: "This class", render: (row) => <strong>{row.source_class}</strong> },
            { key: "connector", header: "Relation", render: (row) => <span title={row.connector}>{CONNECTOR_WORDS[row.connector] ?? "is linked to"}</span> },
            { key: "target_class", header: "That class", render: (row) => <strong>{row.target_class}</strong> },
            { key: "label", header: "Note" },
          ]}
        />
        {notes.length ? (
          <>
            <h3 className="subhead">Things to know</h3>
            <ul className="plain-list small">
              {notes.map((row, index) => <li key={`${row.code}-${index}`}>{row.message}</li>)}
            </ul>
          </>
        ) : null}
      </Card>
    </div>
  );
}

// Coverage depends on the actual requirements, UML elements and anchors, not only
// their release labels. Using the complete validated context prevents an older
// report from being reused when C1/C2 content is rebuilt under the same version.
// Create a stable browser-session key for results derived from one input context.
const contextKey = (context) => (context ? JSON.stringify(context) : null);

// APPLICATION PROFILE - RULE-BASED CRUD OR CUSTOM RECOMMENDATION
// This section reads approved C1/C2 content and recommends an application type.

// List the words that indicate a behaviour-focused application instead of simple CRUD.
const BEHAVIOUR_SIGNALS = [
  ["calculate", "calculation"],
  ["calculator", "calculator"],
  ["gpa", "GPA"],
  ["gradepoint", "grading rule"],
  ["grading policy", "grading policy"],
  ["workflow", "workflow"],
  ["payment", "payment processing"],
  ["authenticate", "authentication"],
  ["predict", "prediction"],
  ["schedule", "scheduling"],
];

// Start the application-profile recommendation using deterministic C1/C2 word matching.
function recommendApplicationProfile(context) {
  // Stop when validated C1/C2 input is not available.
  if (!context) return null;

  // Convert the complete accepted input to lowercase text for consistent matching.
  const inputText = JSON.stringify(context).toLowerCase();

  // Find supported behaviour words and remove duplicate result labels.
  const signals = [...new Set(BEHAVIOUR_SIGNALS
    .filter(([term]) => inputText.includes(term))
    .map(([, label]) => label))];

  // Recommend Custom / non-CRUD when at least one behaviour signal is found.
  if (signals.length) {
    return {
      // Save the profile value used by the generation process.
      profile: "CUSTOM_NON_CRUD",
      // Show the recommended profile name on the page.
      title: "Custom / non-CRUD application",
      // Explain which matched words caused this recommendation.
      reason: `The approved input contains behaviour-specific logic: ${signals.slice(0, 4).join(", ")}.`,
    };
  }

  // Recommend Schema-driven CRUD when no supported behaviour signal is found.
  return {
    // Save the profile value used by the generation process.
    profile: "SCHEMA_DRIVEN_CRUD",
    // Show the recommended profile name on the page.
    title: "Schema-driven CRUD application",
    // Explain why the input is treated as an entity-focused CRUD application.
    reason: "The approved input is primarily structured around entities and does not contain a supported calculation or workflow signal.",
  };
}

// A class no requirement points to can still serve one: it is joined by relationships to a class that does.
// Walks the diagram's relationship lines outwards from the linked classes and names the nearest one.
// Find design classes that support an anchored class through UML relationships.
function supportingClasses(report, relationships) {
  const linked = new Set(report.uml_elements.filter((item) => item.status === "ANCHORED").map((item) => item.name));
  const neighbours = new Map();
  for (const row of relationships) {
    neighbours.set(row.source_class, [...(neighbours.get(row.source_class) ?? []), row.target_class]);
    neighbours.set(row.target_class, [...(neighbours.get(row.target_class) ?? []), row.source_class]);
  }
  const nearest = new Map([...linked].map((name) => [name, name]));
  let frontier = [...linked];
  while (frontier.length) {
    const next = [];
    for (const name of frontier) {
      for (const other of neighbours.get(name) ?? []) {
        if (!nearest.has(other)) {
          nearest.set(other, nearest.get(name));
          next.push(other);
        }
      }
    }
    frontier = next;
  }
  return { nearest, neighbours };
}

// Present requirement coverage, linked classes and missing trace links.
function CoverageCard({ report, titles = {}, relationships = [] }) {
  const { totals } = report;
  const { nearest: servedBy, neighbours } = supportingClasses(report, relationships);
  const related = (name) => [...new Set(neighbours.get(name) ?? [])];
  const supporting = report.uml_elements.filter((item) => item.status !== "ANCHORED" && servedBy.has(item.name));
  const unconnected = report.uml_elements.filter((item) => item.status !== "ANCHORED" && !servedBy.has(item.name));
  const anchoredRequirements = report.requirements.filter((item) => item.status === "ANCHORED");
  const unanchored = report.requirements.filter((item) => item.status === "UNANCHORED_FR");
  const nfrs = report.requirements.filter((item) => item.status === "NFR_NOT_APPLICABLE");
  return (
    <div data-testid="coverage-card">
      <div className="coverage-layout">
        <CoverageRing value={totals.frs_anchored} total={totals.frs_anchored + totals.frs_unanchored} label="requirements linked" />
        <div className="coverage-detail">
          <div className="stats">
            <Stat label="Requirements linked" value={totals.frs_anchored} tone="ok" />
            <Stat label="Not linked" value={totals.frs_unanchored} tone={totals.frs_unanchored ? "bad" : undefined} />
            <Stat label="Quality rules" value={totals.nfrs} hint="not tied to one class" />
            <Stat label="Classes with a requirement" value={totals.uml_anchored} tone="ok" />
            <Stat label="Supporting classes" value={supporting.length} hint="joined to a linked class" />
            {unconnected.length ? <Stat label="Not connected" value={unconnected.length} tone="warn" /> : null}
          </div>
          <h3 className="subhead">Requirements ({report.requirements.length})</h3>
          <div className="chip-row" data-testid="coverage-requirements">
            {anchoredRequirements.map((item) => <span key={item.requirement_id} className="chip chip-ok" title={`${item.requirement_id} → ${item.anchored_uml_ids.join(", ")}`}>✓ {titles[item.requirement_id] || item.requirement_id}</span>)}
            {unanchored.map((item) => <span key={item.requirement_id} className="chip chip-bad" title={item.requirement_id}>✗ {titles[item.requirement_id] || item.requirement_id} · not linked</span>)}
            {nfrs.map((item) => <span key={item.requirement_id} className="chip chip-neutral" data-testid="nfr-chip" title={item.requirement_id}>Quality rule · {titles[item.requirement_id] || item.requirement_id}</span>)}
          </div>
          <h3 className="subhead">Classes ({report.uml_elements.length})</h3>
          <div className="chip-row" data-testid="coverage-uml">
            {report.uml_elements.map((item) => (
              <span
                key={item.uml_id}
                className={`chip ${item.status === "ANCHORED" ? "chip-ok" : servedBy.has(item.name) ? "chip-neutral" : "chip-warn"}`}
                data-status={item.status}
                title={item.anchored_requirement_ids.join(", ") || (servedBy.has(item.name) ? `joined in the diagram to: ${related(item.name).join(", ")}` : "no requirement linked")}
              >
                {item.status === "ANCHORED" ? `✓ ${item.name}` : servedBy.has(item.name) ? `${item.name} · related to ${related(item.name).slice(0, 2).join(", ")}${related(item.name).length > 2 ? ", …" : ""}` : `${item.name} · no requirement`}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// DESIGN & STACK PAGE PROCESS
// Orchestrate design analysis, coverage, application profile, stack comparison and approval.
export default function DesignStack({ navigate }) {
  const { session, set } = useSession();
  // Read the accepted input and any results already stored in the browser session.
  const generationContext = session.validation?.ok ? session.validation.generationContext : null;
  const design = session.designContext;
  const report = session.stackReport;
  const applicationProfile = session.applicationProfile ?? "SCHEMA_DRIVEN_CRUD";
  const fromDocuments = session.inputSources?.c2 === "C3_DOCUMENT_ADAPTER";
  const c1Title = useMemo(() => inspectC1SrsDocument(session.sourceDocuments?.c1Text ?? "").title, [session.sourceDocuments?.c1Text]);
  // Re-read uploaded documents only for labels and source summary values shown in the UI.
  const sourceDesign = useMemo(
    () => inspectC2PlantUmlDocument(session.sourceDocuments?.c2Text || session.c2InputText || ""),
    [session.sourceDocuments?.c2Text, session.c2InputText],
  );
  const sourceSummary = sourceDesign.source_summary;
  // Links between requirements and classes are the user's only when the C2 file carries them.
  const linksSupplied = !fromDocuments || Boolean(sourceSummary?.anchors);
  const requirementTitles = useMemo(
    () => Object.fromEntries((generationContext?.requirements ?? []).map((item) => [item.requirement_id, item.title])),
    [generationContext],
  );
  // Only class diagrams: use-case diagrams are counted on their own row.
  const classDiagrams = design
    ? design.source_uml_elements.filter((item) => {
      const kind = String(item.element_type ?? item.type ?? "").toUpperCase();
      return kind.endsWith("_DIAGRAM") && !kind.includes("USE_CASE");
    }).length || (sourceSummary?.uml_artifacts ?? 0) - (sourceSummary?.use_case_diagrams ?? 0) || design.source_uml_elements.length
    : 0;
  const projectName = design && /^[0-9a-f]{16,}$/i.test(design.project_id ?? "") && c1Title ? c1Title : design?.project_id;
  // Derive the suggested application profile and technology hints from C1/C2.
  const profileRecommendation = useMemo(
    () => recommendApplicationProfile(generationContext),
    [generationContext],
  );

  const named = useMemo(
    () => technologiesNamedIn(session.sourceDocuments?.c1Text, session.sourceDocuments?.c2Text),
    [session.sourceDocuments?.c1Text, session.sourceDocuments?.c2Text],
  );
  // Only what the documents name is used as a preference; team comfort stays neutral.
  const choices = useMemo(() => ({ frontend: named.frontend, backend: named.backend, comfort: { ...DEFAULT_COMFORT }, touched: false }), [named]);
  // Keep the human approval form and demo progress timing in local component state.
  const [approvedBy, setApprovedBy] = useState("");
  const [reference, setReference] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  // How long each button's step animation runs this time (10 to 20 s, chosen when the button is pressed).
  const [paces, setPaces] = useState({});
  const choosePace = (key) => {
    const ms = randomPaceMs();
    setPaces((current) => ({ ...current, [key]: ms }));
    return ms;
  };

  // Step 1: ask the backend to parse the validated C2 class diagram.
  const buildDesign = useAction(async () => {
    const started = Date.now();
    const ms = choosePace("design");
    const result = await api.buildDesignContext(normalizeDesignContextPlantUml(generationContext));
    await pace(started, ms);
    set("designContext", result);
    set("stackReport", null);
    set("stackCompare", null);
    set("approval", null);
    set("generationRun", null);
    set("structural", null);
    set("graph", null);
  });

  // Coverage: ask the backend which FRs and UML elements have C2 anchors.
  const computeCoverage = useAction(async () => {
    const started = Date.now();
    const ms = choosePace("coverage");
    const report = await api.designCoverage(normalizeDesignContextPlantUml(generationContext));
    await pace(started, ms);
    set("designCoverage", { contextKey: contextKey(generationContext), at: new Date().toISOString(), durationMs: Date.now() - started, report });
  });
  const coverage = session.designCoverage?.contextKey === contextKey(generationContext) ? session.designCoverage : null;
  const inputsSimulated = session.inputSources?.c1 === "SIMULATED_FIXTURE" || session.inputSources?.c2 === "SIMULATED_FIXTURE";

  // Step 3: send the design and deterministic criteria to backend stack selection.
  const selectStack = useAction(async () => {
    const started = Date.now();
    const ms = choosePace("stack");
    const base = buildStackCriteria({ named, choices, architecture });
    // 1) compare all four options for display; 2) pick the best one among the options that can be built now.
    const everything = await api.selectStack(buildStackSelectionRequest({ designContext: design, criteria: base }));
    const blocked = unbuildableTechnologies(everything);
    const buildable = blocked.length
      ? await api.selectStack(buildStackSelectionRequest({ designContext: design, criteria: buildStackCriteria({ named, choices, architecture, prohibited: blocked }) }))
      : everything;
    await pace(started, ms);
    set("stackCompare", everything);
    set("stackReport", buildable);
    set("approval", null);
    set("generationRun", null);
    set("structural", null);
    set("graph", null);
  });

  // Step 4: record the researcher's explicit approval or rejection in the session.
  const decide = (status) =>
    set("approval", {
      status,
      approvedBy: approvedBy.trim(),
      approvalReference: reference.trim(),
      acknowledgesProvisionalPolicy: acknowledged,
      at: new Date().toISOString(),
    });

  const candidates = (session.stackCompare ?? report)?.candidate_calculations ?? [];
  const approval = session.approval;
  const profileSupported = applicationProfile === "SCHEMA_DRIVEN_CRUD";
  const architecture = useMemo(() => deriveArchitecture((design?.classes ?? []).map((item) => item.name)), [design]);
  const compare = session.stackCompare ?? report;
  const selectedBuildable = report?.selected_stack?.generator_availability === "IMPLEMENTED";
  const canApprove = acknowledged && approvedBy.trim() && reference.trim() && selectedBuildable;
  // Changing the application profile invalidates all downstream generation results.
  const chooseProfile = (profile) => {
    set("applicationProfile", profile);
    set("approval", null);
    set("generationRun", null);
    set("behaviourRun", null);
    set("behaviourApp", null);
    set("preview", null);
    set("structural", null);
    set("graph", null);
  };

  return (
    <div className="page">
      <PageHeader
        title="Design & Stack"
        subtitle="Review the uploaded design, check requirement coverage, and choose the most suitable technology stack."
        badges={inputsSimulated ? <SimulatedBadge>DEMO INPUT</SimulatedBadge> : null}
      />

      {!generationContext ? (
        <Callout tone="warn" title="Review the input documents first">
          Complete the C1/C2 input review before continuing to design analysis.{" "}
          <button type="button" className="link-button" onClick={() => navigate("inputs")}>Go to C1/C2 Inputs</button>
        </Callout>
      ) : null}

      <Card
        title="1 · Review the design"
        subtitle="Read the uploaded class diagram and summarize its classes, fields, actions, and relationships."
        actions={<Button onClick={() => buildDesign.run()} loading={buildDesign.loading} disabled={!generationContext}>Analyze design</Button>}
      >
        {buildDesign.loading ? (
          <>
            <Loading label="Reading your design" startedAt={buildDesign.startedAt} />
            <RunningSteps startedAt={buildDesign.startedAt} durationMs={paces.design} label="Design analysis progress" steps={["Reading the classes", "Reading fields and actions", "Reading the relationships", "Linking requirements to the design"]} />
          </>
        ) : null}
        <FriendlyDesignError error={buildDesign.error} action="Design analysis" onReviewInputs={() => navigate("inputs")} />
        {design ? (
          <>
            <KeyValues
              items={[
                { label: "Project", value: projectName },
                ...(sourceSummary?.uml_version ? [{ label: "Design version", value: sourceSummary.uml_version }] : []),
                { label: "Requirements", value: design.requirements.length },
                { label: "Class diagrams", value: classDiagrams },
                { label: "Classes", value: design.classes.length },
                { label: "Relationships", value: design.relationships.length },
                { label: linksSupplied ? "Requirement links" : "Requirement links (matched by C3)", value: design.requirement_uml_anchors.length },
                // Only what the uploaded documents actually contain: no use-case or UI rows for things nobody supplied.
                ...(sourceSummary?.use_case_diagrams > 0 ? [{ label: "Use-case diagrams", value: sourceSummary.use_case_diagrams }] : []),
                ...(!fromDocuments && (sourceSummary?.ui_screens ?? 0) > 0 ? [{ label: "UI screens", value: sourceSummary.ui_screens }] : []),
                ...(!fromDocuments && (sourceSummary?.ui_components ?? design.ui_artifacts.length) > 0 ? [{ label: "UI components", value: sourceSummary?.ui_components ?? design.ui_artifacts.length }] : []),
              ]}
            />
            {sourceSummary?.anchors && sourceSummary.anchors !== design.requirement_uml_anchors.length ? (
              <Callout tone="warn" title="Refresh the input contract to preserve every trace link">
                The uploaded C2 document contains {sourceSummary.anchors} trace links, but this saved browser session contains {design.requirement_uml_anchors.length}.
                Go back to C1/C2 Inputs and select Build provisional contract &amp; validate once, then analyze the design again.
              </Callout>
            ) : null}
          </>
        ) : (
          <p className="muted small">Select Analyze design to review the uploaded class diagram.</p>
        )}
      </Card>
      {design ? <Classes design={design} /> : null}

      <Card
        title="Requirement coverage"
        subtitle="Check whether each functional requirement is connected to the relevant design element."
        actions={<Button onClick={() => computeCoverage.run()} loading={computeCoverage.loading} disabled={!generationContext}>Check requirement coverage</Button>}
      >
        <div className="result-head">
          {inputsSimulated ? <EvidenceChip kind="simulated">SIMULATED C1/C2 input</EvidenceChip> : null}
        </div>
        {computeCoverage.loading ? (
          <RunningSteps startedAt={computeCoverage.startedAt} durationMs={paces.coverage} label="Coverage check progress" steps={["Reading the requirements", "Reading the links to the design", "Matching requirements to classes", "Working out what is covered"]} />
        ) : null}
        <FriendlyDesignError error={computeCoverage.error} action="Requirement coverage check" onReviewInputs={() => navigate("inputs")} />
        {coverage ? (
          <CoverageCard report={coverage.report} titles={requirementTitles} relationships={design?.relationships ?? []} />
        ) : (
          !computeCoverage.loading && <p className="muted small">{generationContext ? "Select Check requirement coverage to see which requirements are represented in the design." : "Review the C1/C2 input first, then return here to check coverage."}</p>
        )}
      </Card>

      <Card title="2 · Application profile" subtitle="Choose how the approved requirements and class design should be turned into an application.">
        {profileRecommendation ? (
          <Callout tone="info" title={`Recommended for this input: ${profileRecommendation.title}`}>
            <p>{profileRecommendation.reason}</p>
            <p className="muted small">This recommendation uses deterministic rules over C1 requirement text and C2 UML names and methods. It does not call an LLM.</p>
            {applicationProfile !== profileRecommendation.profile ? (
              <button type="button" className="link-button" onClick={() => chooseProfile(profileRecommendation.profile)}>Use this recommendation</button>
            ) : null}
          </Callout>
        ) : null}
        <div className="profile-grid">
          <button type="button" className={`profile-card${profileSupported ? " profile-active" : ""}`} onClick={() => chooseProfile("SCHEMA_DRIVEN_CRUD")}>
            <strong>Schema-driven CRUD application</strong>
            <span>Implemented for independent entities with supported scalar fields.</span>
            {profileRecommendation?.profile === "SCHEMA_DRIVEN_CRUD" ? <Badge tone="info">Recommended for this input</Badge> : null}
          </button>
          <button type="button" className={`profile-card${!profileSupported ? " profile-active" : ""}`} onClick={() => chooseProfile("CUSTOM_NON_CRUD")}>
            <strong>Custom / non-CRUD application</strong>
            <span>Calculator, workflow, or another behaviour-focused application derived from the approved requirements and design.</span>
            {profileRecommendation?.profile === "CUSTOM_NON_CRUD" ? <Badge tone="info">Recommended for this input</Badge> : null}
          </button>
        </div>
      </Card>

      <Card
        title="3 · Compare technology options"
        subtitle="Compare the frontend and backend combinations for this design."
        actions={<Button onClick={() => selectStack.run()} loading={selectStack.loading} disabled={!design}>Compare technology options</Button>}
      >
        {selectStack.loading ? (
          <>
            <Loading label="Scoring four candidates" startedAt={selectStack.startedAt} />
            <RunningSteps startedAt={selectStack.startedAt} durationMs={paces.stack} label="Technology comparison progress" steps={["Collecting the candidate stacks", "Checking each against your design", "Scoring them with the project criteria", "Choosing the best fit"]} />
          </>
        ) : null}
        <FriendlyDesignError error={selectStack.error} action="Technology comparison" onReviewInputs={() => navigate("inputs")} />
        {report ? (
          <>
            <div className="stack-cards" data-testid="stack-cards">
              {candidates.map((row, index) => {
                const chosen = row.candidate.candidate_id === report.selected_stack.candidate.candidate_id;
                const failures = plainFailures(row.hard_constraint_failures);
                return (
                  <div key={row.candidate.candidate_id} className={`stack-card${chosen ? " stack-card-chosen" : " stack-card-dim"}`} data-selected={chosen ? "true" : "false"} style={{ animationDelay: `${index * 70}ms` }}>
                    <div className="stack-card-head">
                      <strong>{stackName(row.candidate)}</strong>
                      {chosen ? <Badge tone="ok">Selected</Badge> : null}
                    </div>
                    <div className="stack-marks" data-testid="stack-marks">
                      <span className="stack-marks-total">{formatMarks(finalMarks(row))}<small> / 10</small></span>
                      <div className="scorebar"><div className="scorebar-fill" style={{ width: `${Math.max(0, Math.min(100, finalMarks(row) * 10))}%` }} /></div>
                      <span className="small muted">Fit with your design {formatMarks(fitMarks(row))}/10</span>
                    </div>
                    <div className="stack-card-badges">
                      {!row.eligible ? <Badge tone="warn">Does not fit your documents</Badge> : null}
                    </div>
                    {failures.length ? <p className="small text-bad">{failures.join(". ")}.</p> : null}
                    {chosen ? <p className="small stack-card-note">Selected. This is the option you approve in step 4.</p> : null}
                  </div>
                );
              })}
            </div>
            <p className="small" data-testid="stack-reading">
              <strong>How your design was read:</strong> {architecture.label}, because {architecture.reason}.
              {named.frontend || named.backend ? " The technologies named in your documents were taken as preferences." : " Your documents name no technology."}
            </p>
            <p className="small"><strong>Why:</strong> {marksReason(report)}</p>
            <p className="muted small">Final marks = {Math.round((1 - BUILD_WEIGHT) * 100)}% fit with your design + {Math.round(BUILD_WEIGHT * 100)}% whether the generator for that combination exists.</p>
            <p className="muted small">The fit marks come from a fixed scoring policy and what your documents and class diagram show. The other combinations are listed for comparison only.</p>
            <details className="json-view">
              <summary>Scoring details</summary>
              <Table
                dense
                rowKey={(row) => row.criterion}
                rows={report.selected_stack.criterion_scores}
                columns={[
                  { key: "criterion", header: "Criterion" },
                  { key: "weight", header: "Weight" },
                  { key: "raw_score", header: "Raw" },
                  { key: "confidence", header: "Confidence" },
                  { key: "uncertainty_adjusted_score", header: "Adjusted" },
                  { key: "weighted_score", header: "Weighted" },
                  { key: "reason", header: "Reason" },
                ]}
              />
              <JsonView value={compare} summary="Full stack selection report (all four options)" />
            </details>
          </>
        ) : (
          <p className="muted small">Analyze the design first, then compare the available technology options.</p>
        )}
      </Card>

      <Card title="4 · Confirm the selection" subtitle="Generation remains paused until you review and approve the selected option.">
        {!report ? (
          <p className="muted small">Compare the technology options first.</p>
        ) : (
          <>
            <div className="form-grid">
              <label>
                Approved by
                <input value={approvedBy} placeholder="Your name or ID" onChange={(event) => setApprovedBy(event.target.value)} />
              </label>
              <label>
                Approval reference
                <input value={reference} placeholder="Your approval reference" onChange={(event) => setReference(event.target.value)} />
              </label>
            </div>
            <label className="check">
              <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />
              <span>
                I approve this technology choice so the app can be generated. The name above is not verified.
              </span>
            </label>
            <div className="button-row">
              <Button onClick={() => decide(APPROVAL_STATUS.APPROVED)} disabled={!canApprove}>
                Approve {report.selected_stack.candidate.frontend} + {report.selected_stack.candidate.backend}
              </Button>
              <Button variant="danger" onClick={() => decide(APPROVAL_STATUS.REJECTED)}>Reject</Button>
              <Button variant="ghost" onClick={() => set("approval", null)} disabled={!approval}>Clear decision</Button>
            </div>
            <div className="result-head">
              <span>Current decision:</span>
              {approval ? (
                <StatusBadge
                  status={approval.status === APPROVAL_STATUS.APPROVED ? "PROVISIONAL" : "BLOCKED"}
                  label={approval.status === APPROVAL_STATUS.APPROVED ? "APPROVED (provisional, unauthenticated)" : approval.status}
                />
              ) : (
                <StatusBadge status="PENDING" label="PENDING_RESEARCHER_APPROVAL" />
              )}
            </div>
            {approval?.status === APPROVAL_STATUS.APPROVED ? (
              <Button variant="secondary" onClick={() => navigate("generation")}>Continue to Code Generation</Button>
            ) : null}
          </>
        )}
      </Card>
    </div>
  );
}
