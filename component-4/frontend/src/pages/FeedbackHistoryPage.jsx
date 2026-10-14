import React from 'react';
import {
  RefreshCw,
  Repeat,
  ArrowRightLeft,
  GitPullRequest,
  ShieldCheck,
  CheckCircle2,
  Cpu,
  Layers,
  ArrowRight,
} from 'lucide-react';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';

export default function FeedbackHistoryPage() {
  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">
              <RefreshCw size={22} color="var(--primary-400)" />
              <span>Feedback Loop History</span>
              <Badge variant="accent" style={{ fontSize: '0.6875rem' }}>
                Phase 3 Reserved
              </Badge>
            </h1>
            <p className="page-description">
              Audit trail of iterative verification, defect communication, and corrective code repair cycles with Component 3.
            </p>
          </div>
        </div>
      </div>

      {/* Upcoming Feature Notice */}
      <Alert
        type="info"
        title="Bi-Directional Feedback Architecture"
      >
        Component 3 integration reserved for Phase 3. Real multi-turn repair loops and re-verification cycles will be recorded here once the Component 3 API bridge is active. No simulated or mock iterations are presented.
      </Alert>

      {/* Target Workflow Visualization */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.25rem', marginTop: '1.25rem' }}>
        
        {/* Workflow Stages */}
        <Card title="Target Closed-Loop Workflow" subtitle="Autonomous iteration cycle between Component 4 and Component 3">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            
            <div style={{ padding: '0.65rem 0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <ArrowRightLeft size={14} color="var(--accent-cyan)" />
                <span>Iteration 1 — Defect Communication</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                Component 4 detects test failures, extracts error logs and failed assertions, and dispatches a structured <code>DefectReport</code> payload to Component 3. (Human-facing XAI explanations are presented in UI).
              </p>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <GitPullRequest size={14} color="var(--primary-300)" />
                <span>Iteration 2 — Automated Code Refinement</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                Component 3 generates a targeted repair patch and resubmits refined code to Component 4 via <code>POST /api/v1/submissions</code> with source tag <code>component_3_api</code>.
              </p>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <Repeat size={14} color="var(--status-passed)" />
                <span>Iteration 3 — Re-Verification & Convergence</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                Component 4 re-executes tests to verify regression absence. The iteration closes with status <code>RESOLVED</code> once all suites pass with real evidence.
              </p>
            </div>
          </div>
        </Card>

        {/* Data Contract */}
        <Card title="Feedback Iteration Data Model" subtitle="app.schemas.feedback.FeedbackIteration contract">
          <pre
            style={{
              padding: '0.875rem',
              background: '#07080b',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-color)',
              fontSize: '0.75rem',
              fontFamily: 'var(--font-mono)',
              color: 'var(--accent-cyan)',
              overflowX: 'auto',
              lineHeight: 1.6,
            }}
          >
{`class FeedbackIteration(BaseModel):
    iteration_number: int = Field(ge=1)
    defects_reported: List[DefectReport]
    repaired_code_snippet: Optional[str]
    iteration_status: str  # "DISPATCHED" | "RESOLVED"
    reverification_run_id: Optional[str]
    created_at: datetime`}
          </pre>

          <div style={{ marginTop: '0.875rem', padding: '0.625rem', backgroundColor: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Each iteration will display diff comparisons between original and refined code, convergence velocity metrics, and reverification pass/fail statuses.
          </div>
        </Card>
      </div>
    </div>
  );
}
