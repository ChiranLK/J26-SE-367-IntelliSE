import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
  RefreshCw,
  Filter,
  CheckCircle2,
  ExternalLink,
} from 'lucide-react';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';
import Button from '../components/common/Button';
import LoadingSkeleton from '../components/common/LoadingSkeleton';
import EmptyState from '../components/common/EmptyState';
import { getVerificationRuns } from '../api/verificationApi';
import { DEFECT_SEVERITIES } from '../utils/constants';
import { formatDate, formatRelativeTime, truncateId } from '../utils/formatters';

export default function DefectReportsPage() {
  const navigate = useNavigate();
  const [pageMode, setPageMode] = useState('live'); // 'live' or 'architecture'
  const [schemaTab, setSchemaTab] = useState('schema');

  const [defects, setDefects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [severityFilter, setSeverityFilter] = useState('ALL');

  const fetchDefects = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const runsData = await getVerificationRuns({ limit: 50 });
      const items = runsData.items || [];
      const extractedDefects = [];

      for (const run of items) {
        if (run.defect_reports && run.defect_reports.length > 0) {
          for (const defect of run.defect_reports) {
            extractedDefects.push({
              ...defect,
              run_id: run.id,
              submission_id: run.submission_id,
              run_status: run.status,
            });
          }
        }
      }

      setDefects(extractedDefects);
    } catch (err) {
      setError(err.message || 'Failed to fetch defect reports.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchDefects();
  }, []);

  const filteredDefects = defects.filter((d) => {
    if (severityFilter === 'ALL') return true;
    return d.severity === severityFilter;
  });

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">
              <AlertOctagon size={22} color="var(--status-failed)" />
              <span>Defect Reports</span>
              <Badge variant="warning" dot style={{ fontSize: '0.6875rem' }}>
                Phase 2C Active
              </Badge>
            </h1>
            <p className="page-description">
              Evidence-based defect analysis synthesized from real pytest execution outcomes, assertions, and stack traces.
            </p>
          </div>
          <div className="page-actions">
            <div className="segmented-tabs" style={{ marginRight: '0.5rem' }}>
              <button
                type="button"
                className={`segmented-tab-btn ${pageMode === 'live' ? 'active' : ''}`}
                onClick={() => setPageMode('live')}
              >
                Detected Defects ({defects.length})
              </button>
              <button
                type="button"
                className={`segmented-tab-btn ${pageMode === 'architecture' ? 'active' : ''}`}
                onClick={() => setPageMode('architecture')}
              >
                Diagnostic Architecture
              </button>
            </div>
            {pageMode === 'live' && (
              <Button
                variant="outline"
                size="sm"
                icon={RefreshCw}
                onClick={() => fetchDefects(true)}
                loading={refreshing}
              >
                Refresh
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Honest Diagnostic Notice */}
      <Alert
        type="warning"
        title="Phase 2 Architectural Specification"
      >
        Automated defect detection not active in Phase 2A. In strict compliance with research ethics, no fabricated defects or simulated assertion failures are presented. This workspace outlines the upcoming diagnostic schema and pipeline contract.
      </Alert>

      {pageMode === 'live' ? (
        <div style={{ marginTop: '1rem' }}>
          {error && (
            <Alert type="danger" title="Error Loading Defect Reports">
              {error}
            </Alert>
          )}


          {/* Filter Bar */}
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Filter size={13} /> Filter Severity:
            </span>
            {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((sev) => (
              <button
                key={sev}
                type="button"
                onClick={() => setSeverityFilter(sev)}
                style={{
                  padding: '0.25rem 0.6rem',
                  fontSize: '0.72rem',
                  borderRadius: 'var(--radius-xs)',
                  border: severityFilter === sev ? '1px solid var(--primary-500)' : '1px solid var(--border-color)',
                  backgroundColor: severityFilter === sev ? 'var(--primary-600)' : 'var(--bg-input)',
                  color: severityFilter === sev ? '#ffffff' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontWeight: 500,
                  transition: 'all 0.15s ease',
                }}
              >
                {sev}
              </button>
            ))}
          </div>

          {loading ? (
            <LoadingSkeleton lines={4} />
          ) : filteredDefects.length === 0 ? (
            <EmptyState
              icon={CheckCircle2}
              title="No Defect Reports Detected"
              description={
                severityFilter !== 'ALL'
                  ? `No defect reports with severity level '${severityFilter}' match current verification runs.`
                  : 'All executed verification runs passed, or no failed verification runs exist yet. Component 4 generates defect reports only from empirical test failures.'
              }
              action={
                <Button variant="primary" size="sm" onClick={() => navigate('/verifications')}>
                  View Verification Runs
                </Button>
              }
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
              {filteredDefects.map((defect) => (
                <Card key={defect.defect_id} style={{ borderLeft: '3px solid var(--status-failed)' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <Badge variant="danger" style={{ fontWeight: 600 }}>
                          {defect.failure_category || 'ASSERTION_FAILURE'}
                        </Badge>
                        <span className="text-mono" style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary)' }}>
                          {defect.failed_test || defect.title}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.35rem', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                        <span>
                          <strong style={{ color: 'var(--text-muted)' }}>Defect ID:</strong>{' '}
                          <code style={{ color: 'var(--text-primary)' }}>{defect.defect_id}</code>
                        </span>
                        <span>
                          <strong style={{ color: 'var(--text-muted)' }}>Affected File:</strong>{' '}
                          <code style={{ color: 'var(--primary-300)' }}>
                            {defect.file_path || 'solution.py'}{defect.line_number ? `:${defect.line_number}` : ''}
                          </code>
                        </span>
                        <span>
                          <strong style={{ color: 'var(--text-muted)' }}>Run ID:</strong>{' '}
                          <button
                            type="button"
                            onClick={() => navigate(`/verifications?run_id=${defect.run_id}`)}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: 'var(--primary-400)',
                              cursor: 'pointer',
                              padding: 0,
                              fontFamily: 'var(--font-mono)',
                              fontSize: '0.75rem',
                              textDecoration: 'underline',
                            }}
                          >
                            {truncateId(defect.run_id)}
                          </button>
                        </span>
                      </div>
                    </div>
                    <div>
                      <Badge
                        variant={DEFECT_SEVERITIES[defect.severity]?.variant || 'danger'}
                        dot
                        style={{ fontSize: '0.75rem' }}
                      >
                        {DEFECT_SEVERITIES[defect.severity]?.label || defect.severity}
                      </Badge>
                    </div>
                  </div>

                  {/* Expected vs Actual */}
                  {(defect.expected_value || defect.actual_value) && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.625rem', margin: '0.625rem 0' }}>
                      <div
                        style={{
                          padding: '0.5rem 0.75rem',
                          backgroundColor: 'rgba(16, 185, 129, 0.08)',
                          border: '1px solid rgba(16, 185, 129, 0.25)',
                          borderRadius: 'var(--radius-xs)',
                        }}
                      >
                        <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--status-passed)', fontWeight: 600, display: 'block' }}>
                          Expected Value
                        </span>
                        <span className="text-mono" style={{ fontSize: '0.8125rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                          {defect.expected_value || '—'}
                        </span>
                      </div>
                      <div
                        style={{
                          padding: '0.5rem 0.75rem',
                          backgroundColor: 'rgba(239, 68, 68, 0.08)',
                          border: '1px solid rgba(239, 68, 68, 0.25)',
                          borderRadius: 'var(--radius-xs)',
                        }}
                      >
                        <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--status-failed)', fontWeight: 600, display: 'block' }}>
                          Actual / Observed Value
                        </span>
                        <span className="text-mono" style={{ fontSize: '0.8125rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                          {defect.actual_value || '—'}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Assertion or Exception */}
                  {defect.assertion_or_exception && (
                    <div
                      style={{
                        padding: '0.5rem 0.75rem',
                        backgroundColor: 'var(--bg-input)',
                        borderRadius: 'var(--radius-xs)',
                        border: '1px solid var(--border-color)',
                        fontSize: '0.75rem',
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--status-failed)',
                        marginTop: '0.35rem',
                        wordBreak: 'break-word',
                      }}
                    >
                      {defect.assertion_or_exception}
                    </div>
                  )}

                  {/* Traceback Excerpt */}
                  {defect.traceback_excerpt && (
                    <details style={{ marginTop: '0.5rem' }}>
                      <summary style={{ fontSize: '0.72rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
                        View Traceback Excerpt
                      </summary>
                      <pre
                        style={{
                          margin: '0.35rem 0 0',
                          padding: '0.625rem',
                          background: '#07090e',
                          borderRadius: 'var(--radius-xs)',
                          border: '1px solid var(--border-color)',
                          fontSize: '0.72rem',
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-secondary)',
                          overflowX: 'auto',
                          maxHeight: '180px',
                          whiteSpace: 'pre-wrap',
                        }}
                      >
                        {defect.traceback_excerpt}
                      </pre>
                    </details>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>
      ) : (

        /* Architecture Specification View */
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.25rem' }}>
          <Card title="Automated Defect Extraction Pipeline" subtitle="How test failures are transformed into structured defect evidence">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ padding: '0.75rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem' }}>
                  <Terminal size={14} color="var(--primary-300)" />
                  <span>1. Isolated Pytest Execution</span>
                </div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                  Execution inside an unprivileged Docker sandbox produces JUnit XML and short tracebacks with explicit assertion diffs.
                </p>
              </div>

              <div style={{ padding: '0.75rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem' }}>
                  <ShieldAlert size={14} color="var(--status-failed)" />
                  <span>2. Deterministic Severity Classification</span>
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                  Defects are classified deterministically without speculation:
                  <div style={{ display: 'flex', gap: '0.35rem', marginTop: '0.35rem', flexWrap: 'wrap' }}>
                    <Badge variant="danger" dot>CRITICAL (Exception / Crash)</Badge>
                    <Badge variant="warning" dot>HIGH (Assertion Failure)</Badge>
                    <Badge variant="secondary">MEDIUM (Secondary failure)</Badge>
                    <Badge variant="secondary">LOW (Style / Warning)</Badge>
                  </div>
                </div>
              </div>

              <div style={{ padding: '0.75rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
                <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem' }}>
                  <Cpu size={14} color="var(--primary-300)" />
                  <span>3. Evidence-Based Localization</span>
                </div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                  Source file and line number are extracted strictly from real traceback frames referencing the submitted module.
                </p>
              </div>
            </div>
          </Card>

          <Card
            title="Backend Contract Specification"
            subtitle="Pydantic data model defined in app.schemas.defect_report"
            action={
              <div className="segmented-tabs">
                <button
                  type="button"
                  onClick={() => setSchemaTab('schema')}
                  className={`segmented-tab-btn ${schemaTab === 'schema' ? 'active' : ''}`}
                >
                  Python Pydantic
                </button>
                <button
                  type="button"
                  onClick={() => setSchemaTab('json')}
                  className={`segmented-tab-btn ${schemaTab === 'json' ? 'active' : ''}`}
                >
                  JSON Schema
                </button>
              </div>
            }
          >
            {schemaTab === 'schema' ? (
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
    defect_id: str
    verification_run_id: Optional[str]
    submission_id: Optional[str]
    failed_test: Optional[str]
    failure_category: Optional[str] # ASSERTION_FAILURE | RUNTIME_EXCEPTION
    severity: DefectSeverity        # CRITICAL | HIGH | MEDIUM | LOW
    assertion_or_exception: Optional[str]
    expected_value: Optional[str]
    actual_value: Optional[str]
    traceback_excerpt: Optional[str]
    file_path: Optional[str]
    line_number: Optional[int]
    evidence_references: dict
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
  "defect_id": "def-9e81b2c4d12a",
  "verification_run_id": "run-7dc0fb2ac3",
  "submission_id": "sub-4b827e",
  "failed_test": "test_subtraction",
  "failure_category": "ASSERTION_FAILURE",
  "severity": "HIGH",
  "assertion_or_exception": "assert 5 == 1",
  "expected_value": "1",
  "actual_value": "5",
  "file_path": "calculator.py"
}`}
              </pre>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
