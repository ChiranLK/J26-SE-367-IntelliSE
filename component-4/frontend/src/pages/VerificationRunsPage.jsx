import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  PlayCircle,
  RefreshCw,
  Plus,
  Clock,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  Eye,
  Filter,
  Info,
  Check,
  Copy,
  Layers,
  Activity,
  ArrowRight,
  GitBranch,
  Terminal,
  FileCode,
  ShieldCheck,
  ExternalLink,
  Bug,
  ShieldAlert,
} from 'lucide-react';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';
import Modal from '../components/common/Modal';
import EmptyState from '../components/common/EmptyState';
import LoadingSkeleton from '../components/common/LoadingSkeleton';
import Pagination from '../components/common/Pagination';
import CodeViewer from '../components/common/CodeViewer';
import {
  getVerificationRuns,
  createVerificationRun,
  getVerificationRunById,
  getVerificationStatus,
  executeVerificationRun,
} from '../api/verificationApi';
import { getSubmissionById } from '../api/submissionApi';
import { formatDate, formatRelativeTime, truncateId } from '../utils/formatters';
import { VERIFICATION_STATUSES, TEST_TYPES, DEFECT_SEVERITIES } from '../utils/constants';


export default function VerificationRunsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Query parameter filters
  const submissionIdParam = searchParams.get('submission_id') || '';
  const createForParam = searchParams.get('create_for') || '';

  // Data states
  const [runs, setRuns] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const limit = 10;

  const [filterSubmissionId, setFilterSubmissionId] = useState(submissionIdParam);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  // Create verification run modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createSubmissionId, setCreateSubmissionId] = useState(createForParam || '');
  const [selectedTestTypes, setSelectedTestTypes] = useState(['unit', 'integration', 'performance']);
  const [triggeredBy, setTriggeredBy] = useState('manual');
  const [trustedTestCases, setTrustedTestCases] = useState('');
  const [executeImmediately, setExecuteImmediately] = useState(false);
  const [creating, setCreating] = useState(false);
  const [executingRun, setExecutingRun] = useState(false);
  const [createError, setCreateError] = useState(null);

  // Run detail modal state
  const [selectedRun, setSelectedRun] = useState(null);
  const [relatedSubmission, setRelatedSubmission] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [refreshingStatus, setRefreshingStatus] = useState(false);
  const [copiedId, setCopiedId] = useState(null);

  const fetchRuns = async (offset = skip, isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const data = await getVerificationRuns({
        submission_id: filterSubmissionId.trim() || undefined,
        skip: offset,
        limit,
      });
      setRuns(data.items || []);
      setTotal(data.total || 0);
      setSkip(offset);
    } catch (err) {
      setError(err.message || 'Failed to fetch verification runs.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchRuns(0);
  }, [filterSubmissionId]);

  useEffect(() => {
    if (createForParam) {
      setCreateSubmissionId(createForParam);
      setShowCreateModal(true);
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete('create_for');
      setSearchParams(nextParams, { replace: true });
    }
  }, [createForParam]);

  const handleCopy = async (id) => {
    try {
      await navigator.clipboard.writeText(id);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      setCopiedId(null);
    }
  };

  const handleTestTypeToggle = (typeId) => {
    setSelectedTestTypes((prev) => {
      if (prev.includes(typeId)) {
        if (prev.length === 1) return prev;
        return prev.filter((t) => t !== typeId);
      } else {
        return [...prev, typeId];
      }
    });
  };

  const handleExecutePipeline = async (runId, testCode = undefined) => {
    setExecutingRun(true);
    try {
      const updatedRun = await executeVerificationRun(runId, {
        trusted_test_cases: testCode || undefined,
      });
      setSelectedRun(updatedRun);
      setRuns((prev) => prev.map((r) => (r.id === runId ? updatedRun : r)));
    } catch (err) {
      setError(`Failed to execute verification pipeline: ${err.message}`);
    } finally {
      setExecutingRun(false);
    }
  };

  const handleCreateRun = async (e) => {
    e.preventDefault();
    if (!createSubmissionId.trim()) {
      setCreateError('Please provide a valid Submission ID.');
      return;
    }

    setCreating(true);
    setCreateError(null);

    try {
      const newRun = await createVerificationRun({
        submission_id: createSubmissionId.trim(),
        triggered_by: triggeredBy.trim() || 'manual',
        test_types: selectedTestTypes,
        trusted_test_cases: trustedTestCases.trim() || undefined,
      });

      let finalRun = newRun;
      if (executeImmediately) {
        finalRun = await executeVerificationRun(newRun.id, {
          trusted_test_cases: trustedTestCases.trim() || undefined,
        });
      }

      setShowCreateModal(false);
      setCreateSubmissionId('');
      setTrustedTestCases('');
      setExecuteImmediately(false);
      fetchRuns(0, true);
      handleViewDetails(finalRun.id);
    } catch (err) {
      setCreateError(err.message || 'Failed to initiate verification run.');
    } finally {
      setCreating(false);
    }
  };

  const handleViewDetails = async (runId) => {
    setLoadingDetails(true);
    setSelectedRun(null);
    setRelatedSubmission(null);

    try {
      const run = await getVerificationRunById(runId);
      setSelectedRun(run);

      try {
        const sub = await getSubmissionById(run.submission_id);
        setRelatedSubmission(sub);
      } catch {
        setRelatedSubmission(null);
      }
    } catch (err) {
      setError(`Failed to retrieve verification run details: ${err.message}`);
    } finally {
      setLoadingDetails(false);
    }
  };

  const handleRefreshSingleStatus = async (runId) => {
    setRefreshingStatus(true);
    try {
      const statusRes = await getVerificationStatus(runId);
      if (selectedRun && selectedRun.id === runId) {
        setSelectedRun((prev) => ({
          ...prev,
          status: statusRes.status,
          error_message: statusRes.error_message,
          updated_at: statusRes.updated_at,
        }));
      }
      setRuns((prev) =>
        prev.map((r) =>
          r.id === runId
            ? {
                ...r,
                status: statusRes.status,
                error_message: statusRes.error_message,
                updated_at: statusRes.updated_at,
              }
            : r
        )
      );
    } catch (err) {
      setError(`Failed to refresh status: ${err.message}`);
    } finally {
      setRefreshingStatus(false);
    }
  };

  const handleClearFilter = () => {
    setFilterSubmissionId('');
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('submission_id');
    setSearchParams(nextParams);
  };

  const filteredRuns = runs.filter((r) => {
    if (statusFilter === 'ALL') return true;
    return r.status === statusFilter;
  });

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">
              <PlayCircle size={22} color="var(--primary-400)" />
              <span>Verification Pipelines</span>
            </h1>
            <p className="page-description">
              Autonomous testing agent runs, test suite orchestration, and execution telemetry.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              loading={refreshing}
              onClick={() => fetchRuns(skip, true)}
            >
              Refresh Telemetry
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={Plus}
              onClick={() => {
                setCreateError(null);
                setShowCreateModal(true);
              }}
            >
              Initiate Run
            </Button>
          </div>
        </div>
      </div>

      {/* CI/CD Pipeline Lifecycle Banner */}
      <div
        style={{
          padding: '0.75rem 1rem',
          borderRadius: 'var(--radius-sm)',
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
          marginBottom: '1.25rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.75rem',
          fontSize: '0.8125rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Activity size={15} color="var(--status-running)" />
          <span style={{ color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--text-primary)' }}>Pipeline Lifecycle Contract:</strong> Runs initialize in{' '}
            <code style={{ color: 'var(--status-pending)', fontFamily: 'var(--font-mono)' }}>PENDING</code>.
            Autonomous testing agents execute in Phase 2B.
          </span>
        </div>

        {/* Visual pipeline sequence tags */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.6875rem' }}>
          <span style={{ padding: '1px 6px', background: 'var(--bg-tertiary)', borderRadius: '3px', color: 'var(--text-muted)' }}>
            1. INGEST
          </span>
          <ArrowRight size={10} color="var(--text-tertiary)" />
          <span style={{ padding: '1px 6px', background: 'var(--status-pending-bg)', border: '1px solid var(--status-pending-border)', borderRadius: '3px', color: 'var(--status-pending)', fontWeight: 600 }}>
            2. PENDING
          </span>
          <ArrowRight size={10} color="var(--text-tertiary)" />
          <span style={{ padding: '1px 6px', background: 'var(--bg-tertiary)', borderRadius: '3px', color: 'var(--text-muted)' }}>
            3. RUNNING
          </span>
          <ArrowRight size={10} color="var(--text-tertiary)" />
          <span style={{ padding: '1px 6px', background: 'var(--bg-tertiary)', borderRadius: '3px', color: 'var(--text-muted)' }}>
            4. OUTCOME
          </span>
        </div>
      </div>

      {error && (
        <Alert type="danger" title="Pipeline Error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Main Table Card */}
      <Card>
        {/* Filter bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.75rem',
            marginBottom: '1rem',
            flexWrap: 'wrap',
          }}
        >
          {/* Status filter tabs */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', backgroundColor: 'var(--bg-input)', padding: '2px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
            {['ALL', 'PENDING', 'RUNNING', 'PASSED', 'FAILED'].map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setStatusFilter(st)}
                style={{
                  background: statusFilter === st ? 'var(--bg-tertiary)' : 'transparent',
                  color: statusFilter === st ? 'var(--text-primary)' : 'var(--text-muted)',
                  border: 'none',
                  padding: '3px 8px',
                  borderRadius: '3px',
                  fontSize: '0.6875rem',
                  fontWeight: 500,
                  cursor: 'pointer',
                  letterSpacing: '0.04em',
                  transition: 'all 0.12s ease',
                }}
              >
                {st}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, justifyContent: 'flex-end', minWidth: '240px' }}>
            <div style={{ position: 'relative', width: '260px' }}>
              <Filter
                size={13}
                style={{
                  position: 'absolute',
                  left: '0.65rem',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)',
                }}
              />
              <input
                type="text"
                placeholder="Filter by Submission ID..."
                className="form-input"
                style={{ paddingLeft: '1.85rem', fontSize: '0.75rem', padding: '0.35rem 0.5rem 0.35rem 1.85rem' }}
                value={filterSubmissionId}
                onChange={(e) => setFilterSubmissionId(e.target.value)}
              />
            </div>
            {filterSubmissionId && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearFilter}
              >
                Clear
              </Button>
            )}
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Total: {total}
            </span>
          </div>
        </div>

        {/* Pipeline Runs Table */}
        {loading ? (
          <LoadingSkeleton type="table" rows={6} cols={6} />
        ) : filteredRuns.length === 0 ? (
          <EmptyState
            icon={PlayCircle}
            title={filterSubmissionId ? 'No matching pipeline runs' : 'No verification pipelines recorded'}
            description={
              filterSubmissionId
                ? `No verification records exist for submission ID "${filterSubmissionId}".`
                : 'Initiate a verification run on a code submission to begin testing.'
            }
            action={
              <Button
                size="sm"
                variant="primary"
                onClick={() => {
                  setCreateError(null);
                  setShowCreateModal(true);
                }}
                icon={Plus}
              >
                Initiate Run
              </Button>
            }
          />
        ) : (
          <>
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>Target Submission</th>
                    <th>Status</th>
                    <th>Requested Suites</th>
                    <th>Trigger Source</th>
                    <th>Created</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRuns.map((run) => {
                    const statusMeta = VERIFICATION_STATUSES[run.status] || {
                      label: run.status,
                      variant: 'secondary',
                    };

                    return (
                      <tr key={run.id}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <span className="text-mono" style={{ color: 'var(--primary-300)', fontWeight: 500 }}>
                              {truncateId(run.id, 14)}
                            </span>
                            <button
                              type="button"
                              className="btn-copy-id"
                              onClick={() => handleCopy(run.id)}
                              title="Copy Run ID"
                            >
                              {copiedId === run.id ? (
                                <Check size={12} color="var(--status-passed)" />
                              ) : (
                                <Copy size={12} />
                              )}
                            </button>
                          </div>
                        </td>
                        <td>
                          <span className="text-mono" style={{ color: 'var(--text-secondary)' }}>
                            {truncateId(run.submission_id, 12)}
                          </span>
                        </td>
                        <td>
                          <Badge variant={statusMeta.variant} dot>
                            {statusMeta.label}
                          </Badge>
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                            {run.requested_test_types.map((tt) => (
                              <Badge key={tt} variant="secondary" style={{ fontSize: '0.65rem' }}>
                                {tt}
                              </Badge>
                            ))}
                          </div>
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                          {run.triggered_by}
                        </td>
                        <td title={formatDate(run.created_at)} style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                          {formatRelativeTime(run.created_at)}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: '0.35rem' }}>
                            <Button
                              variant="outline"
                              size="sm"
                              className="btn-table-action"
                              icon={RefreshCw}
                              iconOnly
                              onClick={() => handleRefreshSingleStatus(run.id)}
                              title="Poll real status from backend"
                            />
                            <Button
                              variant="outline"
                              size="sm"
                              className="btn-table-action"
                              icon={Eye}
                              onClick={() => handleViewDetails(run.id)}
                            >
                              Details
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <Pagination
              total={total}
              skip={skip}
              limit={limit}
              onPageChange={(newSkip) => fetchRuns(newSkip)}
            />
          </>
        )}
      </Card>

      {/* Initiate Verification Run Modal */}
      {showCreateModal && (
        <Modal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          title="Initiate Verification Pipeline"
          footer={
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowCreateModal(false)}
                disabled={creating}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleCreateRun}
                loading={creating}
                icon={PlayCircle}
              >
                Launch Pipeline
              </Button>
            </>
          }
        >
          {createError && (
            <Alert type="danger" title="Validation Alert" onClose={() => setCreateError(null)}>
              {createError}
            </Alert>
          )}

          <form onSubmit={handleCreateRun}>
            <div className="form-group">
              <label htmlFor="submission-id-input" className="form-label">
                <span>Target Submission ID *</span>
              </label>
              <input
                id="submission-id-input"
                type="text"
                className="form-input text-mono"
                placeholder="sub-..."
                value={createSubmissionId}
                onChange={(e) => setCreateSubmissionId(e.target.value)}
                required
              />
              <span className="form-hint">
                The identifier of the ingested code artifact to verify.
              </span>
            </div>

            <div className="form-group">
              <label htmlFor="triggered-by-input" className="form-label">
                <span>Trigger Origin</span>
              </label>
              <input
                id="triggered-by-input"
                type="text"
                className="form-input"
                placeholder="e.g. manual, pipeline, component_3"
                value={triggeredBy}
                onChange={(e) => setTriggeredBy(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">
                <span>Requested Test Suites</span>
                <span className="form-hint">Select suites to orchestrate</span>
              </label>
              <div className="checkbox-group">
                {TEST_TYPES.map((tt) => (
                  <label key={tt.id} className="checkbox-label" style={{ padding: '0.4rem', borderRadius: '4px', background: 'var(--bg-input)', border: '1px solid var(--border-color)' }}>
                    <input
                      type="checkbox"
                      checked={selectedTestTypes.includes(tt.id)}
                      onChange={() => handleTestTypeToggle(tt.id)}
                    />
                    <div>
                      <div style={{ fontWeight: 500, fontSize: '0.8125rem' }}>{tt.label}</div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        {tt.description}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="trusted-tests-input" className="form-label">
                <span>Authorized Test Cases (Optional pytest suite)</span>
                <span className="form-hint">Explicit test oracle for Python execution</span>
              </label>
              <textarea
                id="trusted-tests-input"
                className="form-input text-mono"
                rows={4}
                placeholder="from solution import add&#10;&#10;def test_add():&#10;    assert add(2, 3) == 5"
                value={trustedTestCases}
                onChange={(e) => setTrustedTestCases(e.target.value)}
                style={{ fontFamily: 'monospace', fontSize: '0.8125rem' }}
              />
              <span className="form-hint">
                Phase 2B requirement: Only explicitly authorized test specifications determine correctness.
              </span>
            </div>

            <div className="form-group">
              <label className="checkbox-label" style={{ padding: '0.4rem', borderRadius: '4px', background: 'var(--bg-input)', border: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  checked={executeImmediately}
                  onChange={(e) => setExecuteImmediately(e.target.checked)}
                />
                <div>
                  <div style={{ fontWeight: 500, fontSize: '0.8125rem' }}>Execute in Docker Sandbox Immediately</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    Runs pytest inside an isolated, unprivileged container upon registration
                  </div>
                </div>
              </label>
            </div>

            <div
              style={{
                padding: '0.625rem 0.75rem',
                backgroundColor: 'rgba(245, 158, 11, 0.05)',
                border: '1px solid rgba(245, 158, 11, 0.18)',
                borderRadius: 'var(--radius-xs)',
                fontSize: '0.75rem',
                color: 'var(--text-secondary)',
                marginTop: '0.75rem',
              }}
            >
              <strong style={{ color: 'var(--text-primary)' }}>Sandbox Security:</strong> Python code executes inside an unprivileged Docker container with zero network access, read-only rootfs, and resource boundaries.
            </div>
          </form>
        </Modal>
      )}

      {/* Verification Run Full Details Modal */}
      {selectedRun && (
        <Modal
          isOpen={!!selectedRun}
          onClose={() => setSelectedRun(null)}
          title={`Pipeline Details: ${selectedRun.id}`}
          size="lg"
          footer={
            <>
              {selectedRun.status === 'PENDING' && (
                <Button
                  variant="primary"
                  size="sm"
                  icon={PlayCircle}
                  loading={executingRun}
                  onClick={() => handleExecutePipeline(selectedRun.id)}
                >
                  Execute in Sandbox
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                icon={RefreshCw}
                loading={refreshingStatus}
                onClick={() => handleRefreshSingleStatus(selectedRun.id)}
              >
                Poll Status
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setSelectedRun(null)}>
                Close
              </Button>
            </>
          }
        >
          {/* Metadata bar */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem', marginBottom: '1rem', fontSize: '0.8125rem' }}>
            <div>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Pipeline Status</span>
              <div>
                <Badge variant={VERIFICATION_STATUSES[selectedRun.status]?.variant || 'secondary'} dot>
                  {VERIFICATION_STATUSES[selectedRun.status]?.label || selectedRun.status}
                </Badge>
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Target Submission</span>
              <div className="text-mono" style={{ fontSize: '0.8125rem', color: 'var(--primary-300)', fontWeight: 500 }}>
                {selectedRun.submission_id}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Trigger Origin</span>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-primary)' }}>{selectedRun.triggered_by}</div>
            </div>
            <div>
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Registered At</span>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                {formatDate(selectedRun.created_at)}
              </div>
            </div>
          </div>

          {/* Requested Test Suites */}
          <div style={{ marginBottom: '1rem' }}>
            <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.3rem' }}>
              Requested Test Suites
            </span>
            <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
              {selectedRun.requested_test_types.map((tt) => (
                <Badge key={tt} variant="secondary">
                  {tt}
                </Badge>
              ))}
            </div>
          </div>

          {/* CI/CD Agent Pipeline Telemetry Box */}
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Autonomous Agent Sandbox Telemetry
              </span>
              {selectedRun.execution_telemetry?.duration_ms && (
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Total Duration: {selectedRun.execution_telemetry.duration_ms.toFixed(1)}ms
                </span>
              )}
            </div>

            {selectedRun.error_message && (
              <div style={{ marginBottom: '0.75rem' }}>
                <Alert type="danger" title="Pipeline Diagnostics">
                  {selectedRun.error_message}
                </Alert>
              </div>
            )}

            {selectedRun.execution_telemetry?.no_oracle && (
              <div
                style={{
                  padding: '0.75rem',
                  backgroundColor: 'rgba(245, 158, 11, 0.08)',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                  borderRadius: 'var(--radius-xs)',
                  fontSize: '0.75rem',
                  color: 'var(--text-secondary)',
                  marginBottom: '0.75rem',
                }}
              >
                <strong style={{ color: 'var(--status-pending)' }}>No Test Oracle Supplied:</strong> Safe AST syntax validation passed, but functional correctness cannot be verified without authorized test specifications.
              </div>
            )}

            {selectedRun.test_results && selectedRun.test_results.length > 0 ? (
              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Test Name</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Duration</th>
                      <th>Diagnostics</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedRun.test_results.map((tr, idx) => (
                      <tr key={idx}>
                        <td>
                          <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                            {tr.test_name || tr.name}
                          </span>
                        </td>
                        <td>
                          <Badge variant="secondary">{tr.test_type}</Badge>
                        </td>
                        <td>
                          <Badge
                            variant={
                              tr.status === 'PASSED'
                                ? 'success'
                                : tr.status === 'FAILED'
                                ? 'danger'
                                : 'warning'
                            }
                            dot
                          >
                            {tr.status}
                          </Badge>
                        </td>
                        <td>
                          {tr.duration_ms !== null && tr.duration_ms !== undefined
                            ? `${tr.duration_ms.toFixed(1)}ms`
                            : '—'}
                        </td>
                        <td style={{ maxWidth: '240px' }}>
                          {tr.error_message ? (
                            <span
                              style={{
                                color: 'var(--status-failed)',
                                fontSize: '0.75rem',
                                wordBreak: 'break-word',
                              }}
                              title={tr.error_message}
                            >
                              {tr.error_message}
                            </span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                              None
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div
                style={{
                  padding: '0.875rem 1rem',
                  backgroundColor: 'var(--bg-tertiary)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.8125rem',
                  color: 'var(--text-secondary)',
                }}
              >
                <div style={{ fontWeight: 500, color: 'var(--text-primary)', marginBottom: '0.2rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Clock size={14} color="var(--status-pending)" />
                  <span>Awaiting Sandbox Pipeline Execution</span>
                </div>
                Verification run is registered in <code style={{ color: 'var(--status-pending)' }}>PENDING</code> state. Click <strong>Execute in Sandbox</strong> to dispatch the LangGraph Docker test runner.
              </div>
            )}
          </div>

          {/* Evidence-Based Defect Reports Section */}
          <div style={{ marginBottom: '1.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Bug size={16} color="var(--primary-400)" />
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Evidence-Based Defect Analysis
                </span>
                {selectedRun.defect_reports && selectedRun.defect_reports.length > 0 && (
                  <Badge variant="danger" dot style={{ fontSize: '0.65rem' }}>
                    {selectedRun.defect_reports.length} {selectedRun.defect_reports.length === 1 ? 'Defect' : 'Defects'}
                  </Badge>
                )}
              </div>
            </div>

            {/* Zero Defects Detected for PASSED runs */}
            {selectedRun.status === 'PASSED' && (
              <div
                style={{
                  padding: '0.75rem 1rem',
                  backgroundColor: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  borderRadius: 'var(--radius-sm)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.6rem',
                  fontSize: '0.8125rem',
                  color: 'var(--text-secondary)',
                }}
              >
                <CheckCircle2 size={18} color="var(--status-passed)" style={{ flexShrink: 0 }} />
                <div>
                  <strong style={{ color: 'var(--status-passed)' }}>Zero Defects Detected:</strong> All test assertions passed within the isolated Docker sandbox. No runtime exceptions or assertion failures observed.
                </div>
              </div>
            )}

            {/* Defect Reports Cards for FAILED runs with defects */}
            {selectedRun.defect_reports && selectedRun.defect_reports.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                {selectedRun.defect_reports.map((defect, dIdx) => (
                  <div
                    key={defect.defect_id || dIdx}
                    style={{
                      padding: '0.75rem 0.875rem',
                      backgroundColor: 'var(--bg-input)',
                      border: '1px solid rgba(239, 68, 68, 0.25)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.8125rem',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem', flexWrap: 'wrap', gap: '0.35rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <Badge variant="danger" style={{ fontSize: '0.6875rem', fontWeight: 600 }}>
                          {defect.failure_category || 'ASSERTION_FAILURE'}
                        </Badge>
                        <span className="text-mono" style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.75rem' }}>
                          {defect.failed_test || defect.title}
                        </span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Severity:</span>
                        <Badge
                          variant={DEFECT_SEVERITIES[defect.severity]?.variant || 'danger'}
                          dot
                          style={{ fontSize: '0.6875rem' }}
                        >
                          {DEFECT_SEVERITIES[defect.severity]?.label || defect.severity}
                        </Badge>
                      </div>
                    </div>

                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.35rem', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                      <div>
                        <span style={{ color: 'var(--text-muted)' }}>Affected File: </span>
                        <code style={{ color: 'var(--primary-300)' }}>
                          {defect.file_path || 'solution.py'}{defect.line_number ? `:${defect.line_number}` : ''}
                        </code>
                      </div>
                      <div>
                        <span style={{ color: 'var(--text-muted)' }}>Defect ID: </span>
                        <code style={{ color: 'var(--text-secondary)' }}>{defect.defect_id}</code>
                      </div>
                    </div>

                    {/* Expected vs Actual Diffs if extractable */}
                    {(defect.expected_value || defect.actual_value) && (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', margin: '0.5rem 0' }}>
                        <div
                          style={{
                            padding: '0.4rem 0.6rem',
                            backgroundColor: 'rgba(16, 185, 129, 0.08)',
                            border: '1px solid rgba(16, 185, 129, 0.25)',
                            borderRadius: 'var(--radius-xs)',
                          }}
                        >
                          <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--status-passed)', fontWeight: 600, display: 'block' }}>
                            Expected Value
                          </span>
                          <span className="text-mono" style={{ fontSize: '0.75rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                            {defect.expected_value || '—'}
                          </span>
                        </div>
                        <div
                          style={{
                            padding: '0.4rem 0.6rem',
                            backgroundColor: 'rgba(239, 68, 68, 0.08)',
                            border: '1px solid rgba(239, 68, 68, 0.25)',
                            borderRadius: 'var(--radius-xs)',
                          }}
                        >
                          <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--status-failed)', fontWeight: 600, display: 'block' }}>
                            Actual / Observed Value
                          </span>
                          <span className="text-mono" style={{ fontSize: '0.75rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                            {defect.actual_value || '—'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Diagnostic details */}
                    {defect.assertion_or_exception && (
                      <div
                        style={{
                          marginTop: '0.35rem',
                          padding: '0.4rem 0.6rem',
                          backgroundColor: 'var(--bg-tertiary)',
                          borderRadius: 'var(--radius-xs)',
                          border: '1px solid var(--border-color)',
                          fontSize: '0.75rem',
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--status-failed)',
                          wordBreak: 'break-word',
                        }}
                      >
                        {defect.assertion_or_exception}
                      </div>
                    )}

                    {/* Traceback Excerpt */}
                    {defect.traceback_excerpt && (
                      <details style={{ marginTop: '0.4rem' }}>
                        <summary style={{ fontSize: '0.7rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
                          View Traceback Excerpt
                        </summary>
                        <pre
                          style={{
                            margin: '0.25rem 0 0',
                            padding: '0.5rem',
                            background: '#07090e',
                            borderRadius: 'var(--radius-xs)',
                            border: '1px solid var(--border-color)',
                            fontSize: '0.7rem',
                            fontFamily: 'var(--font-mono)',
                            color: 'var(--text-secondary)',
                            overflowX: 'auto',
                            maxHeight: '160px',
                            whiteSpace: 'pre-wrap',
                          }}
                        >
                          {defect.traceback_excerpt}
                        </pre>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Awaiting or FAILED without defect reports */}
            {selectedRun.status === 'PENDING' && (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                Defect reports will be synthesized dynamically if test execution detects failures.
              </div>
            )}
          </div>

          {/* Target Code Snippet */}
          {relatedSubmission && (

            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Associated Code ({relatedSubmission.language}):
                </span>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  {relatedSubmission.filename || 'Snippet'}
                </span>
              </div>
              <CodeViewer
                code={relatedSubmission.code}
                language={relatedSubmission.language}
                filename={relatedSubmission.filename}
                maxHeight="220px"
              />
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
