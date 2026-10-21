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
  Bug,
  ShieldAlert,
  FileJson,
  BrainCircuit,
  Send,
  Lock,
  CheckCircle,
  XCircle,
  Wrench,
  RotateCcw,
  GitCompare,
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
import ProjectFileTree from '../components/common/ProjectFileTree';
import ExpandableDiagnostic from '../components/common/ExpandableDiagnostic';
import {
  getVerificationRuns,
  createVerificationRun,
  getVerificationRunById,
  getVerificationStatus,
  executeVerificationRun,
  getFeedbackPreview,
  getXaiExplanation,
  getComponent3Status,
  approveFeedback,
  dispatchFeedback,
  ingestRepairResponse,
  reverifyRepair,
  getRepairAttempts,
  getConvergenceRiskReport,
  getDeploymentReadinessReport,
  getAiEngineStatus,
} from '../api/verificationApi';
import { getSubmissionById } from '../api/submissionApi';
import { formatDate, formatRelativeTime, truncateId } from '../utils/formatters';
import { VERIFICATION_STATUSES, TEST_TYPES, DEFECT_SEVERITIES } from '../utils/constants';

const TEST_GROUP_LABELS = {
  unit: 'Unit Testing',
  integration: 'Integration Testing',
  performance: 'Performance Testing',
};



export default function VerificationRunsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Query parameter filters
  const submissionIdParam = searchParams.get('submission_id') || '';
  const createForParam = searchParams.get('create_for') || '';
  const runIdParam = searchParams.get('run_id') || '';

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
  const [activeProjectFile, setActiveProjectFile] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [refreshingStatus, setRefreshingStatus] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [feedbackPreview, setFeedbackPreview] = useState(null);
  const [loadingFeedback, setLoadingFeedback] = useState(false);
  const [copiedFeedbackJson, setCopiedFeedbackJson] = useState(false);
  const [xaiExplanation, setXaiExplanation] = useState(null);
  const [loadingXai, setLoadingXai] = useState(false);
  const [c3Status, setC3Status] = useState(null);
  const [approvingFeedback, setApprovingFeedback] = useState(false);
  const [dispatchingFeedback, setDispatchingFeedback] = useState(false);
  const [dispatchMessage, setDispatchMessage] = useState(null);

  // Repair Ingestion & Re-Verification States
  const [repairAttempts, setRepairAttempts] = useState([]);
  const [loadingRepairs, setLoadingRepairs] = useState(false);
  const [showIngestRepair, setShowIngestRepair] = useState(false);
  const [correctedCode, setCorrectedCode] = useState('');
  const [correctedFilename, setCorrectedFilename] = useState('solution.py');
  const [repairSource, setRepairSource] = useState('LOCAL_MANUAL');
  const [repairNotes, setRepairNotes] = useState('');
  const [ingestingRepair, setIngestingRepair] = useState(false);
  const [reverifyingRepairId, setReverifyingRepairId] = useState(null);
  const [repairError, setRepairError] = useState(null);
  const [repairWarningMessage, setRepairWarningMessage] = useState(null);
  const [repairSuccessMessage, setRepairSuccessMessage] = useState(null);
  const [forceConfirmRepair, setForceConfirmRepair] = useState(null);

  // Verification Governance & Deployment Readiness States
  const [convergenceReport, setConvergenceReport] = useState(null);
  const [loadingConvergence, setLoadingConvergence] = useState(false);
  const [showConvergenceModal, setShowConvergenceModal] = useState(false);
  const [readinessReport, setReadinessReport] = useState(null);
  const [loadingReadiness, setLoadingReadiness] = useState(false);
  const [showReadinessModal, setShowReadinessModal] = useState(false);
  const [aiEngineStatus, setAiEngineStatus] = useState(null);


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

  useEffect(() => {
    if (!runIdParam) return;
    handleViewDetails(runIdParam);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('run_id');
    setSearchParams(nextParams, { replace: true });
  }, [runIdParam]);

  useEffect(() => {
    getAiEngineStatus()
      .then((st) => setAiEngineStatus(st))
      .catch(() => setAiEngineStatus(null));
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

      // Fetch technical feedback preview and XAI explanation for the executed run
      try {
        const preview = await getFeedbackPreview(runId);
        setFeedbackPreview(preview);
      } catch {
        setFeedbackPreview(null);
      }

      try {
        const xai = await getXaiExplanation(runId);
        setXaiExplanation(xai);
      } catch {
        setXaiExplanation(null);
      }
    } catch (err) {
      setError(`Failed to execute verification pipeline: ${err.message}`);
    } finally {
      setExecutingRun(false);
    }
  };

  const handleCopyFeedbackJson = async () => {
    if (!feedbackPreview?.feedback) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(feedbackPreview.feedback, null, 2));
      setCopiedFeedbackJson(true);
      setTimeout(() => setCopiedFeedbackJson(false), 2000);
    } catch {
      setCopiedFeedbackJson(false);
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
    setFeedbackPreview(null);
    setXaiExplanation(null);
    setRepairAttempts([]);
    setShowIngestRepair(false);
    setCorrectedCode('');
    setRepairError(null);
    setRepairSuccessMessage(null);
    setForceConfirmRepair(null);
    setConvergenceReport(null);
    setReadinessReport(null);
    setActiveProjectFile(null);

    try {
      const run = await getVerificationRunById(runId);
      setSelectedRun(run);

      try {
        const sub = await getSubmissionById(run.submission_id);
        setRelatedSubmission(sub);
        if (sub?.metadata?.is_multi_file) {
          const firstDefectiveFile = run.defect_reports?.find((d) => d.file_path)?.file_path;
          const initialFile =
            firstDefectiveFile ||
            sub.metadata?.entrypoint ||
            Object.keys(sub.metadata?.project_files || {})[0] ||
            'solution.py';
          setActiveProjectFile(initialFile);
          setCorrectedFilename(initialFile);
        } else if (sub?.filename) {
          setCorrectedFilename(sub.filename);
        }
      } catch {
        setRelatedSubmission(null);
      }

      setLoadingFeedback(true);
      setLoadingXai(true);
      try {
        const preview = await getFeedbackPreview(run.id);
        setFeedbackPreview(preview);
      } catch {
        setFeedbackPreview(null);
      } finally {
        setLoadingFeedback(false);
      }

      try {
        const xai = await getXaiExplanation(run.id);
        setXaiExplanation(xai);
      } catch {
        setXaiExplanation(null);
      } finally {
        setLoadingXai(false);
      }

      // Fetch repair integration status
      try {
        const c3 = await getComponent3Status();
        setC3Status(c3);
      } catch {
        setC3Status(null);
      }

      // Fetch repair attempts
      setLoadingRepairs(true);
      try {
        const repairRes = await getRepairAttempts(run.id);
        setRepairAttempts(repairRes?.items || []);
      } catch {
        setRepairAttempts([]);
      } finally {
        setLoadingRepairs(false);
      }

      // Fetch Governance Reports (Convergence Risk & Deployment Readiness)
      setLoadingConvergence(true);
      setLoadingReadiness(true);
      try {
        const conv = await getConvergenceRiskReport(run.id);
        setConvergenceReport(conv);
      } catch {
        setConvergenceReport(null);
      } finally {
        setLoadingConvergence(false);
      }

      try {
        const ready = await getDeploymentReadinessReport(run.id);
        setReadinessReport(ready);
      } catch {
        setReadinessReport(null);
      } finally {
        setLoadingReadiness(false);
      }
    } catch (err) {
      setError(`Failed to retrieve verification run details: ${err.message}`);
    } finally {
      setLoadingDetails(false);
    }
  };

  const handleIngestRepair = async (runId) => {
    if (!correctedCode.trim()) {
      setRepairError('Please provide non-empty Python source code for the repair.');
      return;
    }
    setIngestingRepair(true);
    setRepairError(null);
    setRepairSuccessMessage(null);
    try {
      const payload = {
        corrected_code: correctedCode,
        filename: correctedFilename.trim() || 'solution.py',
        repair_source: repairSource,
        notes: repairNotes.trim() || undefined,
      };
      await ingestRepairResponse(runId, payload);
      setRepairSuccessMessage('Corrected source code ingested successfully. You can now re-verify this implementation.');
      setShowIngestRepair(false);
      setCorrectedCode('');
      setRepairNotes('');
      // Refresh repair list
      const updatedList = await getRepairAttempts(runId);
      setRepairAttempts(updatedList.items || []);
    } catch (err) {
      setRepairError(err.message || 'Failed to ingest corrected code.');
    } finally {
      setIngestingRepair(false);
    }
  };

  const handleReverifyRepair = async (runId, repairId, force = false) => {
    setReverifyingRepairId(repairId);
    setRepairError(null);
    setRepairWarningMessage(null);
    setRepairSuccessMessage(null);
    try {
      const result = await reverifyRepair(runId, repairId, { force_reverify: force });
      const isBlocked =
        result.status === 'BLOCKED' ||
        result.is_inconsistent ||
        (!result.corrected_run_id && result.comparison?.verdict === 'INCONCLUSIVE');

      if (isBlocked) {
        setRepairWarningMessage(
          result.notes || 'Re-verification is blocked: original trusted test suite is unavailable to safely verify this repair.'
        );
      } else if (result.status === 'FAILED') {
        setRepairError(result.notes || 'Re-verification execution failed.');
      } else {
        setRepairSuccessMessage('Re-verification completed. Resolution comparison updated below.');
      }

      const [updatedList, updatedRun] = await Promise.all([
        getRepairAttempts(runId),
        getVerificationRunById(runId),
      ]);
      setRepairAttempts(updatedList.items || []);
      setSelectedRun(updatedRun);
      setRuns((prev) => prev.map((r) => (r.id === runId ? updatedRun : r)));
    } catch (err) {
      setRepairError(err.message || 'Failed to execute re-verification.');
    } finally {
      setReverifyingRepairId(null);
    }
  };

  const handleConfirmForceReverify = async () => {
    if (!forceConfirmRepair || reverifyingRepairId) return;
    const repairId = forceConfirmRepair.repair_id || forceConfirmRepair.id;
    try {
      await handleReverifyRepair(selectedRun.id, repairId, true);
    } finally {
      setForceConfirmRepair(null);
    }
  };

  const handleApproveFeedback = async (runId) => {
    setApprovingFeedback(true);
    setDispatchMessage(null);
    try {
      const iteration = await approveFeedback(runId, {
        approver: 'human_engineer',
        notes: 'Approved via Verification Explorer for Component 3 technical feedback', // ui-copy-ignore: required integration terminology
      });
      // Refresh run to show updated iterations
      const updatedRun = await getVerificationRunById(runId);
      setSelectedRun(updatedRun);
      setRuns((prev) => prev.map((r) => (r.id === runId ? updatedRun : r)));
      setDispatchMessage({
        type: 'success',
        text: `Feedback iteration #${iteration.iteration_number} successfully approved by human reviewer. Ready for dispatch when Component 3 integration is available.`, // ui-copy-ignore: required integration terminology
      });
    } catch (err) {
      setDispatchMessage({
        type: 'error',
        text: `Approval failed: ${err.message || 'Unknown error'}`,
      });
    } finally {
      setApprovingFeedback(false);
    }
  };

  const handleDispatchFeedback = async (runId) => {
    setDispatchingFeedback(true);
    setDispatchMessage(null);
    try {
      const res = await dispatchFeedback(runId, {
        approved: true,
        approver: 'human_engineer',
      });
      const updatedRun = await getVerificationRunById(runId);
      setSelectedRun(updatedRun);
      setRuns((prev) => prev.map((r) => (r.id === runId ? updatedRun : r)));

      if (res.delivery_status === 'ACKNOWLEDGED') {
        setDispatchMessage({
          type: 'success',
          text: `Technical feedback acknowledged by Component 3. Job ID: ${res.component_3_job_id || 'N/A'}. Correlation ID: ${res.correlation_id}`, // ui-copy-ignore: required integration terminology
        });
      } else if (res.delivery_status === 'NOT_DISPATCHED') {
        setDispatchMessage({
          type: 'info',
          text: `Safe fail-closed: ${res.message} (Delivery Status: NOT_DISPATCHED, Category: ${res.error_category})`,
        });
      } else if (res.delivery_status === 'UNKNOWN') {
        setDispatchMessage({
          type: 'warning',
          text: `Delivery outcome unknown: ${res.message} [Category: ${res.error_category || 'TIMEOUT'}]. Automatic retry suppressed.`,
        });
      } else {
        setDispatchMessage({
          type: 'warning',
          text: `Dispatch outcome: ${res.message} [Category: ${res.error_category || 'FAILED'}]`,
        });
      }
    } catch (err) {
      setDispatchMessage({
        type: 'error',
        text: `Dispatch request failed: ${err.message || 'Unknown error'}`,
      });
    } finally {
      setDispatchingFeedback(false);
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

  const renderSourceCodeViewer = () => {
    if (!relatedSubmission) return null;

    const projectFiles = relatedSubmission.metadata?.project_files;
    const isMultiFile = Boolean(relatedSubmission.metadata?.is_multi_file && projectFiles);
    const selectedFile = activeProjectFile || relatedSubmission.metadata?.entrypoint;

    return (
      <section className="verification-detail-section source-code-section" aria-labelledby="source-code-heading">
        <div className="verification-section-heading">
          <div>
            <span className="verification-section-kicker">Section 4</span>
            <h4 id="source-code-heading">Source Code Viewer</h4>
          </div>
          <span className="source-code-context">
            {isMultiFile
              ? `${Object.keys(projectFiles).length} files · Viewing: ${selectedFile || 'No file selected'}`
              : (relatedSubmission.filename || 'Source snippet')}
          </span>
        </div>

        {isMultiFile ? (
          <div className="project-source-layout">
            <div className="project-source-tree">
              <ProjectFileTree
                files={projectFiles}
                selectedFile={selectedFile}
                onSelectFile={(filePath) => {
                  setActiveProjectFile(filePath);
                  setCorrectedFilename(filePath);
                  if (showIngestRepair) setCorrectedCode(projectFiles[filePath] || '');
                }}
                defects={selectedRun?.defect_reports || []}
                entrypoint={relatedSubmission.metadata.entrypoint}
              />
            </div>
            <div className="project-source-code">
              <CodeViewer
                code={projectFiles[selectedFile] || relatedSubmission.code}
                language={relatedSubmission.language || 'python'}
                filename={selectedFile}
                maxHeight="340px"
              />
            </div>
          </div>
        ) : (
          <CodeViewer
            code={relatedSubmission.code}
            language={relatedSubmission.language}
            filename={relatedSubmission.filename}
            maxHeight="300px"
          />
        )}
      </section>
    );
  };

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
            <strong style={{ color: 'var(--text-primary)' }}>Pipeline Lifecycle:</strong> Runs initialize in{' '}
            <code style={{ color: 'var(--status-pending)', fontFamily: 'var(--font-mono)' }}>PENDING</code> and execute in an isolated test environment.
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
            {['ALL', 'PENDING', 'RUNNING', 'PASSED', 'FAILED', 'BLOCKED', 'ERROR'].map((st) => (
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
                            {(run.requested_test_types || []).map((tt) => (
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
                Verification Standard: Only explicitly authorized test specifications determine correctness.
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
          className="verification-details-modal"
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
          <section className="verification-detail-section" aria-labelledby="verification-overview-heading">
            <div className="verification-section-heading">
              <div>
                <span className="verification-section-kicker">Section 1</span>
                <h4 id="verification-overview-heading">Verification Overview</h4>
              </div>
            </div>
            <div className="verification-overview-grid">
              <div className="verification-overview-item">
                <span>Submission ID</span>
                <strong className="text-mono">{selectedRun.submission_id}</strong>
              </div>
              <div className="verification-overview-item">
                <span>Run ID</span>
                <strong className="text-mono">{selectedRun.id}</strong>
              </div>
              <div className="verification-overview-item">
                <span>Language</span>
                <strong>{relatedSubmission?.language || 'Not reported'}</strong>
              </div>
              <div className="verification-overview-item">
                <span>Overall status</span>
                <Badge variant={VERIFICATION_STATUSES[selectedRun.status]?.variant || 'secondary'} dot>
                  {VERIFICATION_STATUSES[selectedRun.status]?.label || selectedRun.status}
                </Badge>
              </div>
              <div className="verification-overview-item">
                <span>Execution duration</span>
                <strong>
                  {Number.isFinite(selectedRun.execution_telemetry?.duration_ms)
                    ? `${selectedRun.execution_telemetry.duration_ms.toFixed(1)} ms`
                    : 'Not available'}
                </strong>
              </div>
              <div className="verification-overview-item">
                <span>Docker execution</span>
                <strong>
                  {selectedRun.execution_telemetry?.docker_available === false
                    ? 'Unavailable'
                    : selectedRun.execution_telemetry?.docker_ready === true || selectedRun.test_results?.length > 0
                    ? 'Executed in sandbox'
                    : 'Not executed'}
                </strong>
              </div>
              {(selectedRun.evaluation_mode === 'LLM_ASSISTED' || selectedRun.execution_telemetry?.ai_contribution) && (
                <div className="verification-overview-item">
                  <span>Ollama inference</span>
                  <strong>
                    {selectedRun.execution_telemetry?.ai_contribution?.successful_llm_response_count > 0
                      ? 'Completed'
                      : selectedRun.execution_telemetry?.ai_contribution?.llm_enabled === false
                      ? 'Disabled; deterministic evidence used'
                      : aiEngineStatus?.ollama_connected
                      ? 'Available; no successful run inference recorded'
                      : 'Unavailable; deterministic evidence used'}
                  </strong>
                </div>
              )}
            </div>
            <div className="verification-requested-suites" aria-label="Requested test suites">
              <span>Requested:</span>
              {(selectedRun.requested_test_types || []).map((tt) => (
                <Badge key={tt} variant="secondary">{TEST_GROUP_LABELS[tt] || tt}</Badge>
              ))}
            </div>
          </section>

          {selectedRun.status === 'PASSED' && (
            <Alert type="success" title="SUCCESSFUL / PASSED">
              All executed authorized checks passed. See each testing category below for its actual execution status.
            </Alert>
          )}

          {/* CI/CD Agent Pipeline Telemetry Box */}
          <section className="verification-detail-section" aria-labelledby="testing-categories-heading">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                <span className="verification-section-kicker">Section 2</span>
                <span id="testing-categories-heading">Testing Categories</span>
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
                  <ExpandableDiagnostic
                    text={selectedRun.error_message}
                    variant="danger"
                    maxLength={100}
                  />
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

            <div
                className="testing-category-grid"
                aria-label="Testing category results"
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
                  gap: '0.5rem',
                  marginBottom: '0.75rem',
                }}
              >
                {['unit', 'integration', 'performance'].map((testType) => {
                  const report = selectedRun.execution_telemetry?.agent_reports?.[testType];
                  const metrics = report?.metrics;
                  const passedCount = testType === 'unit'
                    ? report?.passed_tests
                    : testType === 'integration'
                    ? report?.passed_interactions
                    : report?.status === 'PASSED' ? 1 : 0;
                  const failedCount = testType === 'unit'
                    ? report?.failed_tests
                    : testType === 'integration'
                    ? report?.failed_interactions
                    : report?.status === 'FAILED' ? 1 : 0;
                  const executedCount = testType === 'unit'
                    ? report?.total_tests
                    : testType === 'integration'
                    ? report?.total_interactions
                    : metrics?.sample_size;
                  const durationMs = testType === 'performance' ? metrics?.duration_ms : report?.duration_ms;
                  return (
                    <div
                      key={testType}
                      style={{
                        padding: '0.65rem',
                        border: '1px solid var(--border-color)',
                        borderRadius: 'var(--radius-sm)',
                        background: 'var(--bg-tertiary)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.4rem', marginBottom: '0.35rem' }}>
                        <strong style={{ fontSize: '0.75rem' }}>{TEST_GROUP_LABELS[testType]}</strong>
                        <Badge
                          variant={
                            report?.status === 'PASSED' ? 'success'
                            : report?.status === 'FAILED' ? 'danger'
                            : report?.status === 'ERROR' ? 'danger'
                            : report?.status === 'NOT_EXECUTED' ? 'warning'
                            : report?.status === 'BLOCKED' ? 'warning'
                            : 'secondary'
                          }
                          dot={Boolean(report)}
                        >
                          {report?.status || 'NOT EXECUTED'}
                        </Badge>
                      </div>
                      <div className="testing-category-metrics">
                        <span>Executed <strong>{report ? (executedCount ?? 0) : 0}</strong></span>
                        {testType !== 'performance' && (
                          <>
                            <span>Passed <strong>{passedCount ?? 0}</strong></span>
                            <span>Failed <strong>{failedCount ?? 0}</strong></span>
                          </>
                        )}
                        <span>Duration <strong>{Number.isFinite(durationMs) ? `${Number(durationMs).toFixed(1)} ms` : 'Not available'}</strong></span>
                      </div>
                      {metrics && (
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                          Measured latency (p95): {Number(metrics.latency_p95_ms || 0).toFixed(2)} ms<br />
                          Configured threshold: {Number(metrics.threshold_latency_ms || 0).toFixed(2)} ms<br />
                          Performance verdict: {metrics.is_breached ? 'THRESHOLD BREACHED' : 'WITHIN THRESHOLD'}
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>

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
                        <td className="diagnostic-cell">
                          <ExpandableDiagnostic
                            text={tr.error_message}
                            variant="danger"
                            maxLength={70}
                            emptyFallback="None"
                          />
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
          </section>

          {/* Evidence-Based Defect Reports Section */}
          <section className="verification-detail-section" aria-labelledby="defect-results-heading">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Bug size={16} color="var(--primary-400)" />
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  <span className="verification-section-kicker">Section 3</span>
                  <span id="defect-results-heading">Defect Detection Results</span>
                </span>
                {selectedRun.defect_reports && selectedRun.defect_reports.length > 0 && (
                  <Badge variant="danger" dot style={{ fontSize: '0.65rem' }}>
                    {selectedRun.defect_reports.length} {selectedRun.defect_reports.length === 1 ? 'Defect' : 'Defects'}
                  </Badge>
                )}
              </div>
            </div>

            {selectedRun.execution_telemetry?.ai_contribution && (
              <div style={{ marginBottom: '0.65rem', padding: '0.65rem', border: '1px solid rgba(99, 102, 241, 0.3)', borderRadius: 'var(--radius-sm)', background: 'rgba(99, 102, 241, 0.06)' }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 600, marginBottom: '0.3rem' }}>Local AI inference evidence</div>
                <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                  <Badge variant="secondary">Mode: {selectedRun.execution_telemetry.ai_contribution.evaluation_mode}</Badge>
                  <Badge variant={selectedRun.execution_telemetry.ai_contribution.llm_enabled ? 'success' : 'secondary'}>
                    LLM enabled: {String(selectedRun.execution_telemetry.ai_contribution.llm_enabled)}
                  </Badge>
                  <Badge variant="secondary">Invocations: {selectedRun.execution_telemetry.ai_contribution.actual_llm_invocation_count}</Badge>
                  <Badge variant={selectedRun.execution_telemetry.ai_contribution.successful_llm_response_count > 0 ? 'success' : 'warning'}>
                    Successful responses: {selectedRun.execution_telemetry.ai_contribution.successful_llm_response_count}
                  </Badge>
                  <Badge variant="secondary">Model: {selectedRun.execution_telemetry.ai_contribution.model_identifier}</Badge>
                </div>
              </div>
            )}

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
                  <strong style={{ color: 'var(--status-passed)' }}>No defects detected by the executed tests.</strong>
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
                        {relatedSubmission?.metadata?.is_multi_file && defect.file_path ? (
                          <button
                            type="button"
                            onClick={() => {
                              setActiveProjectFile(defect.file_path);
                              setCorrectedFilename(defect.file_path);
                              if (relatedSubmission?.metadata?.project_files?.[defect.file_path]) {
                                setCorrectedCode(relatedSubmission.metadata.project_files[defect.file_path]);
                              }
                            }}
                            title="Click to view file in project tree & source viewer"
                            style={{
                              background: 'rgba(59, 130, 246, 0.1)',
                              border: '1px solid rgba(59, 130, 246, 0.3)',
                              borderRadius: '3px',
                              padding: '1px 6px',
                              cursor: 'pointer',
                              fontFamily: 'var(--font-mono)',
                              fontSize: '0.75rem',
                              color: 'var(--primary-300, #93c5fd)',
                              fontWeight: 500,
                            }}
                          >
                            {defect.file_path}{defect.line_number ? `:${defect.line_number}` : ''} ↗
                          </button>
                        ) : (
                          <code style={{ color: 'var(--primary-300)' }}>
                            {defect.file_path || 'solution.py'}{defect.line_number ? `:${defect.line_number}` : ''}
                          </code>
                        )}
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

                    {defect.description && (
                      <div style={{ marginTop: '0.45rem', padding: '0.55rem', borderRadius: 'var(--radius-xs)', background: 'rgba(59, 130, 246, 0.06)', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                          <strong style={{ color: 'var(--text-primary)' }}>Verified facts:</strong>{' '}
                          {defect.description.split('\n[LLM Root Cause]:')[0]}
                        </div>
                        {defect.description.includes('\n[LLM Root Cause]:') && (
                          <div style={{ marginTop: '0.4rem', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                            <strong style={{ color: 'var(--primary-300)' }}>AI-assisted hypothesis:</strong>{' '}
                            {defect.description.split('\n[LLM Root Cause]:').slice(1).join('\n[LLM Root Cause]:').trim()}
                            <div style={{ marginTop: '0.25rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                              This hypothesis is grounded in the test evidence above and requires human review. It is not authorized Post-Delivery XAI.
                            </div>
                          </div>
                        )}
                        {defect.suggested_fix && (
                          <div style={{ marginTop: '0.4rem', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                            <strong style={{ color: 'var(--status-pending)' }}>Suggested correction:</strong> {defect.suggested_fix}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Diagnostic details */}
                    {defect.assertion_or_exception && (
                      <div style={{ marginTop: '0.35rem' }}>
                        <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '0.2rem' }}>
                          Failed Assertion / Exception Detail
                        </div>
                        <ExpandableDiagnostic
                          text={defect.assertion_or_exception}
                          variant="danger"
                          maxLength={90}
                        />
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
          </section>

          {renderSourceCodeViewer()}

          <section className="verification-detail-section verification-outcome" aria-labelledby="verification-outcome-heading">
            <div className="verification-section-heading">
              <div>
                <span className="verification-section-kicker">Section 5</span>
                <h4 id="verification-outcome-heading">Verification Outcome and Delivery</h4>
              </div>
              <Badge
                variant={selectedRun.status === 'PASSED' ? 'success' : selectedRun.status === 'FAILED' ? 'danger' : 'warning'}
                dot
              >
                {selectedRun.status === 'PASSED'
                  ? 'Verification Passed'
                  : selectedRun.status === 'FAILED'
                  ? 'Verification Failed'
                  : `Verification ${selectedRun.status}`}
              </Badge>
            </div>

            {selectedRun.status === 'FAILED' ? (
              <div className="verification-outcome-panel is-failed">
                <div>
                  <strong>Delivery blocked</strong>
                  <p>The submitted software cannot proceed to delivery because one or more executed checks failed.</p>
                  {selectedRun.test_results?.some((test) => test.status === 'FAILED') && (
                    <ul>
                      {selectedRun.test_results.filter((test) => test.status === 'FAILED').map((test, index) => (
                        <li key={`${test.test_name || test.name}-${index}`}>{test.test_name || test.name}</li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="xai-lock-status"><Lock size={15} /> Post-delivery XAI locked</div>
              </div>
            ) : selectedRun.status === 'PASSED' ? (
              <div className="verification-outcome-panel is-passed">
                <div>
                  <strong>Verification passed; delivery is a separate decision</strong>
                  <p>
                    Governance decision: {readinessReport?.readiness_status || 'Evaluating'}. Delivery status:{' '}
                    {xaiExplanation?.delivery_status?.replace(/_/g, ' ') || 'Pending delivery confirmation'}.
                  </p>
                </div>
                {['CONFIRMED_PRODUCTION_DELIVERY', 'CONFIRMED_DELIVERED'].includes(xaiExplanation?.delivery_status) && xaiExplanation?.post_delivery_explanation ? (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={BrainCircuit}
                    onClick={() => {
                      const targetRunId = selectedRun.id;
                      setSelectedRun(null);
                      navigate(`/xai?runId=${targetRunId}`);
                    }}
                  >
                    View Software Explanation
                  </Button>
                ) : (
                  <div className="xai-lock-status"><Lock size={15} /> Software explanation locked until authorized delivery</div>
                )}
              </div>
            ) : (
              <div className="verification-outcome-panel">
                Verification must complete before a delivery decision can be made. Post-delivery XAI remains locked.
              </div>
            )}
          </section>

          <details className="advanced-details">
            <summary>Advanced — Component 3 Feedback Integration</summary> {/* ui-copy-ignore: supervisor-required integration label */}
            <div className="advanced-details-content">
          {/* Technical Feedback & Component 3 Integration Section */}
          <div style={{ marginBottom: '1.25rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.625rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <FileJson size={16} color="var(--primary-400)" />
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Machine-Readable Feedback Preview
                </span>
                <Badge variant="secondary" style={{ fontSize: '0.625rem' }}>
                  Target: Component 3
                </Badge>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                {feedbackPreview?.eligible ? (
                  <Badge variant="success" dot style={{ fontSize: '0.65rem' }}>
                    Eligible for Component 3 Feedback
                  </Badge>
                ) : (
                  <Badge variant="secondary" style={{ fontSize: '0.65rem' }}>
                    Corrective Feedback Ineligible
                  </Badge>
                )}
                {/* Governance Lifecycle Pill */}
                {(() => {
                  const latestIter = selectedRun?.feedback_iterations?.length
                    ? selectedRun.feedback_iterations[selectedRun.feedback_iterations.length - 1]
                    : null;
                  if (!feedbackPreview?.eligible) return null;
                  if (latestIter?.delivery_status === 'ACKNOWLEDGED') {
                    return <Badge variant="success" style={{ fontSize: '0.65rem' }}>ACKNOWLEDGED</Badge>;
                  }
                  if (latestIter?.delivery_status === 'NOT_DISPATCHED') {
                    return <Badge variant="secondary" style={{ fontSize: '0.65rem' }}>NOT DISPATCHED (Fail-Closed)</Badge>;
                  }
                  if (latestIter?.delivery_status === 'FAILED') {
                    return <Badge variant="danger" style={{ fontSize: '0.65rem' }}>DISPATCH FAILED</Badge>;
                  }
                  if (latestIter?.delivery_status === 'UNKNOWN') {
                    return <Badge variant="warning" style={{ fontSize: '0.65rem' }}>UNKNOWN OUTCOME</Badge>;
                  }
                  if (latestIter?.delivery_status === 'PENDING_DELIVERY') {
                    return <Badge variant="warning" style={{ fontSize: '0.65rem' }}>DISPATCHING...</Badge>;
                  }
                  if (latestIter?.approval_status === 'APPROVED') {
                    return <Badge variant="accent" style={{ fontSize: '0.65rem' }}>APPROVED</Badge>;
                  }
                  return <Badge variant="secondary" style={{ fontSize: '0.65rem' }}>PREVIEW (Awaiting Approval)</Badge>;
                })()}
              </div>
            </div>

            {/* Repair Integration Status Banner */}
            <div
              style={{
                padding: '0.625rem 0.75rem',
                backgroundColor: 'rgba(234, 88, 12, 0.05)',
                border: '1px solid rgba(234, 88, 12, 0.25)',
                borderRadius: 'var(--radius-xs)',
                fontSize: '0.72rem',
                color: 'var(--text-secondary)',
                marginBottom: '0.75rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.3rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <ShieldAlert size={14} color="var(--primary-400)" />
                  Component 3 Integration Status:
                </span>
                <div style={{ display: 'flex', gap: '0.35rem' }}>
                  <Badge variant="outline" style={{ fontSize: '0.625rem' }}>
                    Contract: {c3Status?.contract_status || 'UNDER_DEVELOPMENT'}
                  </Badge>
                  <Badge variant={c3Status?.dispatch_allowed ? 'success' : 'secondary'} style={{ fontSize: '0.625rem' }}>
                    Delivery: {c3Status?.dispatch_allowed ? 'Enabled' : 'Disabled (Safety Lock)'}
                  </Badge>
                </div>
              </div>
              <p style={{ margin: 0, fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                {c3Status?.dispatch_allowed
                  ? (c3Status.reason || 'Component 3 integration is available for authorized feedback dispatch.')
                  : 'Component 3 integration unavailable. Technical feedback dispatch is safely disabled.'}
              </p>
            </div>

            {/* Explanation / Eligibility Status Message */}
            <div
              style={{
                padding: '0.625rem 0.75rem',
                backgroundColor: feedbackPreview?.eligible ? 'rgba(249, 115, 22, 0.06)' : 'var(--bg-tertiary)',
                border: feedbackPreview?.eligible ? '1px solid rgba(249, 115, 22, 0.2)' : '1px solid var(--border-color)',
                borderRadius: 'var(--radius-xs)',
                fontSize: '0.75rem',
                color: 'var(--text-secondary)',
                marginBottom: '0.75rem',
              }}
            >
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', marginBottom: '0.15rem' }}>
                Eligibility Decision:
              </div>
              {feedbackPreview?.reason || (selectedRun.status === 'PASSED'
                ? 'Verification run passed successfully; zero defects detected, so no corrective feedback is applicable.'
                : 'Evaluating technical feedback eligibility...')}
            </div>

            {/* Dispatch Action Notification */}
            {dispatchMessage && (
              <div
                style={{
                  padding: '0.5rem 0.75rem',
                  borderRadius: 'var(--radius-xs)',
                  fontSize: '0.72rem',
                  marginBottom: '0.75rem',
                  backgroundColor: dispatchMessage.type === 'success'
                    ? 'rgba(34, 197, 94, 0.1)'
                    : dispatchMessage.type === 'error'
                    ? 'rgba(239, 68, 68, 0.1)'
                    : 'rgba(59, 130, 246, 0.1)',
                  border: `1px solid ${
                    dispatchMessage.type === 'success'
                      ? 'rgba(34, 197, 94, 0.3)'
                      : dispatchMessage.type === 'error'
                      ? 'rgba(239, 68, 68, 0.3)'
                      : 'rgba(59, 130, 246, 0.3)'
                  }`,
                  color: 'var(--text-primary)',
                }}
              >
                {dispatchMessage.text}
              </div>
            )}

            {/* If Eligible: Show Technical Findings, Governance Controls, and Structured JSON Preview */}
            {feedbackPreview?.eligible && feedbackPreview.feedback && (() => {
              const latestIter = selectedRun?.feedback_iterations?.length
                ? selectedRun.feedback_iterations[selectedRun.feedback_iterations.length - 1]
                : null;
              const isApproved = latestIter?.approval_status === 'APPROVED';

              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                  {/* Findings Summary Pills */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.5rem', fontSize: '0.75rem' }}>
                    <div style={{ padding: '0.5rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.65rem', textTransform: 'uppercase', display: 'block' }}>Package ID</span>
                      <code style={{ color: 'var(--primary-300)' }}>{feedbackPreview.feedback.feedback_id}</code>
                    </div>
                    <div style={{ padding: '0.5rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.65rem', textTransform: 'uppercase', display: 'block' }}>Affected Files</span>
                      <span className="text-mono" style={{ color: 'var(--text-primary)' }}>
                        {feedbackPreview.feedback.affected_files?.join(', ') || 'solution.py'}
                      </span>
                    </div>
                    <div style={{ padding: '0.5rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.65rem', textTransform: 'uppercase', display: 'block' }}>Failed Assertions</span>
                      <span style={{ color: 'var(--status-failed)', fontWeight: 600 }}>
                        {feedbackPreview.feedback.failed_assertions?.length || 0} statement(s)
                      </span>
                    </div>
                  </div>

                  {/* Governance & Approval Controls Bar */}
                  <div
                    style={{
                      padding: '0.625rem 0.75rem',
                      background: 'var(--bg-tertiary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 'var(--radius-xs)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: '0.5rem',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                        Human Review & Dispatch Authorization
                      </div>
                      <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                        {isApproved
                          ? `Approved by ${latestIter.approved_by || 'Reviewer'} at ${formatDate(latestIter.approved_at)}`
                          : 'Explicit human approval is mandatory prior to sending defect payload for repair.'}
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                      {!isApproved ? (
                        <Button
                          variant="primary"
                          size="sm"
                          icon={CheckCircle}
                          onClick={() => handleApproveFeedback(selectedRun.id)}
                          loading={approvingFeedback}
                          style={{ height: '26px', fontSize: '0.7rem' }}
                        >
                          Approve Feedback for Component 3
                        </Button>
                      ) : (
                        <Badge variant="success" style={{ fontSize: '0.6875rem' }}>
                          ✓ Approved
                        </Badge>
                      )}

                      {/* Dispatch Button with Tooltip and Safety Lock */}
                      <Button
                        variant={c3Status?.dispatch_allowed ? 'primary' : 'secondary'}
                        size="sm"
                        icon={c3Status?.dispatch_allowed ? Send : Lock}
                        disabled={!c3Status?.dispatch_allowed}
                        title={
                          !c3Status?.dispatch_allowed
                            ? 'Component 3 integration unavailable. Outbound delivery is safely disabled.'
                            : 'Send authorized technical feedback to Component 3'
                        }
                        onClick={() => handleDispatchFeedback(selectedRun.id)}
                        loading={dispatchingFeedback}
                        style={{ height: '26px', fontSize: '0.7rem', opacity: c3Status?.dispatch_allowed ? 1 : 0.6 }}
                      >
                        {c3Status?.dispatch_allowed
                          ? 'Send Technical Feedback to Component 3'
                          : 'Component 3 Integration Unavailable'}
                      </Button>

                      {/* Test Fail-Closed Button to demonstrate safety verification */}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDispatchFeedback(selectedRun.id)}
                        loading={dispatchingFeedback}
                        title="Verifies fail-closed behavior: attempts dispatch to demonstrate safe error category recording and rejection."
                        style={{ height: '26px', fontSize: '0.6875rem', color: 'var(--text-muted)' }}
                      >
                        Test Fail-Closed
                      </Button>
                    </div>
                  </div>

                  {/* Formatted JSON Payload Card */}
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-xs)', overflow: 'hidden' }}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.4rem 0.625rem',
                        background: 'var(--bg-tertiary)',
                        borderBottom: '1px solid var(--border-color)',
                        fontSize: '0.72rem',
                      }}
                    >
                      <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                        payload.json (Schema v{feedbackPreview.feedback.schema_version})
                      </span>
                      <div style={{ display: 'flex', gap: '0.35rem' }}>
                        <Button
                          variant="outline"
                          size="sm"
                          icon={copiedFeedbackJson ? Check : Copy}
                          onClick={handleCopyFeedbackJson}
                          style={{ height: '24px', fontSize: '0.6875rem', padding: '0 0.5rem' }}
                        >
                          {copiedFeedbackJson ? 'Copied' : 'Copy JSON'}
                        </Button>
                      </div>
                    </div>
                    <pre
                      style={{
                        margin: 0,
                        padding: '0.625rem',
                        background: '#07090e',
                        fontSize: '0.7rem',
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--primary-300)',
                        maxHeight: '200px',
                        overflowX: 'auto',
                        whiteSpace: 'pre',
                        lineHeight: 1.5,
                      }}
                    >
                      {JSON.stringify(feedbackPreview.feedback, null, 2)}
                    </pre>
                  </div>
                </div>
              );
            })()}
          </div>

          {/* Repair Ingestion, Re-Verification & Defect Resolution Tracking Section */}
          <div style={{ marginBottom: '1.25rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.625rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Wrench size={16} color="var(--primary-400)" />
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Corrected Code Re-Verification
                </span>
                <Badge variant="secondary" style={{ fontSize: '0.625rem' }}>
                  Target: Verification Engine
                </Badge>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                  {repairAttempts.length} Recorded Attempt(s)
                </span>
                {selectedRun.status !== 'PASSED' && (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={Plus}
                    onClick={() => {
                      setShowIngestRepair((prev) => !prev);
                      setRepairError(null);
                      setRepairSuccessMessage(null);
                    }}
                    style={{ height: '26px', fontSize: '0.7rem' }}
                  >
                    {showIngestRepair ? 'Cancel Ingestion' : 'Submit Corrected Code'}
                  </Button>
                )}
              </div>
            </div>

            {/* Context Notice */}
            <div
              style={{
                padding: '0.625rem 0.75rem',
                backgroundColor: 'rgba(249, 115, 22, 0.04)',
                border: '1px solid rgba(249, 115, 22, 0.2)',
                borderRadius: 'var(--radius-xs)',
                fontSize: '0.72rem',
                color: 'var(--text-secondary)',
                marginBottom: '0.75rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.25rem',
              }}
            >
              <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                Deterministic Defect Resolution Tracking
              </div>
              <p style={{ margin: 0, fontSize: '0.6875rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                Ingest corrected source code to re-run test suites in the isolated Docker sandbox. The original failed submission remains unchanged. Defect resolutions, remaining issues, and regressions are deterministically verified against authorized test specifications.
              </p>
            </div>

            {/* Ingestion Alerts */}
            {repairSuccessMessage && (
              <div
                style={{
                  padding: '0.5rem 0.75rem',
                  borderRadius: 'var(--radius-xs)',
                  fontSize: '0.72rem',
                  marginBottom: '0.75rem',
                  backgroundColor: 'rgba(34, 197, 94, 0.1)',
                  border: '1px solid rgba(34, 197, 94, 0.3)',
                  color: 'var(--text-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span>{repairSuccessMessage}</span>
                <button
                  type="button"
                  onClick={() => setRepairSuccessMessage(null)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.8rem' }}
                >
                  ×
                </button>
              </div>
            )}

            {repairWarningMessage && (
              <div
                style={{
                  padding: '0.5rem 0.75rem',
                  borderRadius: 'var(--radius-xs)',
                  fontSize: '0.72rem',
                  marginBottom: '0.75rem',
                  backgroundColor: 'rgba(234, 179, 8, 0.1)',
                  border: '1px solid rgba(234, 179, 8, 0.3)',
                  color: 'var(--text-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <AlertTriangle size={14} color="var(--warning-color, #eab308)" />
                  <span>{repairWarningMessage}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setRepairWarningMessage(null)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.8rem' }}
                >
                  ×
                </button>
              </div>
            )}

            {repairError && (
              <div
                style={{
                  padding: '0.5rem 0.75rem',
                  borderRadius: 'var(--radius-xs)',
                  fontSize: '0.72rem',
                  marginBottom: '0.75rem',
                  backgroundColor: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: 'var(--status-failed)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span>{repairError}</span>
                <button
                  type="button"
                  onClick={() => setRepairError(null)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.8rem' }}
                >
                  ×
                </button>
              </div>
            )}

            {/* Inline Ingestion Form */}
            {showIngestRepair && (
              <div
                style={{
                  padding: '0.75rem',
                  backgroundColor: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-xs)',
                  marginBottom: '0.75rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.625rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Ingest Corrected Python Source Artifact
                  </span>
                  <Badge variant="outline" style={{ fontSize: '0.625rem' }}>
                    Sandboxed Re-Verification
                  </Badge>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                  <div>
                    <label style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
                      Filename (.py only)
                    </label>
                    <input
                      type="text"
                      className="form-input text-mono"
                      value={correctedFilename}
                      onChange={(e) => setCorrectedFilename(e.target.value)}
                      style={{ fontSize: '0.75rem', padding: '0.35rem 0.5rem' }}
                      placeholder="solution.py"
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
                      Provenance Source
                    </label>
                    <select
                      className="form-input"
                      value={repairSource}
                      onChange={(e) => setRepairSource(e.target.value)}
                      style={{ fontSize: '0.75rem', padding: '0.35rem 0.5rem' }}
                    >
                      <option value="LOCAL_MANUAL">Local Manual Fix</option>
                      <option value="LOCAL_UPLOAD">Local File Upload</option>
                      <option value="LOCAL_AUTOMATED">Automated Local Script</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
                    Corrected Source Code
                  </label>
                  <textarea
                    className="form-input text-mono"
                    rows={6}
                    value={correctedCode}
                    onChange={(e) => setCorrectedCode(e.target.value)}
                    placeholder="# Paste corrected Python implementation here..."
                    style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}
                  />
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                    Safety Policy: Code syntax is statically validated with AST parsing on host; execution occurs strictly within isolated Docker containers.
                  </span>
                </div>

                <div>
                  <label style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.2rem' }}>
                    Notes (Optional)
                  </label>
                  <input
                    type="text"
                    className="form-input"
                    value={repairNotes}
                    onChange={(e) => setRepairNotes(e.target.value)}
                    placeholder="Brief description of defect fix applied"
                    style={{ fontSize: '0.75rem', padding: '0.35rem 0.5rem' }}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.4rem', marginTop: '0.25rem' }}>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowIngestRepair(false)}
                    style={{ height: '26px', fontSize: '0.7rem' }}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    loading={ingestingRepair}
                    onClick={() => handleIngestRepair(selectedRun.id)}
                    style={{ height: '26px', fontSize: '0.7rem' }}
                  >
                    Ingest Corrected Code
                  </Button>
                </div>
              </div>
            )}

            {/* Repair Attempts List / Cards */}
            {loadingRepairs ? (
              <div style={{ padding: '0.75rem', color: 'var(--text-muted)', fontSize: '0.75rem', textAlign: 'center' }}>
                Loading repair history...
              </div>
            ) : repairAttempts.length === 0 ? (
              <div
                style={{
                  padding: '0.75rem',
                  backgroundColor: 'var(--bg-tertiary)',
                  border: '1px dashed var(--border-color)',
                  borderRadius: 'var(--radius-xs)',
                  fontSize: '0.72rem',
                  color: 'var(--text-muted)',
                  textAlign: 'center',
                }}
              >
                No repair iterations ingested for this run. Use &quot;Submit Corrected Code&quot; above to test fixes.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                {repairAttempts.map((attempt) => {
                  const comp = attempt.comparison;
                  const isReverifying = reverifyingRepairId === (attempt.repair_id || attempt.id);
                  const isBlockedOrInconclusive =
                    attempt.status === 'BLOCKED' ||
                    attempt.is_inconsistent ||
                    (!attempt.corrected_run_id && comp?.verdict === 'INCONCLUSIVE');
                  const isReverifiedSuccess = attempt.status === 'REVERIFIED' && !!attempt.corrected_run_id;

                  return (
                    <div
                      key={attempt.repair_id || attempt.id}
                      style={{
                        padding: '0.75rem',
                        backgroundColor: 'var(--bg-tertiary)',
                        border: '1px solid var(--border-color)',
                        borderRadius: 'var(--radius-xs)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.5rem',
                      }}
                    >
                      {/* Attempt Header Bar */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.4rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                          <code style={{ fontSize: '0.75rem', color: 'var(--primary-300)', fontWeight: 600 }}>
                            {attempt.repair_id || attempt.id}
                          </code>
                          <Badge variant="outline" style={{ fontSize: '0.625rem' }}>
                            {attempt.repair_source}
                          </Badge>
                          <Badge
                            variant={
                              isReverifiedSuccess
                                ? 'success'
                                : isBlockedOrInconclusive
                                ? 'warning'
                                : attempt.status === 'INGESTED'
                                ? 'warning'
                                : attempt.status === 'REVERIFYING'
                                ? 'primary'
                                : 'danger'
                            }
                            dot
                            style={{ fontSize: '0.625rem' }}
                          >
                            {isBlockedOrInconclusive ? 'BLOCKED' : attempt.status}
                          </Badge>
                          <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                            {formatDate(attempt.created_at)}
                          </span>
                        </div>

                        {/* Action buttons */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                          {attempt.status === 'INGESTED' ? (
                            <Button
                              variant="primary"
                              size="sm"
                              icon={PlayCircle}
                              loading={isReverifying}
                              onClick={() => handleReverifyRepair(selectedRun.id, attempt.repair_id || attempt.id)}
                              style={{ height: '24px', fontSize: '0.6875rem' }}
                            >
                              Run Verification Again
                            </Button>
                          ) : isReverifiedSuccess ? (
                            <Button
                              variant="outline"
                              size="sm"
                              icon={RotateCcw}
                              loading={reverifyingRepairId === (attempt.repair_id || attempt.id)}
                              onClick={() => setForceConfirmRepair(attempt)}
                              style={{ height: '24px', fontSize: '0.6875rem' }}
                              title="Re-run verification against this repair artifact"
                            >
                              Run Again (Force)
                            </Button>
                          ) : isBlockedOrInconclusive ? (
                            <Button
                              variant="secondary"
                              size="sm"
                              disabled
                              style={{ height: '24px', fontSize: '0.6875rem', opacity: 0.6 }}
                              title="Re-verification is blocked: trusted test suite is unavailable"
                            >
                              Blocked (Test Suite Required)
                            </Button>
                          ) : null}
                        </div>
                      </div>

                      {/* Corrected Submission Info */}
                      <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.72rem', color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>Corrected Submission: </span>
                          <code className="text-mono" style={{ color: 'var(--text-primary)' }}>
                            {attempt.corrected_submission_id}
                          </code>
                        </div>
                        {attempt.corrected_run_id && (
                          <div>
                            <span style={{ color: 'var(--text-muted)' }}>Re-Verification Run: </span>
                            <code className="text-mono" style={{ color: 'var(--primary-300)' }}>
                              {attempt.corrected_run_id}
                            </code>
                          </div>
                        )}
                        {attempt.notes && (
                          <div>
                            <span style={{ color: 'var(--text-muted)' }}>Notes: </span>
                            <span>{attempt.notes}</span>
                          </div>
                        )}
                      </div>

                      {/* Defect Resolution Comparison Section */}
                      {comp && (
                        <div
                          style={{
                            marginTop: '0.25rem',
                            padding: '0.625rem',
                            backgroundColor: 'var(--bg-input)',
                            borderRadius: 'var(--radius-xs)',
                            border: '1px solid var(--border-color)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '0.5rem',
                          }}
                        >
                          {/* Informative notice if verification was blocked or inconclusive */}
                          {isBlockedOrInconclusive && (
                            <div
                              style={{
                                padding: '0.5rem 0.75rem',
                                borderRadius: 'var(--radius-xs)',
                                backgroundColor: 'rgba(234, 179, 8, 0.1)',
                                border: '1px solid rgba(234, 179, 8, 0.3)',
                                color: 'var(--text-primary)',
                                fontSize: '0.72rem',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '0.25rem',
                              }}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600, color: 'var(--status-pending)' }}>
                                <AlertTriangle size={14} />
                                <span>Verification Blocked: Authorized Test Suite Unavailable</span>
                              </div>
                              <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
                                {comp.notes || attempt.notes || 'The original trusted test suite is unavailable. To prevent false positives or unsafe execution, re-verification cannot proceed until an authorized test suite is provided.'}
                              </p>
                            </div>
                          )}

                          {/* Verdict Summary Header */}
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.4rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                              <GitCompare size={14} color="var(--primary-400)" />
                              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                                Defect Resolution Outcome:
                              </span>
                              <Badge
                                variant={
                                  comp.verdict === 'FULLY_RESOLVED'
                                    ? 'success'
                                    : comp.verdict === 'PARTIALLY_RESOLVED'
                                    ? 'warning'
                                    : comp.verdict === 'REGRESSION_INTRODUCED'
                                    ? 'danger'
                                    : comp.verdict === 'UNRESOLVED'
                                    ? 'danger'
                                    : 'secondary'
                                }
                                style={{ fontSize: '0.65rem' }}
                              >
                                {comp.verdict === 'FULLY_RESOLVED'
                                  ? 'All Defects Resolved'
                                  : comp.verdict === 'PARTIALLY_RESOLVED'
                                  ? 'Partially Resolved'
                                  : comp.verdict === 'REGRESSION_INTRODUCED'
                                  ? 'Regression Introduced'
                                  : comp.verdict === 'UNRESOLVED'
                                  ? 'Defects Persist'
                                  : isBlockedOrInconclusive
                                  ? 'Blocked / Inconclusive'
                                  : 'Inconclusive'}
                              </Badge>
                            </div>
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-primary)', fontWeight: 600 }}>
                              Resolution Rate: {isBlockedOrInconclusive ? 'Inconclusive' : `${comp.resolution_rate}%`}
                            </span>
                          </div>

                          {/* Stats Metrics Grid */}
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '0.35rem', fontSize: '0.72rem' }}>
                            <div style={{ padding: '0.35rem 0.5rem', background: 'var(--bg-tertiary)', borderRadius: '3px', border: '1px solid var(--border-color)' }}>
                              <span style={{ color: 'var(--text-muted)', fontSize: '0.625rem', display: 'block' }}>ORIGINAL DEFECTS</span>
                              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{comp.original_defects_count}</span>
                            </div>
                            <div style={{ padding: '0.35rem 0.5rem', background: 'var(--bg-tertiary)', borderRadius: '3px', border: '1px solid var(--border-color)' }}>
                              <span style={{ color: 'var(--text-muted)', fontSize: '0.625rem', display: 'block' }}>RESOLVED</span>
                              <span style={{ fontWeight: 600, color: 'var(--status-passed)' }}>{comp.resolved_defects_count}</span>
                            </div>
                            <div style={{ padding: '0.35rem 0.5rem', background: 'var(--bg-tertiary)', borderRadius: '3px', border: '1px solid var(--border-color)' }}>
                              <span style={{ color: 'var(--text-muted)', fontSize: '0.625rem', display: 'block' }}>REMAINING</span>
                              <span style={{ fontWeight: 600, color: isBlockedOrInconclusive ? 'var(--text-muted)' : (comp.remaining_defects_count > 0 ? 'var(--status-failed)' : 'var(--text-muted)') }}>
                                {isBlockedOrInconclusive ? 'Inconclusive' : comp.remaining_defects_count}
                              </span>
                            </div>
                            <div style={{ padding: '0.35rem 0.5rem', background: 'var(--bg-tertiary)', borderRadius: '3px', border: '1px solid var(--border-color)' }}>
                              <span style={{ color: 'var(--text-muted)', fontSize: '0.625rem', display: 'block' }}>NEW REGRESSIONS</span>
                              <span style={{ fontWeight: 600, color: comp.new_defects_count > 0 ? 'var(--status-failed)' : 'var(--text-muted)' }}>
                                {comp.new_defects_count}
                              </span>
                            </div>
                          </div>

                          {/* Test-Level Comparison Details Table */}
                          {comp.test_comparisons && comp.test_comparisons.length > 0 && (
                            <div style={{ marginTop: '0.25rem' }}>
                              <span style={{ fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '0.2rem' }}>
                                Test Suite Verification Details:
                              </span>
                              <div className="table-responsive">
                                <table className="data-table" style={{ fontSize: '0.7rem' }}>
                                  <thead>
                                    <tr>
                                      <th>Test Case</th>
                                      <th>Original</th>
                                      <th>Corrected</th>
                                      <th>Resolution Outcome</th>
                                      <th>Diagnostic Notes</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {comp.test_comparisons.map((tc, idx) => (
                                      <tr key={idx}>
                                        <td className="text-mono" style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                                          {tc.test_name}
                                        </td>
                                        <td>
                                          <Badge variant={tc.original_status === 'PASSED' ? 'success' : 'danger'}>
                                            {tc.original_status}
                                          </Badge>
                                        </td>
                                        <td>
                                          <Badge variant={tc.corrected_status === 'PASSED' ? 'success' : 'danger'}>
                                            {tc.corrected_status}
                                          </Badge>
                                        </td>
                                        <td>
                                          <Badge
                                            variant={
                                              tc.resolution_status === 'RESOLVED'
                                                ? 'success'
                                                : tc.resolution_status === 'NEW_FAILURE'
                                                ? 'danger'
                                                : tc.resolution_status === 'STILL_FAILING'
                                                ? 'danger'
                                                : 'warning'
                                            }
                                          >
                                            {tc.resolution_status}
                                          </Badge>
                                        </td>
                                        <td className="diagnostic-cell" style={{ color: 'var(--text-secondary)' }}>
                                          <ExpandableDiagnostic
                                            text={tc.notes || tc.error_message}
                                            variant="default"
                                            maxLength={60}
                                            emptyFallback="—"
                                          />
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
            </div>
          </details>

          {/* Verification Governance & Deployment Readiness Section */}
          <details className="advanced-details">
            <summary>Advanced — Governance &amp; Research Diagnostics</summary>
            <div className="advanced-details-content">
          <div style={{ marginBottom: '1.25rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.625rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <ShieldCheck size={16} color="var(--primary-400)" />
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Governance &amp; Research Diagnostics
                </span>
                <Badge variant="secondary" style={{ fontSize: '0.625rem' }}>
                  Safety Gates
                </Badge>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.75rem' }}>
              {/* Convergence Risk Assessment Card */}
              <div
                style={{
                  padding: '0.75rem',
                  backgroundColor: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-xs)',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '0.5rem',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                      Module Convergence Risk
                    </span>
                    <Badge
                      variant={
                        convergenceReport?.risk_level === 'LOW'
                          ? 'success'
                          : convergenceReport?.risk_level === 'MEDIUM'
                          ? 'warning'
                          : 'danger'
                      }
                      style={{ fontSize: '0.65rem' }}
                    >
                      {convergenceReport?.risk_level ? `${convergenceReport.risk_level} RISK` : 'EVALUATING'}
                    </Badge>
                  </div>
                  <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: '0 0 0.5rem', lineHeight: 1.4 }}>
                    {convergenceReport?.risk_justification || 'Analyzes iteration cycles, defect stability, and potential test weakening across revisions.'}
                  </p>
                  {convergenceReport?.escalation_required && (
                    <div style={{ padding: '0.35rem 0.5rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: '3px', fontSize: '0.6875rem', color: 'var(--status-failed)', marginBottom: '0.35rem' }}>
                      <strong>Human Review Required:</strong> {convergenceReport.escalation_reason || 'Escalation triggered due to cycle threshold.'}
                    </div>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowConvergenceModal(true)}
                  style={{ alignSelf: 'flex-start', fontSize: '0.7rem' }}
                >
                  View Convergence Risk Report
                </Button>
              </div>

              {/* Deployment Readiness Certificate Card */}
              <div
                style={{
                  padding: '0.75rem',
                  backgroundColor: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-xs)',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '0.5rem',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                      Deployment Authorization
                    </span>
                    <Badge
                      variant={
                        readinessReport?.readiness_status === 'READY'
                          ? 'success'
                          : readinessReport?.readiness_status === 'NEEDS_REVIEW'
                          ? 'warning'
                          : 'danger'
                      }
                      style={{ fontSize: '0.65rem' }}
                    >
                      {readinessReport?.readiness_status ? `GATE: ${readinessReport.readiness_status}` : 'GATE: EVALUATING'}
                    </Badge>
                  </div>
                  <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: '0 0 0.5rem', lineHeight: 1.4 }}>
                    {readinessReport?.is_ready_for_deployment
                      ? 'All verification safety gates satisfied. Module is formally authorized for downstream promotion.'
                      : `Deployment blocked by ${readinessReport?.blocking_reasons?.length || 1} outstanding safety gate condition(s).`}
                  </p>
                  {readinessReport?.provenance_hash && (
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      Provenance SHA: {readinessReport.provenance_hash.slice(0, 16)}...
                    </div>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowReadinessModal(true)}
                  style={{ alignSelf: 'flex-start', fontSize: '0.7rem' }}
                >
                  View Deployment Readiness Report
                </Button>
              </div>
            </div>
          </div>
            </div>
          </details>

        </Modal>
      )}

      {/* Forced Re-Verification Confirmation Modal */}
      <Modal
        isOpen={!!forceConfirmRepair}
        onClose={() => {
          if (!reverifyingRepairId) {
            setForceConfirmRepair(null);
          }
        }}
        title="Confirm Re-Verification Execution"
        size="md"
        className="modal-confirmation-dialog"
        footer={
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', width: '100%' }}>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setForceConfirmRepair(null)}
              disabled={!!reverifyingRepairId}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={RotateCcw}
              loading={reverifyingRepairId === (forceConfirmRepair?.repair_id || forceConfirmRepair?.id)}
              disabled={!!reverifyingRepairId}
              onClick={handleConfirmForceReverify}
            >
              Run Verification Again
            </Button>
          </div>
        }
      >
        <div className="force-reverify-modal-content">
          <p style={{ color: 'var(--text-primary)', fontSize: '0.875rem', lineHeight: 1.5, marginBottom: '1rem' }}>
            The corrected code will be tested again against the authorized test specifications in an isolated execution sandbox.
          </p>

          {forceConfirmRepair && (
            <div
              style={{
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.75rem',
                marginBottom: '1rem',
                fontSize: '0.75rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.35rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Target Repair ID:</span>
                <span className="text-mono" style={{ color: 'var(--primary-400)', fontWeight: 500 }}>
                  {forceConfirmRepair.repair_id || forceConfirmRepair.id}
                </span>
              </div>
              {forceConfirmRepair.corrected_submission_id && (
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Corrected Submission:</span>
                  <span className="text-mono" style={{ color: 'var(--text-secondary)' }}>
                    {forceConfirmRepair.corrected_submission_id}
                  </span>
                </div>
              )}
            </div>
          )}

          <ul
            style={{
              margin: 0,
              paddingLeft: '1.25rem',
              color: 'var(--text-secondary)',
              fontSize: '0.8125rem',
              lineHeight: 1.6,
              display: 'flex',
              flexDirection: 'column',
              gap: '0.35rem',
            }}
          >
            <li>
              <strong>New Execution:</strong> A new execution will be started in the container sandbox to evaluate the corrected source code.
            </li>
            <li>
              <strong>Preserved Evidence:</strong> Existing verification evidence and history will be preserved without overwriting prior test records.
            </li>
            <li>
              <strong>Execution Time:</strong> The operation may take some time depending on test suite complexity and container provisioning.
            </li>
          </ul>
        </div>
      </Modal>

      {/* Module Convergence Risk Report Modal */}
      {showConvergenceModal && (
        <Modal
          isOpen={showConvergenceModal}
          onClose={() => setShowConvergenceModal(false)}
          title={`Module Convergence Risk Report: ${selectedRun?.id}`}
          size="lg"
          footer={
            <Button variant="secondary" size="sm" onClick={() => setShowConvergenceModal(false)}>
              Close
            </Button>
          }
        >
          {convergenceReport ? (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '1rem', fontSize: '0.8125rem' }}>
                <div>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Risk Level</span>
                  <div>
                    <Badge
                      variant={
                        convergenceReport.risk_level === 'LOW'
                          ? 'success'
                          : convergenceReport.risk_level === 'MEDIUM'
                          ? 'warning'
                          : 'danger'
                      }
                      dot
                    >
                      {convergenceReport.risk_level}
                    </Badge>
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Total Iterations</span>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                    {convergenceReport.total_iterations}
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Superficial Convergence</span>
                  <div>
                    <Badge variant={convergenceReport.is_superficial_convergence ? 'danger' : 'success'}>
                      {convergenceReport.is_superficial_convergence ? 'DRIFT DETECTED' : 'SAFE'}
                    </Badge>
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Escalation Status</span>
                  <div>
                    <Badge variant={convergenceReport.escalation_required ? 'danger' : 'secondary'}>
                      {convergenceReport.escalation_required ? 'ESCALATION REQUIRED' : 'NORMAL'}
                    </Badge>
                  </div>
                </div>
              </div>

              <div style={{ padding: '0.75rem', background: 'var(--bg-tertiary)', borderRadius: '4px', border: '1px solid var(--border-color)', marginBottom: '1rem', fontSize: '0.75rem' }}>
                <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.25rem' }}>
                  Risk Justification & Diagnostic Analysis
                </span>
                <p style={{ color: 'var(--text-primary)', lineHeight: 1.5, margin: 0 }}>
                  {convergenceReport.risk_justification}
                </p>
              </div>

              {convergenceReport.diagnostic_signals && convergenceReport.diagnostic_signals.length > 0 && (
                <div style={{ marginBottom: '1rem' }}>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.35rem' }}>
                    Observed Diagnostic Signals
                  </span>
                  <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    {convergenceReport.diagnostic_signals.map((signal, idx) => (
                      <li key={idx} style={{ marginBottom: '0.2rem' }}>{signal}</li>
                    ))}
                  </ul>
                </div>
              )}

              {convergenceReport.iteration_history && convergenceReport.iteration_history.length > 0 && (
                <div>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.35rem' }}>
                    Iteration Cycle History
                  </span>
                  <div className="table-responsive">
                    <table className="data-table" style={{ fontSize: '0.72rem' }}>
                      <thead>
                        <tr>
                          <th>Cycle #</th>
                          <th>Status</th>
                          <th>Defects Reported</th>
                          <th>Resolved Defects</th>
                          <th>Timestamp</th>
                        </tr>
                      </thead>
                      <tbody>
                        {convergenceReport.iteration_history.map((it, idx) => (
                          <tr key={idx}>
                            <td className="text-mono" style={{ fontWeight: 600 }}>#{it.iteration_number}</td>
                            <td><Badge variant="secondary">{it.status}</Badge></td>
                            <td style={{ color: it.defects_count > 0 ? 'var(--status-failed)' : 'var(--status-passed)' }}>
                              {it.defects_count}
                            </td>
                            <td style={{ color: 'var(--status-passed)' }}>{it.resolved_defects}</td>
                            <td style={{ color: 'var(--text-muted)' }}>{formatDate(it.timestamp)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              Loading convergence risk evaluation...
            </div>
          )}
        </Modal>
      )}

      {/* Deployment Readiness Certificate Modal */}
      {showReadinessModal && (
        <Modal
          isOpen={showReadinessModal}
          onClose={() => setShowReadinessModal(false)}
          title={`Deployment Readiness Certificate: ${readinessReport?.report_id || selectedRun?.id}`}
          size="lg"
          footer={
            <Button variant="secondary" size="sm" onClick={() => setShowReadinessModal(false)}>
              Close
            </Button>
          }
        >
          {readinessReport ? (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '1rem', fontSize: '0.8125rem' }}>
                <div>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Release Status</span>
                  <div>
                    <Badge
                      variant={
                        readinessReport.readiness_status === 'READY'
                          ? 'success'
                          : readinessReport.readiness_status === 'NEEDS_REVIEW'
                          ? 'warning'
                          : 'danger'
                      }
                      dot
                    >
                      {readinessReport.readiness_status}
                    </Badge>
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Target Module</span>
                  <div className="text-mono" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                    {readinessReport.module_name}
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Sign-Off Authority</span>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    {readinessReport.sign_off_authority}
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Certified At</span>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    {formatDate(readinessReport.issued_at)}
                  </div>
                </div>
              </div>

              {readinessReport.blocking_reasons && readinessReport.blocking_reasons.length > 0 && (
                <div style={{ marginBottom: '1rem' }}>
                  <Alert type="danger" title="Deployment Safety Gate Violations">
                    <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.75rem' }}>
                      {readinessReport.blocking_reasons.map((reason, idx) => (
                        <li key={idx} style={{ marginBottom: '0.2rem' }}>{reason}</li>
                      ))}
                    </ul>
                  </Alert>
                </div>
              )}

              <div style={{ marginBottom: '1rem' }}>
                <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '0.35rem' }}>
                  Mandatory Safety Gating Checks
                </span>
                <div className="table-responsive">
                  <table className="data-table" style={{ fontSize: '0.72rem' }}>
                    <thead>
                      <tr>
                        <th>Gating Condition</th>
                        <th>Status</th>
                        <th>Required</th>
                        <th>Evaluation Rationale</th>
                      </tr>
                    </thead>
                    <tbody>
                      {readinessReport.gating_checks.map((gate, idx) => (
                        <tr key={idx}>
                          <td className="text-mono" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                            {gate.gate_name}
                          </td>
                          <td>
                            <Badge variant={gate.status === 'PASSED' ? 'success' : 'danger'}>
                              {gate.status}
                            </Badge>
                          </td>
                          <td>
                            <span style={{ color: gate.required ? 'var(--status-failed)' : 'var(--text-muted)' }}>
                              {gate.required ? 'MANDATORY' : 'OPTIONAL'}
                            </span>
                          </td>
                          <td style={{ color: 'var(--text-secondary)' }}>{gate.details}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={{ padding: '0.5rem 0.75rem', background: 'var(--bg-tertiary)', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '0.7rem' }}>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.65rem', textTransform: 'uppercase' }}>
                  Cryptographic Provenance Hash
                </span>
                <span className="text-mono" style={{ color: 'var(--primary-300)', wordBreak: 'break-all' }}>
                  {readinessReport.provenance_hash}
                </span>
              </div>
            </div>
          ) : (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              Loading deployment readiness assessment...
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
