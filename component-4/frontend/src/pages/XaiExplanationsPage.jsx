import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  BrainCircuit,
  RefreshCw,
  CheckCircle2,
  AlertOctagon,
  AlertTriangle,
  Clock,
  ArrowRightCircle,
  ArrowLeftCircle,
  ExternalLink,
  Copy,
  Check,
  ShieldCheck,
  HelpCircle,
  FileCode2,
  Cpu,
} from 'lucide-react';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import Alert from '../components/common/Alert';
import EmptyState from '../components/common/EmptyState';
import LoadingSkeleton from '../components/common/LoadingSkeleton';
import { getVerificationRuns, getXaiExplanation } from '../api/verificationApi';
import { formatDate, formatRelativeTime } from '../utils/formatters';

export default function XaiExplanationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(searchParams.get('runId') || '');
  const [explanation, setExplanation] = useState(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingExplanation, setLoadingExplanation] = useState(false);
  const [error, setError] = useState(null);
  const [copiedSummary, setCopiedSummary] = useState(false);

  // Load all verification runs for the selector
  const fetchRuns = async () => {
    setLoadingRuns(true);
    setError(null);
    try {
      const data = await getVerificationRuns({ limit: 100 });
      const items = data.items || [];
      setRuns(items);

      // Default to URL param or the first failed/available run
      const requestedId = searchParams.get('runId');
      if (requestedId && items.some((r) => r.id === requestedId)) {
        setSelectedRunId(requestedId);
      } else if (items.length > 0 && !selectedRunId) {
        // Prefer a failed run if one exists, else first run
        const failedRun = items.find((r) => r.status === 'FAILED');
        const defaultRun = failedRun || items[0];
        setSelectedRunId(defaultRun.id);
        setSearchParams({ runId: defaultRun.id });
      }
    } catch (err) {
      setError(`Failed to load verification runs: ${err.message}`);
    } finally {
      setLoadingRuns(false);
    }
  };

  useEffect(() => {
    fetchRuns();
  }, []);

  // Fetch explanation when selectedRunId changes
  useEffect(() => {
    if (!selectedRunId) {
      setExplanation(null);
      return;
    }

    const fetchExplanation = async () => {
      setLoadingExplanation(true);
      setError(null);
      try {
        const data = await getXaiExplanation(selectedRunId);
        setExplanation(data);
      } catch (err) {
        setError(`Failed to retrieve XAI explanation for run ${selectedRunId}: ${err.message}`);
        setExplanation(null);
      } finally {
        setLoadingExplanation(false);
      }
    };

    fetchExplanation();
  }, [selectedRunId]);

  const handleSelectRun = (runId) => {
    setSelectedRunId(runId);
    setSearchParams({ runId });
  };

  const handleCopySummary = async () => {
    if (!explanation) return;
    const textToCopy = `XAI Explanation for ${explanation.verification_run_id} (${explanation.verification_status})
Method: ${explanation.explanation_method}
Summary: ${explanation.summary}

Why Inconsistent:
${explanation.evidence_based_interpretation}

Recommendation:
[${explanation.recommendation?.action}] ${explanation.recommendation?.reason}`;

    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedSummary(true);
      setTimeout(() => setCopiedSummary(false), 2000);
    } catch {
      setCopiedSummary(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'PASSED':
        return <Badge variant="success" dot>PASSED</Badge>;
      case 'FAILED':
        return <Badge variant="danger" dot>FAILED</Badge>;
      case 'ERROR':
        return <Badge variant="warning" dot>ERROR</Badge>;
      default:
        return <Badge variant="secondary" dot>{status || 'UNKNOWN'}</Badge>;
    }
  };

  const getRecommendationBadge = (action) => {
    switch (action) {
      case 'RETURN_TO_COMPONENT_3':
        return (
          <Badge variant="danger" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}>
            SEND FOR REPAIR
          </Badge>
        );
      case 'ACCEPT_VERIFICATION':
        return (
          <Badge variant="success" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}>
            ACCEPT VERIFICATION (PASS)
          </Badge>
        );
      case 'RETRY_INFRASTRUCTURE':
        return (
          <Badge variant="warning" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}>
            RETRY INFRASTRUCTURE
          </Badge>
        );
      default:
        return (
          <Badge variant="secondary" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}>
            {action || 'PENDING EVALUATION'}
          </Badge>
        );
    }
  };

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">
              <BrainCircuit size={22} color="var(--primary-400)" />
              <span>Human-Facing XAI Explanations</span>
              <Badge variant="secondary" style={{ fontSize: '0.6875rem' }}>
                Target: Reviewer
              </Badge>
            </h1>
            <p className="page-description">
              Evidence-grounded root-cause reasoning and repair recommendations for software engineers, derived directly from test execution outcomes.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              onClick={fetchRuns}
              loading={loadingRuns}
            >
              Refresh Telemetry
            </Button>
          </div>
        </div>
      </div>

      {/* Target Audience Decoupling Notice */}
      <div
        style={{
          padding: '0.75rem 1rem',
          borderRadius: 'var(--radius-sm)',
          backgroundColor: 'rgba(249, 115, 22, 0.05)',
          border: '1px solid rgba(249, 115, 22, 0.25)',
          marginBottom: '1.25rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.75rem',
          fontSize: '0.8125rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <ShieldCheck size={18} color="var(--primary-400)" />
          <span style={{ color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--text-primary)' }}>Engineering Explanations:</strong>{' '}
            Diagnostic narratives provide human-readable root-cause analysis for code review, decoupled from automated machine-level repair payloads.
          </span>
        </div>
      </div>

      {/* Verification Run Selector Card */}
      <Card
        title="Target Verification Run"
        subtitle="Select a verified run to inspect evidence-grounded XAI explanations"
        style={{ marginBottom: '1.25rem' }}
      >
        {loadingRuns ? (
          <LoadingSkeleton count={1} height="40px" />
        ) : runs.length === 0 ? (
          <EmptyState
            title="No Verification Runs Detected"
            description="Initiate and execute a code verification run in the Verification Runs page to view explainable diagnostics."
          />
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 320px' }}>
              <label htmlFor="run-selector" className="form-label" style={{ marginBottom: '0.35rem' }}>
                Active Verification Pipeline
              </label>
              <select
                id="run-selector"
                className="form-input text-mono"
                value={selectedRunId}
                onChange={(e) => handleSelectRun(e.target.value)}
                style={{ fontSize: '0.8125rem', padding: '0.5rem 0.75rem' }}
              >
                {runs.map((r) => {
                  const defectCount = r.defect_reports?.length || 0;
                  return (
                    <option key={r.id} value={r.id}>
                      {r.id} — [{r.status}] — {defectCount} defect(s) — {r.submission_id} ({formatRelativeTime(r.created_at)})
                    </option>
                  );
                })}
              </select>
            </div>

            {selectedRunId && (
              <div style={{ display: 'flex', gap: '0.5rem', alignSelf: 'flex-end', marginBottom: '2px' }}>
                <Button
                  variant="outline"
                  size="sm"
                  icon={ExternalLink}
                  onClick={() => navigate('/verifications')}
                  title="View full pipeline runs"
                >
                  Inspect in Verifications
                </Button>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Error state */}
      {error && (
        <Alert type="danger" title="Explanation Retrieval Error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Loading Explanation Skeleton */}
      {loadingExplanation && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <LoadingSkeleton count={3} height="80px" />
        </div>
      )}

      {/* Loaded Explanation Content */}
      {!loadingExplanation && explanation && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Metadata & Eligibility Banner */}
          <div
            style={{
              padding: '1rem',
              background: 'var(--bg-card)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-color)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <span className="text-mono" style={{ fontWeight: 600, fontSize: '0.9375rem', color: 'var(--text-primary)' }}>
                  {explanation.verification_run_id}
                </span>
                {getStatusBadge(explanation.verification_status)}
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Submission: <code style={{ color: 'var(--primary-300)' }}>{explanation.submission_id}</code>
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                {explanation.eligible ? (
                  <Badge variant="danger" dot style={{ fontSize: '0.6875rem' }}>
                    Eligible for Corrective Explanation
                  </Badge>
                ) : (
                  <Badge variant="secondary" style={{ fontSize: '0.6875rem' }}>
                    Corrective Feedback Ineligible
                  </Badge>
                )}
                <Badge variant="secondary" style={{ fontSize: '0.6875rem' }}>
                  Schema v{explanation.schema_version}
                </Badge>
              </div>
            </div>

            {/* Eligibility Evaluation Note */}
            <div
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: explanation.eligible ? 'rgba(239, 68, 68, 0.05)' : 'var(--bg-input)',
                border: explanation.eligible ? '1px solid rgba(239, 68, 68, 0.18)' : '1px solid var(--border-color)',
                borderRadius: 'var(--radius-xs)',
                fontSize: '0.75rem',
                color: 'var(--text-secondary)',
              }}
            >
              <strong style={{ color: 'var(--text-primary)' }}>Eligibility Decision:</strong>{' '}
              {explanation.eligibility_reason}
            </div>

            {/* Inference Provenance & Model Attestation */}
            {explanation.inference_provenance && (
              <div
                style={{
                  padding: '0.6rem 0.85rem',
                  backgroundColor: explanation.inference_provenance.genuine_inference
                    ? 'rgba(99, 102, 241, 0.08)'
                    : 'rgba(245, 158, 11, 0.08)',
                  border: explanation.inference_provenance.genuine_inference
                    ? '1px solid rgba(99, 102, 241, 0.25)'
                    : '1px solid rgba(245, 158, 11, 0.25)',
                  borderRadius: 'var(--radius-xs)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '0.6rem',
                  fontSize: '0.78rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
                  <Cpu size={16} color={explanation.inference_provenance.genuine_inference ? '#818cf8' : '#f59e0b'} />
                  <span style={{ color: 'var(--text-secondary)' }}>
                    <strong style={{ color: 'var(--text-primary)' }}>Inference Provenance:</strong>{' '}
                    {explanation.inference_provenance.genuine_inference ? (
                      <span>
                        Synthesized by local LLM <code style={{ color: '#818cf8', fontWeight: 600 }}>{explanation.inference_provenance.model || 'qwen2.5-coder:3b'}</code> via Ollama (grounded in verified pytest observations)
                      </span>
                    ) : (
                      <span>
                        Deterministic Evidence Baseline ({explanation.inference_provenance.fallback_reason || 'Rule-based generator'})
                      </span>
                    )}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  {explanation.inference_provenance.genuine_inference ? (
                    <Badge variant="primary" style={{ fontSize: '0.65rem' }}>
                      GENUINE LOCAL LLM
                    </Badge>
                  ) : (
                    <Badge variant="warning" style={{ fontSize: '0.65rem' }}>
                      DETERMINISTIC FALLBACK
                    </Badge>
                  )}
                  {explanation.inference_provenance.duration_ms && (
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      {(explanation.inference_provenance.duration_ms / 1000).toFixed(2)}s
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Section 1: Executive Findings Summary */}
          <Card
            title="1. Executive Findings Summary"
            subtitle="High-level synthesis of verification telemetry for engineering review"
            action={
              <Button
                variant="outline"
                size="sm"
                icon={copiedSummary ? Check : Copy}
                onClick={handleCopySummary}
                style={{ height: '24px', fontSize: '0.6875rem' }}
              >
                {copiedSummary ? 'Copied' : 'Copy Explanation'}
              </Button>
            }
          >
            <p style={{ fontSize: '0.875rem', color: 'var(--text-primary)', lineHeight: 1.6, margin: 0 }}>
              {explanation.summary}
            </p>
          </Card>

          {/* Section 2: What Failed? */}
          <Card
            title="2. What Failed?"
            subtitle="Specific tests and assertion statements that failed during containerized execution"
          >
            {explanation.what_failed && explanation.what_failed.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {explanation.what_failed.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '0.6rem 0.8rem',
                      background: 'rgba(239, 68, 68, 0.05)',
                      border: '1px solid rgba(239, 68, 68, 0.2)',
                      borderRadius: 'var(--radius-xs)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.6rem',
                      fontSize: '0.8125rem',
                      color: 'var(--text-primary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    <AlertOctagon size={15} color="var(--status-failed)" style={{ flexShrink: 0 }} />
                    <span style={{ wordBreak: 'break-all' }}>{item}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                Zero test failures or assertion exceptions occurred in this verification run.
              </div>
            )}
          </Card>

          {/* Section 3: Confirmed Observations (Empirical Facts) */}
          <Card
            title="3. Confirmed Observations"
            subtitle="Empirical facts extracted directly from pytest output (no fabricated line numbers or values)"
          >
            {explanation.confirmed_observations && explanation.confirmed_observations.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                {explanation.confirmed_observations.map((obs, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '0.85rem',
                      background: 'var(--bg-input)',
                      borderRadius: 'var(--radius-xs)',
                      border: '1px solid var(--border-color)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.6rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <code style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--primary-300)' }}>
                          {obs.test_name}
                        </code>
                        <Badge variant="secondary" style={{ fontSize: '0.65rem' }}>
                          {obs.failure_category || 'ASSERTION_FAILURE'}
                        </Badge>
                      </div>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {obs.file_path}{obs.line_number ? `:${obs.line_number}` : ''}
                      </span>
                    </div>

                    {/* Expected vs Observed Grid */}
                    {(obs.expected_value !== null || obs.observed_value !== null) && (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.6rem' }}>
                        <div
                          style={{
                            padding: '0.5rem 0.75rem',
                            backgroundColor: 'rgba(16, 185, 129, 0.08)',
                            border: '1px solid rgba(16, 185, 129, 0.25)',
                            borderRadius: 'var(--radius-xs)',
                          }}
                        >
                          <span style={{ fontSize: '0.6875rem', textTransform: 'uppercase', color: 'var(--status-passed)', fontWeight: 600, display: 'block' }}>
                            Expected Value (Oracle)
                          </span>
                          <span className="text-mono" style={{ fontSize: '0.8125rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                            {obs.expected_value !== null ? String(obs.expected_value) : '—'}
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
                          <span style={{ fontSize: '0.6875rem', textTransform: 'uppercase', color: 'var(--status-failed)', fontWeight: 600, display: 'block' }}>
                            Observed Value (Actual Output)
                          </span>
                          <span className="text-mono" style={{ fontSize: '0.8125rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                            {obs.observed_value !== null ? String(obs.observed_value) : '—'}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Assertion statement diff */}
                    {obs.assertion_or_exception && (
                      <div
                        style={{
                          padding: '0.5rem 0.65rem',
                          background: '#07080c',
                          border: '1px solid var(--border-color)',
                          borderRadius: 'var(--radius-xs)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.75rem',
                          color: 'var(--status-failed)',
                        }}
                      >
                        {obs.assertion_or_exception}
                      </div>
                    )}

                    {/* Diagnostic Traceback */}
                    {obs.traceback_excerpt && (
                      <details style={{ marginTop: '0.2rem' }}>
                        <summary style={{ fontSize: '0.72rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
                          View Diagnostic Traceback Excerpt
                        </summary>
                        <pre
                          style={{
                            margin: '0.35rem 0 0',
                            padding: '0.5rem',
                            background: '#050608',
                            borderRadius: 'var(--radius-xs)',
                            border: '1px solid var(--border-color)',
                            fontSize: '0.7rem',
                            fontFamily: 'var(--font-mono)',
                            color: 'var(--text-secondary)',
                            overflowX: 'auto',
                            maxHeight: '180px',
                            whiteSpace: 'pre-wrap',
                          }}
                        >
                          {obs.traceback_excerpt}
                        </pre>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                No failing observations recorded.
              </div>
            )}
          </Card>

          {/* Section 4: Evidence-Based Interpretation */}
          <Card
            title="4. Evidence-Based Interpretation"
            subtitle="Analysis of divergence between observed output and authorized test specifications"
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {explanation.evidence_based_interpretation
                ? explanation.evidence_based_interpretation.split('\n\n').map((para, i) => (
                    <p key={i} style={{ margin: 0 }}>
                      {para}
                    </p>
                  ))
                : 'No interpretation available.'}
            </div>
          </Card>

          {/* Section 5: Action Recommendation */}
          <Card
            title="5. Action Recommendation for Engineering Review"
            subtitle="Recommended next step based on verification analysis"
          >
            <div
              style={{
                padding: '1rem',
                backgroundColor:
                  explanation.recommendation?.action === 'RETURN_TO_COMPONENT_3'
                    ? 'rgba(239, 68, 68, 0.05)'
                    : 'rgba(16, 185, 129, 0.05)',
                border:
                  explanation.recommendation?.action === 'RETURN_TO_COMPONENT_3'
                    ? '1px solid rgba(239, 68, 68, 0.25)'
                    : '1px solid rgba(16, 185, 129, 0.25)',
                borderRadius: 'var(--radius-xs)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.65rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  {explanation.recommendation?.action === 'RETURN_TO_COMPONENT_3' ? (
                    <ArrowLeftCircle size={18} color="var(--status-failed)" />
                  ) : (
                    <CheckCircle2 size={18} color="var(--status-passed)" />
                  )}
                  {getRecommendationBadge(explanation.recommendation?.action)}
                </div>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Target: {explanation.recommendation?.target_audience || 'Human Engineer / Reviewer'}
                </span>
              </div>

              <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.55 }}>
                {explanation.recommendation?.reason}
              </p>
            </div>
          </Card>

          {/* Section 6: Suggested Next Investigations */}
          <Card
            title="6. Suggested Next Investigations"
            subtitle="Actionable, evidence-grounded pointers for resolving observed test divergences"
          >
            {explanation.suggested_investigations && explanation.suggested_investigations.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {explanation.suggested_investigations.map((step, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '0.6rem 0.8rem',
                      background: 'var(--bg-input)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 'var(--radius-xs)',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '0.65rem',
                      fontSize: '0.8125rem',
                      color: 'var(--text-secondary)',
                      lineHeight: 1.5,
                    }}
                  >
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: '18px',
                        height: '18px',
                        borderRadius: '50%',
                        backgroundColor: 'var(--primary-500)',
                        color: '#07090e',
                        fontWeight: 700,
                        fontSize: '0.6875rem',
                        flexShrink: 0,
                        marginTop: '1px',
                      }}
                    >
                      {idx + 1}
                    </span>
                    <span style={{ color: 'var(--text-primary)' }}>{step}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                No corrective investigations required.
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
