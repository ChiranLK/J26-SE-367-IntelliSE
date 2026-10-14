import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Code2,
  PlayCircle,
  Clock,
  CheckCircle2,
  RefreshCw,
  Plus,
  ArrowUpRight,
  Check,
  Copy,
} from 'lucide-react';
import Card from '../components/common/Card';
import StatCard from '../components/common/StatCard';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';
import EmptyState from '../components/common/EmptyState';
import LoadingSkeleton from '../components/common/LoadingSkeleton';
import CodeViewer from '../components/common/CodeViewer';
import Modal from '../components/common/Modal';
import { checkBackendHealth } from '../api/healthApi';
import { getSubmissions } from '../api/submissionApi';
import { getVerificationRuns } from '../api/verificationApi';
import { formatDate, formatRelativeTime, truncateId } from '../utils/formatters';
import { VERIFICATION_STATUSES } from '../utils/constants';

export default function DashboardPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [dismissStorageNotice, setDismissStorageNotice] = useState(false);
  
  // Backend data
  const [health, setHealth] = useState(null);
  const [submissionsData, setSubmissionsData] = useState({ total: 0, items: [] });
  const [verificationsData, setVerificationsData] = useState({ total: 0, items: [] });

  // Quick view modal
  const [selectedSubmission, setSelectedSubmission] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  const fetchDashboardData = async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const [healthRes, subRes, verRes] = await Promise.allSettled([
        checkBackendHealth(),
        getSubmissions({ skip: 0, limit: 10 }),
        getVerificationRuns({ skip: 0, limit: 10 }),
      ]);

      if (healthRes.status === 'fulfilled') {
        setHealth(healthRes.value);
      } else {
        setHealth(null);
      }

      if (subRes.status === 'fulfilled') {
        setSubmissionsData(subRes.value);
      } else {
        setSubmissionsData({ total: 0, items: [] });
      }

      if (verRes.status === 'fulfilled') {
        setVerificationsData(verRes.value);
      } else {
        setVerificationsData({ total: 0, items: [] });
      }

      if (healthRes.status === 'rejected' && subRes.status === 'rejected') {
        setError(subRes.reason?.message || 'Unable to connect to Component 4 backend service.');
      }
    } catch (err) {
      setError(err.message || 'An unexpected error occurred while loading dashboard telemetry.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const handleCopy = async (id) => {
    try {
      await navigator.clipboard.writeText(id);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      setCopiedId(null);
    }
  };

  // Status metrics calculated strictly from real backend responses
  const statusCounts = verificationsData.items.reduce(
    (acc, run) => {
      acc[run.status] = (acc[run.status] || 0) + 1;
      return acc;
    },
    { PENDING: 0, RUNNING: 0, PASSED: 0, FAILED: 0, ERROR: 0 }
  );

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">
              <span>Operational Telemetry</span>
            </h1>
            <p className="page-description">
              Verification pipeline monitor, code submission metrics, and runtime health for Component 4.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              loading={refreshing}
              onClick={() => fetchDashboardData(true)}
            >
              Refresh
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={Plus}
              onClick={() => navigate('/submissions/new')}
            >
              Submit Code
            </Button>
          </div>
        </div>
      </div>

      {/* Backend Offline Banner */}
      {error && (
        <Alert type="danger" title="Connection Interrupted" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Refined Contextual Ephemeral Storage Notice — Minimal, non-jarring */}
      {health && health.is_ephemeral_storage && !dismissStorageNotice && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.6rem 0.875rem',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'rgba(245, 158, 11, 0.05)',
            border: '1px solid rgba(245, 158, 11, 0.18)',
            marginBottom: '1.25rem',
            fontSize: '0.8125rem',
            color: 'var(--text-secondary)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: 'var(--status-pending)',
                boxShadow: '0 0 6px rgba(245, 158, 11, 0.5)',
                flexShrink: 0,
              }}
            />
            <span>
              <strong style={{ color: 'var(--text-primary)', fontWeight: 600 }}>Ephemeral In-Memory Mode:</strong>{' '}
              Storage backend is running in temporary memory (<code>{health.storage_backend}</code>). Submissions and verification runs will reset on server restart.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setDismissStorageNotice(true)}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: '0.75rem',
              padding: '2px 6px',
              borderRadius: 'var(--radius-xs)',
              marginLeft: '0.75rem',
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Key Metric Panels */}
      {loading ? (
        <div className="stat-card-grid">
          <LoadingSkeleton type="card" height="96px" />
          <LoadingSkeleton type="card" height="96px" />
          <LoadingSkeleton type="card" height="96px" />
          <LoadingSkeleton type="card" height="96px" />
        </div>
      ) : (
        <div className="stat-card-grid">
          <StatCard
            title="Total Submissions"
            value={submissionsData.total}
            icon={Code2}
            description="Stored codebases & snippets"
          />
          <StatCard
            title="Verification Runs"
            value={verificationsData.total}
            icon={PlayCircle}
            description="Agentic verification pipelines"
          />
          <StatCard
            title="Pending Queue"
            value={statusCounts.PENDING}
            icon={Clock}
            badge={<Badge variant="warning" dot>Phase 2 Queue</Badge>}
            description="Awaiting agent test runner"
          />
          <StatCard
            title="Verified (Passed)"
            value={statusCounts.PASSED}
            icon={CheckCircle2}
            badge={<Badge variant="success" dot>Zero Fabricated</Badge>}
            description="Passed with test evidence"
          />
        </div>
      )}

      {/* Two-Column Operational Activity Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(440px, 1fr))', gap: '1.25rem', marginBottom: '1.5rem' }}>
        
        {/* Recent Submissions */}
        <Card
          title="Recent Code Submissions"
          subtitle="Latest artifacts ingested for verification"
          action={
            <Link to="/submissions" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', color: 'var(--primary-300)' }}>
              <span>View All</span>
              <ArrowUpRight size={12} />
            </Link>
          }
        >
          {loading ? (
            <LoadingSkeleton type="table" rows={4} cols={3} />
          ) : submissionsData.items.length === 0 ? (
            <EmptyState
              title="No submissions recorded"
              description="Ingest code manually or upload files to begin verification testing."
              action={
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <Button size="sm" variant="primary" onClick={() => navigate('/submissions/new')} icon={Plus}>
                    Submit Code
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => navigate('/submissions/upload')} icon={Upload}>
                    Upload File
                  </Button>
                </div>
              }
            />
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Submission ID</th>
                    <th>Language</th>
                    <th>Filename</th>
                    <th>Submitted</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {submissionsData.items.slice(0, 5).map((sub) => (
                    <tr key={sub.id}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                          <span className="text-mono" style={{ color: 'var(--primary-300)', fontWeight: 500 }}>
                            {truncateId(sub.id, 12)}
                          </span>
                          <button
                            type="button"
                            className="btn-copy-id"
                            onClick={() => handleCopy(sub.id)}
                            title="Copy ID"
                          >
                            {copiedId === sub.id ? (
                              <Check size={12} color="var(--status-passed)" />
                            ) : (
                              <Copy size={12} />
                            )}
                          </button>
                        </div>
                      </td>
                      <td>
                        <Badge variant="secondary">{sub.language}</Badge>
                      </td>
                      <td>
                        <span style={{ color: sub.filename ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                          {sub.filename || '—'}
                        </span>
                      </td>
                      <td title={formatDate(sub.created_at)} style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                        {formatRelativeTime(sub.created_at)}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Button
                          variant="outline"
                          size="sm"
                          className="btn-table-action"
                          onClick={() => setSelectedSubmission(sub)}
                        >
                          Inspect
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Recent Verification Activity */}
        <Card
          title="Recent Verification Activity"
          subtitle="Pipeline execution telemetry"
          action={
            <Link to="/verifications" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', color: 'var(--primary-300)' }}>
              <span>View Pipelines</span>
              <ArrowUpRight size={12} />
            </Link>
          }
        >
          {loading ? (
            <LoadingSkeleton type="table" rows={4} cols={3} />
          ) : verificationsData.items.length === 0 ? (
            <EmptyState
              title="No verification pipelines"
              description="Register an automated test suite on an existing submission."
              action={
                <Button size="sm" variant="primary" onClick={() => navigate('/verifications')} icon={PlayCircle}>
                  Initiate Run
                </Button>
              }
            />
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Pipeline Run ID</th>
                    <th>Target Submission</th>
                    <th>Status</th>
                    <th>Trigger</th>
                    <th style={{ textAlign: 'right' }}>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {verificationsData.items.slice(0, 5).map((run) => {
                    const statusMeta = VERIFICATION_STATUSES[run.status] || {
                      label: run.status,
                      variant: 'secondary',
                    };
                    return (
                      <tr key={run.id}>
                        <td>
                          <span className="text-mono" style={{ color: 'var(--primary-300)', fontWeight: 500 }}>
                            {truncateId(run.id, 12)}
                          </span>
                        </td>
                        <td>
                          <span className="text-mono" style={{ color: 'var(--text-secondary)' }}>
                            {truncateId(run.submission_id, 10)}
                          </span>
                        </td>
                        <td>
                          <Badge variant={statusMeta.variant} dot>
                            {statusMeta.label}
                          </Badge>
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                          {run.triggered_by}
                        </td>
                        <td title={formatDate(run.created_at)} style={{ textAlign: 'right', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                          {formatRelativeTime(run.created_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Code Inspection Modal */}
      {selectedSubmission && (
        <Modal
          isOpen={!!selectedSubmission}
          onClose={() => setSelectedSubmission(null)}
          title={`Code Artifact: ${selectedSubmission.id}`}
          size="lg"
          footer={
            <>
              <Button
                variant="primary"
                size="sm"
                icon={PlayCircle}
                onClick={() => {
                  const subId = selectedSubmission.id;
                  setSelectedSubmission(null);
                  navigate(`/verifications?create_for=${encodeURIComponent(subId)}`);
                }}
              >
                Verify Artifact
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setSelectedSubmission(null)}>
                Close
              </Button>
            </>
          }
        >
          <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap', marginBottom: '1rem', fontSize: '0.8125rem' }}>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', display: 'block' }}>Language</span>
              <Badge variant="primary">{selectedSubmission.language}</Badge>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', display: 'block' }}>Filename</span>
              <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{selectedSubmission.filename || 'None'}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', display: 'block' }}>Submitted</span>
              <span style={{ color: 'var(--text-secondary)' }}>{formatDate(selectedSubmission.created_at)}</span>
            </div>
          </div>

          {selectedSubmission.requirement_ids && selectedSubmission.requirement_ids.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.35rem' }}>
                Requirements Traced:
              </span>
              <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                {selectedSubmission.requirement_ids.map((req, i) => (
                  <Badge key={i} variant="accent">
                    {req}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          <div style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
            Source Code Content:
          </div>
          <CodeViewer
            code={selectedSubmission.code}
            language={selectedSubmission.language}
            filename={selectedSubmission.filename}
          />
        </Modal>
      )}
    </div>
  );
}
