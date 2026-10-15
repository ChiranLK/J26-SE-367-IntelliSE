import { Badge, Callout, Card, PageHeader, StatusBadge, Table } from "../components/ui.jsx";
import { deriveReadiness } from "../lib/readiness.js";
import { useSession } from "../state/session.jsx";

export default function Readiness() {
  const { session } = useSession();
  const readiness = deriveReadiness(session);

  return (
    <div className="page">
      <PageHeader
        title="Readiness"
        subtitle="Computed only from the real API results received in this session."
        badges={
          <>
            <StatusBadge status="PENDING" label="C4 RETEST PENDING" />
            <StatusBadge status="BLOCKED" label="DEPLOYMENT BLOCKED" />
          </>
        }
      />
      <Callout tone="info" title="No fabricated approvals">
        Component 3 cannot record a Component 4 result or approve deployment. Gates can be pending, review
        required, or blocked; they are never marked satisfied when the evidence does not exist.
      </Callout>

      <Card title="Workflow gates">
        <Table
          rowKey={(row) => row.id}
          rows={readiness.gates}
          columns={[
            { key: "title", header: "Gate", render: (row) => <strong>{row.title}</strong> },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={row.status} /> },
            { key: "detail", header: "Evidence" },
            { key: "source", header: "Source", render: (row) => <code>{row.source}</code> },
          ]}
        />
      </Card>

      <Card title="Deployment" tone="bad">
        <div className="result-head">
          <StatusBadge status={readiness.deployment.status} label="BLOCKED" />
          <Badge tone="neutral">Deployment is not implemented in Component 3 and was never attempted</Badge>
        </div>
        <ul className="blockers" data-testid="deployment-blockers">
          {readiness.deployment.blockers.map((item) => (<li key={item}>{item}</li>))}
        </ul>
      </Card>
    </div>
  );
}
