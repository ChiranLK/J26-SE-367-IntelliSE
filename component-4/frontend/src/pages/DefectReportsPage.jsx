import React, { useState } from 'react';
import {
  AlertOctagon,
  Info,
  ShieldAlert,
  Cpu,
  ArrowRight,
  FileCode,
  Terminal,
  Layers,
  Bug,
  Code,
  Sparkles,
} from 'lucide-react';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';

export default function DefectReportsPage() {
  const [activeTab, setActiveTab] = useState('schema');

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">
              <AlertOctagon size={22} color="var(--status-failed)" />
              <span>Defect Reports</span>
              <Badge variant="warning" dot style={{ fontSize: '0.6875rem' }}>
                Phase 2 Reserved
              </Badge>
            </h1>
            <p className="page-description">
              Structured defect identification, severity classification, and stack trace synthesizer for verified artifacts.
            </p>
          </div>
        </div>
      </div>

      {/* Honest Upcoming-Feature Notice */}
      <Alert
        type="warning"
        title="Phase 2 Architectural Specification"
      >
        Automated defect detection not active in Phase 2A. In strict compliance with research ethics, no fabricated defects or simulated assertion failures are presented. This workspace outlines the upcoming diagnostic schema and pipeline contract.
      </Alert>

      {/* Pipeline Architecture Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.25rem', marginTop: '1.25rem' }}>
        
        {/* Left Column: Defect Engine Design */}
        <Card title="Automated Defect Extraction Pipeline" subtitle="How test failures will be transformed into structured defects">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            
            <div style={{ padding: '0.75rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem' }}>
                <Terminal size={14} color="var(--primary-300)" />
                <span>1. Multi-Agent Test Runner Execution</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Unit, integration, and performance agents execute test suites against the submitted codebase, capturing exit codes, stderr traces, and assertion diffs.
              </p>
            </div>

            <div style={{ padding: '0.75rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem' }}>
                <ShieldAlert size={14} color="var(--status-failed)" />
                <span>2. Severity Classification Matrix</span>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Defects are classified into 4 strict tiers:
                <div style={{ display: 'flex', gap: '0.35rem', marginTop: '0.35rem', flexWrap: 'wrap' }}>
                  <Badge variant="danger" dot>CRITICAL (Syntax / Panic)</Badge>
                  <Badge variant="warning" dot>HIGH (Assertion Failure)</Badge>
                  <Badge variant="secondary">MEDIUM (Performance)</Badge>
                  <Badge variant="secondary">LOW (Style / Lint)</Badge>
                </div>
              </div>
            </div>

            <div style={{ padding: '0.75rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem' }}>
                <Cpu size={14} color="var(--primary-300)" />
                <span>3. Requirement Correlation</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Every detected failure is mapped to the associated <code>requirement_ids</code> provided at submission time, facilitating traceability in research reports.
              </p>
            </div>
          </div>
        </Card>

        {/* Right Column: Schema Explorer */}
        <Card
          title="Backend Contract Specification"
          subtitle="Pydantic data model defined in app.schemas.defect_report"
          action={
            <div className="segmented-tabs">
              <button
                type="button"
                onClick={() => setActiveTab('schema')}
                className={`segmented-tab-btn ${activeTab === 'schema' ? 'active' : ''}`}
              >
                Python Pydantic
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('json')}
                className={`segmented-tab-btn ${activeTab === 'json' ? 'active' : ''}`}
              >
                JSON Schema
              </button>
            </div>
          }
        >
          {activeTab === 'schema' ? (
            <pre
              style={{
                padding: '0.875rem',
                background: '#07080b',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-color)',
                fontSize: '0.75rem',
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-primary)',
                overflowX: 'auto',
                lineHeight: 1.6,
              }}
            >
{`class DefectReport(BaseModel):
    id: str = Field(description="Unique defect ID (def-...)")
    verification_run_id: str
    severity: DefectSeverity  # LOW | MEDIUM | HIGH | CRITICAL
    category: str             # e.g., "assertion_failure"
    description: str          # Concise human summary
    location: Optional[str]   # File, line number, or function
    stack_trace: Optional[str]# Normalized compiler / test trace
    suggested_fix: Optional[str] # Algorithmic hint
    requirement_id: Optional[str]# Correlated REQ tag
    created_at: datetime`}
            </pre>
          ) : (
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
{`{
  "id": "def-9e81b2c4",
  "verification_run_id": "run-7dc0fb2ac3",
  "severity": "HIGH",
  "category": "unit_test_failure",
  "description": "Expected result 42, got null",
  "location": "math_utils.py:14",
  "requirement_id": "REQ-MATH-01"
}`}
            </pre>
          )}

          <div style={{ marginTop: '0.875rem', padding: '0.625rem', backgroundColor: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Once Phase 2 testing agents are deployed, this interface will render live stack trace inspector trees, code diff sidecars, and automated patch proposals.
          </div>
        </Card>
      </div>
    </div>
  );
}
