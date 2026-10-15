import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertOctagon,
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
import ExpandableDiagnostic from '../components/common/ExpandableDiagnostic';
import { getVerificationRuns } from '../api/verificationApi';
import { DEFECT_SEVERITIES } from '../utils/constants';
import { formatDate, formatRelativeTime, truncateId } from '../utils/formatters';

export default function DefectReportsPage() {
  const navigate = useNavigate();
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
      const runsResponse = await getVerificationRuns({ skip: 0, limit: 100 });
      const runs = runsResponse.items || [];

      // Extract all persisted defects across runs
      const extractedDefects = [];
      runs.forEach((run) => {
        if (run.defect_reports && Array.isArray(run.defect_reports)) {
          run.defect_reports.forEach((dr) => {
            extractedDefects.push({
              ...dr,
              run_id: run.id,
              run_created_at: run.created_at,
              submission_id: run.submission_id,
            });
          });
        }
      });

      // Sort newest first
      extractedDefects.sort((a, b) => new Date(b.created_at || b.run_created_at) - new Date(a.created_at || a.run_created_at));
      setDefects(extractedDefects);
    } catch (err) {
      setError(err.message || 'Unable to retrieve defect reports.');
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
            </h1>
            <p className="page-description">
              Evidence-based defect analysis synthesized from real pytest execution outcomes, assertions, and stack traces.
            </p>
          </div>
          <div className="page-actions">
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              onClick={() => fetchDefects(true)}
              loading={refreshing}
            >
              Refresh
            </Button>
          </div>
        </div>
      </div>

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
                backgroundColor: severityFilter === sev ? 'rgba(249, 115, 22, 0.15)' : 'var(--bg-tertiary)',
                color: severityFilter === sev ? 'var(--primary-400)' : 'var(--text-secondary)',
                cursor: 'pointer',
                fontWeight: severityFilter === sev ? 600 : 400,
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
                : 'All executed verification runs passed, or no failed verification runs exist yet. Defect reports are generated automatically from test run failures and assertion errors.'
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
                        <strong style={{ color: 'var(--text-muted)' }}>Severity:</strong>{' '}
                        <span style={{ color: DEFECT_SEVERITIES[defect.severity]?.variant === 'danger' ? 'var(--status-failed)' : 'var(--status-pending)', fontWeight: 600 }}>
                          {defect.severity}
                        </span>
                      </span>
                      {defect.file_path && (
                        <span>
                          <strong style={{ color: 'var(--text-muted)' }}>Location:</strong>{' '}
                          <code style={{ color: 'var(--text-primary)' }}>
                            {defect.file_path}{defect.line_number ? `:${defect.line_number}` : ''}
                          </code>
                        </span>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Button
                      variant="outline"
                      size="sm"
                      icon={ExternalLink}
                      onClick={() => navigate(`/verifications?inspect=${defect.run_id}`)}
                      style={{ fontSize: '0.72rem', height: '28px' }}
                    >
                      Inspect Run
                    </Button>
                  </div>
                </div>

                {/* Assertion / Failure Details Box */}
                <div
                  style={{
                    backgroundColor: 'var(--bg-input)',
                    padding: '0.625rem 0.85rem',
                    borderRadius: 'var(--radius-xs)',
                    border: '1px solid var(--border-color)',
                    fontSize: '0.75rem',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-primary)',
                    marginBottom: '0.5rem',
                  }}
                >
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.6875rem', marginBottom: '0.25rem', textTransform: 'uppercase' }}>
                    Failed Assertion / Error Detail:
                  </div>
                  <ExpandableDiagnostic
                    text={defect.assertion_or_exception || 'Assertion error detected during pytest execution'}
                    variant="danger"
                    maxLength={100}
                  />
                </div>

                {/* Expected vs Actual Value Comparison */}
                {(defect.expected_value || defect.actual_value) && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.5rem', fontSize: '0.75rem' }}>
                    <div style={{ padding: '0.5rem', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.6875rem', display: 'block' }}>Expected Value:</span>
                      <code style={{ color: 'var(--status-passed)' }}>{defect.expected_value || 'None'}</code>
                    </div>
                    <div style={{ padding: '0.5rem', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.6875rem', display: 'block' }}>Actual Value:</span>
                      <code style={{ color: 'var(--status-failed)' }}>{defect.actual_value || 'None'}</code>
                    </div>
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
    </div>
  );
}
