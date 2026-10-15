import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
  ExternalLink,
  Clock,
  AlertTriangle,
  AlertOctagon,
  FileJson,
  Hash,
  Send,
  Lock,
  UserCheck,
  Check,
  Copy,
  Bug,
  Terminal,
  FileCode,
  Search,
  Filter,
} from 'lucide-react';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';
import Button from '../components/common/Button';
import LoadingSkeleton from '../components/common/LoadingSkeleton';
import EmptyState from '../components/common/EmptyState';
import { getVerificationRuns, getComponent3Status } from '../api/verificationApi';
import { formatDate, formatRelativeTime, truncateId } from '../utils/formatters';

export default function FeedbackHistoryPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [c3Status, setC3Status] = useState(null);
  const [iterationsList, setIterationsList] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [copiedKey, setCopiedKey] = useState(null);
  const [error, setError] = useState(null);

  const fetchData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const [runsData, statusData] = await Promise.all([
        getVerificationRuns({ limit: 100 }),
        getComponent3Status().catch(() => null),
      ]);

      setC3Status(statusData);

      // Extract all feedback iterations from verification runs
      const extracted = [];
      const runs = runsData.items || [];
      for (const run of runs) {
        if (run.feedback_iterations && run.feedback_iterations.length > 0) {
          for (const iter of run.feedback_iterations) {
            extracted.push({
              ...iter,
              run_id: iter.verification_run_id || run.id,
              submission_id: iter.submission_id || run.submission_id,
              run_status: run.status,
              run_defects_count: run.defect_reports?.length || 0,
            });
          }
        }
      }

      // Sort by creation or update timestamp descending
      extracted.sort((a, b) => {
        const dateA = new Date(a.updated_at || a.created_at || 0);
        const dateB = new Date(b.updated_at || b.created_at || 0);
        return dateB - dateA;
      });

      setIterationsList(extracted);
    } catch (err) {
      setError(err.message || 'Failed to load feedback iteration history');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCopy = async (key, text) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    } catch {
      setCopiedKey(null);
    }
  };

  const getApprovalBadge = (status) => {
    switch (status) {
      case 'APPROVED':
        return <Badge variant="success" dot>APPROVED</Badge>;
      case 'REJECTED':
        return <Badge variant="danger" dot>REJECTED</Badge>;
      default:
        return <Badge variant="secondary">NOT_REQUESTED</Badge>;
    }
  };

  const getDeliveryBadge = (status) => {
    switch (status) {
      case 'ACKNOWLEDGED':
        return <Badge variant="success">ACKNOWLEDGED</Badge>;
      case 'PENDING_DELIVERY':
        return <Badge variant="warning">PENDING_DELIVERY</Badge>;
      case 'DISPATCHED':
        return <Badge variant="accent">DISPATCHED</Badge>;
      case 'NOT_DISPATCHED':
        return <Badge variant="secondary">NOT_DISPATCHED</Badge>;
      case 'FAILED':
        return <Badge variant="danger">FAILED</Badge>;
      case 'UNKNOWN':
        return <Badge variant="warning">UNKNOWN</Badge>;
      default:
        return <Badge variant="secondary">PENDING</Badge>;
    }
  };

  // Filter iterations by search term and status
  const filteredIterations = iterationsList.filter((iter) => {
    const q = searchQuery.trim().toLowerCase();
    const matchesSearch =
      !q ||
      (iter.run_id && iter.run_id.toLowerCase().includes(q)) ||
      (iter.submission_id && iter.submission_id.toLowerCase().includes(q)) ||
      (iter.iteration_id && iter.iteration_id.toLowerCase().includes(q)) ||
      (iter.correlation_id && iter.correlation_id.toLowerCase().includes(q)) ||
      (iter.approved_by && iter.approved_by.toLowerCase().includes(q));

    const matchesStatus =
      statusFilter === 'ALL' ||
      (statusFilter === 'APPROVED' && iter.approval_status === 'APPROVED') ||
      (statusFilter === 'ACKNOWLEDGED' && iter.delivery_status === 'ACKNOWLEDGED') ||
      (statusFilter === 'NOT_DISPATCHED' && iter.delivery_status === 'NOT_DISPATCHED') ||
      (statusFilter === 'FAILED' && iter.delivery_status === 'FAILED') ||
      (statusFilter === 'UNKNOWN' && iter.delivery_status === 'UNKNOWN');

    return matchesSearch && matchesStatus;
  });

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">
              <RefreshCw size={22} color="var(--primary-400)" />
              <span>Feedback Loop History</span>
              <Badge variant="accent" style={{ fontSize: '0.6875rem' }}>
                Repair Integration
              </Badge>
            </h1>
            <p className="page-description">
              Auditable governance lifecycle for technical feedback packages, human approval events, and repair integration iterations.
            </p>
          </div>
          <div>
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              loading={refreshing}
              onClick={() => fetchData(true)}
            >
              Refresh History
            </Button>
          </div>
        </div>
      </div>


      {/* Integration Readiness Diagnostic Banner */}
      <div
        style={{
          padding: '0.75rem 1rem',
          backgroundColor: 'rgba(234, 88, 12, 0.05)',
          border: '1px solid rgba(234, 88, 12, 0.25)',
          borderRadius: 'var(--radius-sm)',
          marginBottom: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Cpu size={18} color="var(--primary-400)" />
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--text-primary)' }}>
                Repair Integration Status
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Target Service: <code>{c3Status?.base_url || 'http://127.0.0.1:8000'}{c3Status?.endpoint || '/api/v1/correction-feedback'}</code>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Badge variant="outline">
              Contract: {c3Status?.contract_status || 'UNDER_DEVELOPMENT'}
            </Badge>
            <Badge variant={c3Status?.dispatch_allowed ? 'success' : 'secondary'}>
              Live Delivery: {c3Status?.dispatch_allowed ? 'Active' : 'Disabled (Safety Lock)'}
            </Badge>
          </div>
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.45rem' }}>
          {c3Status?.reason ? c3Status.reason.replace(/Component 3 code correction contract is (currently )?under development(\.?| in the shared repository\.?)/i, 'Automatic repair delivery is currently unavailable.') : 'Automatic repair delivery is currently unavailable. Fail-closed safety is enforced: automated delivery remains disabled until a verified endpoint is available.'}
        </div>
      </div>

      {error && (
        <Alert type="error" title="Data Retrieval Error" style={{ marginBottom: '1.25rem' }}>
          {error}
        </Alert>
      )}

      {/* Top Metric Strip / Filter Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Persisted Feedback Iterations ({iterationsList.length})
          </span>
          <Badge variant="secondary" style={{ fontSize: '0.6875rem' }}>
            {iterationsList.filter((i) => i.approval_status === 'APPROVED').length} Approved
          </Badge>
          <Badge variant="outline" style={{ fontSize: '0.6875rem' }}>
            {iterationsList.filter((i) => i.delivery_status === 'ACKNOWLEDGED').length} Acknowledged
          </Badge>
        </div>

        {/* Search & Filter Toolbar */}
        {iterationsList.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', width: '220px' }}>
              <input
                type="text"
                placeholder="Search run, sub, approver..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.35rem 0.6rem 0.35rem 1.8rem',
                  fontSize: '0.75rem',
                  backgroundColor: 'var(--bg-input)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-xs)',
                  color: 'var(--text-primary)',
                }}
              />
              <Search
                size={12}
                color="var(--text-muted)"
                style={{ position: 'absolute', left: '0.55rem', top: '50%', transform: 'translateY(-50%)' }}
              />
            </div>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                padding: '0.35rem 0.6rem',
                fontSize: '0.75rem',
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-xs)',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              <option value="ALL">All Delivery States</option>
              <option value="APPROVED">Approved</option>
              <option value="ACKNOWLEDGED">Acknowledged</option>
              <option value="NOT_DISPATCHED">Not Dispatched</option>
              <option value="FAILED">Failed</option>
              <option value="UNKNOWN">Unknown Outcome</option>
            </select>
          </div>
        )}
      </div>

      {/* Responsive Feedback Iteration Cards */}
      <div style={{ marginBottom: '2rem' }}>
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <LoadingSkeleton rows={3} />
            <LoadingSkeleton rows={3} />
          </div>
        ) : filteredIterations.length === 0 ? (
          <Card>
            <EmptyState
              icon={FileJson}
              title={iterationsList.length === 0 ? 'No Feedback Iterations Recorded Yet' : 'No Matching Iterations Found'}
              description={
                iterationsList.length === 0
                  ? 'When an eligible verification run fails, human reviewers can inspect the structured technical feedback preview and approve it for repair dispatch.'
                  : 'Try adjusting your search query or status filter.'
              }
              action={
                iterationsList.length === 0 ? (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => navigate('/verifications')}
                  >
                    Go to Verification Runs
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSearchQuery('');
                      setStatusFilter('ALL');
                    }}
                  >
                    Clear Filters
                  </Button>
                )
              }
            />
          </Card>
        ) : (
          <div className="feedback-iterations-list">
            {filteredIterations.map((iter) => (
              <div
                key={`${iter.run_id}-${iter.iteration_id || iter.iteration_number}`}
                className="feedback-iteration-card"
              >
                {/* Header Row: Iteration badge, IDs, Status badges, and Action */}
                <div className="iteration-card-header">
                  <div className="iteration-card-header-left">
                    <span className="iteration-badge">#{iter.iteration_number}</span>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                          Iteration {iter.iteration_id || `#${iter.iteration_number}`}
                        </span>
                        {iter.iteration_id && (
                          <button
                            type="button"
                            className="iteration-copy-icon-btn"
                            title="Copy Iteration ID"
                            onClick={() => handleCopy(`iter-${iter.iteration_id}`, iter.iteration_id)}
                          >
                            {copiedKey === `iter-${iter.iteration_id}` ? (
                              <Check size={13} color="var(--status-passed)" />
                            ) : (
                              <Copy size={13} />
                            )}
                          </button>
                        )}
                      </div>
                      <div style={{ fontSize: '0.71875rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '2px' }}>
                        <Clock size={12} />
                        <span>{formatDate(iter.updated_at || iter.created_at)}</span>
                        <span>•</span>
                        <span>{formatRelativeTime(iter.updated_at || iter.created_at)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="iteration-card-header-right">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      {getApprovalBadge(iter.approval_status)}
                      {getDeliveryBadge(iter.delivery_status)}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      icon={ExternalLink}
                      onClick={() => navigate(`/verifications?run_id=${iter.run_id}`)}
                      style={{ height: '28px', fontSize: '0.75rem' }}
                    >
                      Inspect Run
                    </Button>
                  </div>
                </div>

                {/* Multi-Column Information Grid */}
                <div className="iteration-card-body-grid">
                  {/* Column 1: Verification & Submission Reference */}
                  <div className="iteration-detail-col">
                    <div className="iteration-detail-label">
                      <Terminal size={12} color="var(--primary-400)" />
                      <span>Verification & Run ID</span>
                    </div>
                    <div className="iteration-detail-value">
                      <div className="iteration-mono-chip">
                        <button
                          type="button"
                          className="btn-link"
                          style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', padding: 0, textAlign: 'left', wordBreak: 'break-all' }}
                          onClick={() => navigate(`/verifications?run_id=${iter.run_id}`)}
                          title="Navigate to Verification Run"
                        >
                          {iter.run_id}
                        </button>
                        <button
                          type="button"
                          className="iteration-copy-icon-btn"
                          title="Copy Run ID"
                          onClick={() => handleCopy(`run-${iter.run_id}`, iter.run_id)}
                        >
                          {copiedKey === `run-${iter.run_id}` ? (
                            <Check size={12} color="var(--status-passed)" />
                          ) : (
                            <Copy size={12} />
                          )}
                        </button>
                      </div>

                      {iter.submission_id && (
                        <div style={{ fontSize: '0.71875rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.35rem' }}>
                          <span>Sub: <code style={{ color: 'var(--text-primary)', fontSize: '0.72rem' }}>{iter.submission_id}</code></span>
                          <button
                            type="button"
                            className="iteration-copy-icon-btn"
                            title="Copy Submission ID"
                            onClick={() => handleCopy(`sub-${iter.submission_id}`, iter.submission_id)}
                          >
                            {copiedKey === `sub-${iter.submission_id}` ? (
                              <Check size={11} color="var(--status-passed)" />
                            ) : (
                              <Copy size={11} />
                            )}
                          </button>
                        </div>
                      )}

                      <div className="iteration-defect-chip">
                        <Bug size={12} />
                        <span>{iter.defects_count || iter.run_defects_count || 0} defect report(s)</span>
                      </div>
                    </div>
                  </div>

                  {/* Column 2: Human Review & Authorization */}
                  <div className="iteration-detail-col">
                    <div className="iteration-detail-label">
                      <UserCheck size={12} color="var(--accent-cyan)" />
                      <span>Human Authorization</span>
                    </div>
                    <div className="iteration-detail-value">
                      <div style={{ fontWeight: 500, color: 'var(--text-primary)', fontSize: '0.78125rem' }}>
                        {iter.approval_status === 'APPROVED' ? 'Explicit Human Authorization' : 'Pending Authorization'}
                      </div>
                      {iter.approved_by ? (
                        <div style={{ fontSize: '0.71875rem', color: 'var(--text-secondary)' }}>
                          by {iter.approved_by}
                        </div>
                      ) : (
                        <div style={{ fontSize: '0.71875rem', color: 'var(--text-muted)' }}>
                          No reviewer assigned
                        </div>
                      )}
                      {iter.approved_at && (
                        <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                          Authorized: {formatDate(iter.approved_at)}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Column 3: Repair Service Delivery Status */}
                  <div className="iteration-detail-col">
                    <div className="iteration-detail-label">
                      <Cpu size={12} color="var(--primary-400)" />
                      <span>Repair Service Delivery</span>
                    </div>
                    <div className="iteration-detail-value">
                      {iter.component_3_job_id ? (
                        <div className="iteration-mono-chip">
                          <span style={{ fontSize: '0.72rem' }}>Job: {iter.component_3_job_id}</span>
                          <button
                            type="button"
                            className="iteration-copy-icon-btn"
                            title="Copy Job ID"
                            onClick={() => handleCopy(`job-${iter.component_3_job_id}`, iter.component_3_job_id)}
                          >
                            {copiedKey === `job-${iter.component_3_job_id}` ? (
                              <Check size={12} color="var(--status-passed)" />
                            ) : (
                              <Copy size={12} />
                            )}
                          </button>
                        </div>
                      ) : iter.component_3_acknowledged ? (
                        <Badge variant="success">Acknowledged</Badge>
                      ) : (
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          Delivery Unavailable
                        </span>
                      )}

                      {iter.error_category && (
                        <div style={{ fontSize: '0.71875rem', color: 'var(--status-failed)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                          <AlertTriangle size={12} />
                          <span>{iter.error_category}</span>
                        </div>
                      )}

                      {iter.sanitized_error_message && (
                        <div style={{ fontSize: '0.6875rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          {iter.sanitized_error_message}
                        </div>
                      )}

                      {iter.attempt_count > 0 && (
                        <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                          Attempts: {iter.attempt_count}
                        </div>
                      )}

                      {iter.dispatched_at && (
                        <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                          Dispatched: {formatDate(iter.dispatched_at)}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Column 4: Traceability & Identifiers */}
                  <div className="iteration-detail-col">
                    <div className="iteration-detail-label">
                      <Hash size={12} color="var(--text-muted)" />
                      <span>Traceability Identifiers</span>
                    </div>
                    <div className="iteration-detail-value">
                      <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Correlation ID:</div>
                      {iter.correlation_id ? (
                        <div className="iteration-mono-chip">
                          <span style={{ fontSize: '0.72rem' }}>{iter.correlation_id}</span>
                          <button
                            type="button"
                            className="iteration-copy-icon-btn"
                            title="Copy Correlation ID"
                            onClick={() => handleCopy(`corr-${iter.correlation_id}`, iter.correlation_id)}
                          >
                            {copiedKey === `corr-${iter.correlation_id}` ? (
                              <Check size={12} color="var(--status-passed)" />
                            ) : (
                              <Copy size={12} />
                            )}
                          </button>
                        </div>
                      ) : (
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>—</span>
                      )}

                      {iter.dispatch_attempt_id && (
                        <>
                          <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '2px' }}>Attempt ID:</div>
                          <div className="iteration-mono-chip">
                            <span style={{ fontSize: '0.72rem' }}>{iter.dispatch_attempt_id}</span>
                            <button
                              type="button"
                              className="iteration-copy-icon-btn"
                              title="Copy Attempt ID"
                              onClick={() => handleCopy(`disp-${iter.dispatch_attempt_id}`, iter.dispatch_attempt_id)}
                            >
                              {copiedKey === `disp-${iter.dispatch_attempt_id}` ? (
                                <Check size={12} color="var(--status-passed)" />
                              ) : (
                                <Copy size={12} />
                              )}
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {/* Findings & Notes Footer */}
                {(iter.payload || iter.notes) && (
                  <div className="iteration-card-footer">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                      {iter.payload?.affected_files?.length > 0 && (
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>Affected Files: </span>
                          <span className="text-mono" style={{ color: 'var(--text-primary)' }}>
                            {iter.payload.affected_files.join(', ')}
                          </span>
                        </div>
                      )}
                      {iter.payload?.failed_assertions?.length > 0 && (
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>Failed Assertions: </span>
                          <span style={{ color: 'var(--status-failed)', fontWeight: 600 }}>
                            {iter.payload.failed_assertions.length} statement(s)
                          </span>
                        </div>
                      )}
                      {iter.notes && (
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>Note: </span>
                          <span style={{ color: 'var(--text-secondary)' }}>"{iter.notes}"</span>
                        </div>
                      )}
                    </div>
                    {iter.payload?.schema_version && (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.6875rem', fontFamily: 'var(--font-mono)' }}>
                        Schema v{iter.payload.schema_version}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Re-Verification Boundary & Target Closed-Loop Workflow */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.25rem' }}>
        
        {/* Workflow Stages */}
        <Card title="Repair Feedback Workflow" subtitle="Structured feedback and re-verification cycle with automated repair services">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            
            <div style={{ padding: '0.65rem 0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <ArrowRightLeft size={14} color="var(--primary-400)" />
                <span>Step 1 — Defect Communication & Authorization</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                When verification fails, structured <code>DefectReport</code> entities and a sanitized <code>TechnicalFeedbackPayload</code> are generated. A human engineer explicitly authorizes dispatch.
              </p>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <GitPullRequest size={14} color="var(--accent-cyan)" />
                <span>Step 2 — Automated Code Repair</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                The repair service accepts the feedback package, creates an internal correction job, and generates a refined code implementation addressing the failed assertions and value comparisons.
              </p>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <Repeat size={14} color="var(--status-passed)" />
                <span>Step 3 — Ingestion & Re-Verification Boundary</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                The corrected implementation returns via the standard API <code>POST /api/v1/submissions</code>, triggering a fresh verification run.
              </p>
            </div>
          </div>
        </Card>

        {/* Audit Record Summary */}
        <Card title="Iteration Audit Record" subtitle="Auditable metadata preserved for each feedback cycle">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.625rem' }}>
            <div style={{ padding: '0.65rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.6875rem' }}>Iteration Tracking</div>
              <div style={{ color: 'var(--text-primary)', fontSize: '0.75rem', fontWeight: 500 }}>Sequential Iteration ID & Number</div>
            </div>
            <div style={{ padding: '0.65rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.6875rem' }}>Source References</div>
              <div style={{ color: 'var(--text-primary)', fontSize: '0.75rem', fontWeight: 500 }}>Run ID & Submission ID Linkage</div>
            </div>
            <div style={{ padding: '0.65rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.6875rem' }}>Governance Audit</div>
              <div style={{ color: 'var(--text-primary)', fontSize: '0.75rem', fontWeight: 500 }}>Approval Status & Reviewer Identity</div>
            </div>
            <div style={{ padding: '0.65rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.6875rem' }}>Dispatch Verification</div>
              <div style={{ color: 'var(--text-primary)', fontSize: '0.75rem', fontWeight: 500 }}>Correlation ID & Repair Job ID</div>
            </div>
          </div>

          <div style={{ marginTop: '0.875rem', padding: '0.625rem', backgroundColor: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Each feedback iteration preserves state idempotently, preventing duplicate dispatches while establishing full end-to-end traceability via correlation IDs.
          </div>
        </Card>
      </div>
    </div>
  );
}
