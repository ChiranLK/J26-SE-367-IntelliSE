import { useState } from "react";
import { api } from "../api/endpoints.js";
import { Badge, Button, Callout, Card, ErrorPanel, JsonView, KeyValues, Loading, PageHeader, SimulatedBadge, StatusBadge, Table } from "../components/ui.jsx";
import { APPROVAL_STATUS, buildStackSelectionRequest } from "../lib/requests.js";
import { useSession } from "../state/session.jsx";
import { useAction } from "../state/useAction.js";

function ScoreBar({ value }) {
  const percent = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="scorebar" title={`${value}`}>
      <div className="scorebar-fill" style={{ width: `${percent}%` }} />
      <span>{value.toFixed(3)}</span>
    </div>
  );
}

function Classes({ design }) {
  return (
    <div className="grid grid-2">
      <Card title="Parsed classes" subtitle={`PlantUML subset parsed from ${design.source_uml_elements.length} C2 UML element(s)`}>
        {design.classes.length === 0 ? <p className="muted small">No class diagram parsed.</p> : null}
        {design.classes.map((cls) => (
          <div key={cls.name} className="class-box">
            <div className="class-name">{cls.name} <span className="muted small">from {cls.source_uml_id}</span></div>
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
      <Card title="Relationships and diagnostics">
        <Table
          dense
          rowKey={(row, index) => `${row.source_class}-${row.target_class}-${index}`}
          rows={design.relationships}
          empty="No relationships parsed."
          columns={[
            { key: "source_class", header: "From" },
            { key: "connector", header: "Connector", render: (row) => <code>{row.connector}</code> },
            { key: "target_class", header: "To" },
            { key: "label", header: "Label" },
          ]}
        />
        <h3 className="subhead">Diagnostics</h3>
        <Table
          dense
          rowKey={(row, index) => `${row.code}-${index}`}
          rows={design.diagnostics}
          empty="No diagnostics."
          columns={[
            { key: "severity", header: "Severity", render: (row) => <StatusBadge status={row.severity === "WARNING" ? "REVIEW_REQUIRED" : "NOT_REQUIRED"} label={row.severity} /> },
            { key: "code", header: "Code" },
            { key: "message", header: "Message" },
          ]}
        />
      </Card>
    </div>
  );
}

export default function DesignStack({ navigate }) {
  const { session, set } = useSession();
  const generationContext = session.validation?.ok ? session.validation.generationContext : null;
  const design = session.designContext;
  const report = session.stackReport;

  const [approvedBy, setApprovedBy] = useState("LOCAL-RESEARCHER-DEMO");
  const [reference, setReference] = useState(`SIMULATED-DEMO-APPROVAL-${new Date().toISOString().slice(0, 10)}`);
  const [acknowledged, setAcknowledged] = useState(false);

  const buildDesign = useAction(async () => {
    const result = await api.buildDesignContext(generationContext);
    set("designContext", result);
    set("stackReport", null);
    set("approval", null);
    set("generationRun", null);
    set("structural", null);
    set("graph", null);
  });

  const selectStack = useAction(async () => {
    const criteria = session.fixtures.stackCriteria ?? (await api.fixture("stack-criteria"));
    set("fixtures", { ...session.fixtures, stackCriteria: criteria });
    const result = await api.selectStack(buildStackSelectionRequest({ designContext: design, criteria: criteria.payload }));
    set("stackReport", result);
    set("approval", null);
    set("generationRun", null);
    set("structural", null);
    set("graph", null);
  });

  const decide = (status) =>
    set("approval", {
      status,
      approvedBy: approvedBy.trim(),
      approvalReference: reference.trim(),
      acknowledgesProvisionalPolicy: acknowledged,
      at: new Date().toISOString(),
    });

  const candidates = report ? report.candidate_calculations : [];
  const approval = session.approval;
  const canApprove = acknowledged && approvedBy.trim() && reference.trim();

  return (
    <div className="page">
      <PageHeader
        title="Design & Stack"
        subtitle="Parse the C2 design with FR-C3-02, score all four stack candidates, then approve explicitly."
        badges={<SimulatedBadge>SIMULATED INPUT · REAL C3 SERVICES</SimulatedBadge>}
      />

      {!generationContext ? (
        <Callout tone="warn" title="Validated input required">
          Run the C1/C2 validation first. This page only accepts the context the validation API returned.{" "}
          <button type="button" className="link-button" onClick={() => navigate("inputs")}>Go to C1/C2 Inputs</button>
        </Callout>
      ) : null}

      <Card
        title="1 · Parsed design information"
        subtitle="POST /api/v1/design-context"
        actions={<Button onClick={() => buildDesign.run()} loading={buildDesign.loading} disabled={!generationContext}>Build design context</Button>}
      >
        {buildDesign.loading ? <Loading label="Parsing design" startedAt={buildDesign.startedAt} /> : null}
        <ErrorPanel error={buildDesign.error} context="Design understanding" />
        {design ? (
          <KeyValues
            items={[
              { label: "Project", value: design.project_id },
              { label: "Design context version", value: design.design_context_version },
              { label: "Requirements", value: design.requirements.length },
              { label: "Parsed classes", value: design.classes.length },
              { label: "Relationships", value: design.relationships.length },
              { label: "Anchors", value: design.requirement_uml_anchors.length },
            ]}
          />
        ) : (
          <p className="muted small">Not built yet.</p>
        )}
      </Card>
      {design ? <Classes design={design} /> : null}

      <Card
        title="2 · Stack candidates and scores"
        subtitle="POST /api/v1/stack-selection · deterministic policy, four candidates"
        actions={<Button onClick={() => selectStack.run()} loading={selectStack.loading} disabled={!design}>Run stack selection</Button>}
      >
        {selectStack.loading ? <Loading label="Scoring four candidates" startedAt={selectStack.startedAt} /> : null}
        <ErrorPanel error={selectStack.error} context="Stack selection" />
        {report ? (
          <>
            <Callout tone="sim" title="Scoring inputs are provisional">
              Weights, architecture scores, and evidence confidences are PROVISIONAL RESEARCH POLICY
              ASSUMPTIONS. The manual criteria and evidence references come from a simulated fixture and
              are unverified.
            </Callout>
            <Table
              rowKey={(row) => row.candidate.candidate_id}
              rows={candidates}
              columns={[
                { key: "id", header: "Candidate", render: (row) => (<><strong>{row.candidate.frontend} + {row.candidate.backend}</strong><div className="muted small">{row.candidate.candidate_id}</div></>) },
                { key: "score", header: "Normalized score", render: (row) => <ScoreBar value={row.normalized_score} /> },
                { key: "eligible", header: "Eligible", render: (row) => <StatusBadge status={row.eligible ? "SATISFIED" : "BLOCKED"} label={row.eligible ? "eligible" : "excluded"} /> },
                { key: "gen", header: "Generator", render: (row) => (<><StatusBadge status={row.generator_availability === "IMPLEMENTED" ? "SATISFIED" : "NOT_IMPLEMENTED"} label={row.generator_availability.replaceAll("_", " ")} />{row.october_21_mvp_generator_target ? <Badge tone="info">Oct 21 target</Badge> : null}</>) },
                { key: "chosen", header: "Result", render: (row) => (row.candidate.candidate_id === report.selected_stack.candidate.candidate_id ? <Badge tone="ok">SELECTED</Badge> : <Badge tone="neutral">alternative</Badge>) },
                { key: "reason", header: "Decision reason", render: (row) => (<>{row.decision_reason}{row.hard_constraint_failures.length ? <div className="text-bad small">Hard failures: {row.hard_constraint_failures.join("; ")}</div> : null}</>) },
              ]}
            />
            <details className="json-view">
              <summary>Criterion scores for the selected stack</summary>
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
            </details>
            <p className="small"><strong>Selection reason:</strong> {report.selection_reason}</p>
            <ul className="small">
              {report.manual_approval_reasons.map((item) => (<li key={item}>{item}</li>))}
            </ul>
            <JsonView value={report} summary="Full stack selection report" />
          </>
        ) : (
          <p className="muted small">Not run yet.</p>
        )}
      </Card>

      <Card title="3 · Explicit provisional approval" subtitle="Generation stays blocked until a researcher approves. The backend re-checks this gate.">
        {!report ? (
          <p className="muted small">Run stack selection first.</p>
        ) : (
          <>
            <div className="form-grid">
              <label>
                Approved by
                <input value={approvedBy} onChange={(event) => setApprovedBy(event.target.value)} />
              </label>
              <label>
                Approval reference
                <input value={reference} onChange={(event) => setReference(event.target.value)} />
              </label>
            </div>
            <label className="check">
              <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />
              <span>
                I acknowledge this is a provisional research-policy approval for MVP generation and that
                the approving identity is not authenticated.
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
