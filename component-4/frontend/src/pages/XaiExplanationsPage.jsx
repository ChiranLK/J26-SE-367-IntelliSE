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
  BookOpen,
  Layers,
  Sparkles,
  Send,
  User,
  Settings,
} from 'lucide-react';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import Alert from '../components/common/Alert';
import EmptyState from '../components/common/EmptyState';
import LoadingSkeleton from '../components/common/LoadingSkeleton';
import { getVerificationRuns, getXaiExplanation, confirmDelivery } from '../api/verificationApi';
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
  const [copiedSetupSnippet, setCopiedSetupSnippet] = useState(false);
  const [explanationLevel, setExplanationLevel] = useState('technical');
  const [confirmingDelivery, setConfirmingDelivery] = useState(false);

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

  const handleCopySetupSnippet = async () => {
    const text = explanation?.post_delivery_explanation?.setup_and_usage;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedSetupSnippet(true);
      setTimeout(() => setCopiedSetupSnippet(false), 2000);
    } catch {
      setCopiedSetupSnippet(false);
    }
  };

  const handleSimulateDelivery = async () => {
    if (!selectedRunId) return;
    setConfirmingDelivery(true);
    try {
      await confirmDelivery(selectedRunId, {
        is_simulation: true,
        notes: 'Simulated downstream delivery confirmed via XAI Console',
      });
      const data = await getXaiExplanation(selectedRunId);
      setExplanation(data);
    } catch (err) {
      setError(`Delivery confirmation failed: ${err.message}`);
    } finally {
      setConfirmingDelivery(false);
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
              <span>Post-Delivery Software Explanations</span>
              <Badge variant="secondary" style={{ fontSize: '0.6875rem' }}>
                Target: Reviewer
              </Badge>
            </h1>
            <p className="page-description">
              Beginner and technical explanations of verified software, available only after an authorized delivery event.
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
            <strong style={{ color: 'var(--text-primary)' }}>Strict post-delivery boundary:</strong>{' '}
            Failed verification exposes technical test evidence in the verification workflow only. This console explains delivered software, not defects.
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
                {explanation.delivery_status && (
                  <Badge
                    variant={
                      explanation.delivery_status === 'CONFIRMED_PRODUCTION_DELIVERY'
                        ? 'success'
                        : explanation.delivery_status === 'SIMULATED_DELIVERY'
                        ? 'warning'
                        : explanation.delivery_status.startsWith('BLOCKED_')
                        ? 'danger'
                        : 'secondary'
                    }
                    style={{ fontSize: '0.6875rem' }}
                  >
                    {explanation.delivery_status === 'SIMULATED_DELIVERY'
                      ? 'SIMULATED DELIVERY (DEV MODE)'
                      : explanation.delivery_status.replace(/_/g, ' ')}
                  </Badge>
                )}
                {explanation.eligible ? (
                  <Badge variant="danger" dot style={{ fontSize: '0.6875rem' }}>
                    Eligible for Corrective Explanation
                  </Badge>
                ) : (
                  <Badge variant="secondary" style={{ fontSize: '0.6875rem' }}>
                    Post-Delivery XAI Locked
                  </Badge>
                )}
                <Badge variant="secondary" style={{ fontSize: '0.6875rem' }}>
                  Schema v{explanation.schema_version}
                </Badge>
              </div>
            </div>

            {/* Delivery Gate Status Banners */}
            {explanation.delivery_status === 'SIMULATED_DELIVERY' && (
              <div
                style={{
                  padding: '0.6rem 0.85rem',
                  backgroundColor: 'rgba(245, 158, 11, 0.08)',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                  borderRadius: 'var(--radius-xs)',
                  fontSize: '0.78rem',
                  color: 'var(--text-secondary)',
                }}
              >
                <strong style={{ color: '#f59e0b' }}>Simulated Delivery (Development Mode):</strong>{' '}
                A server-authorized development simulation confirmed delivery. The software-understanding package below is a development-only preview and is not evidence of production delivery.
              </div>
            )}
            {explanation.delivery_status === 'CONFIRMED_PRODUCTION_DELIVERY' && (
              <div
                style={{
                  padding: '0.6rem 0.85rem',
                  backgroundColor: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  borderRadius: 'var(--radius-xs)',
                  fontSize: '0.78rem',
                  color: 'var(--text-secondary)',
                }}
              >
                <strong style={{ color: '#10b981' }}>Authenticated Production Delivery:</strong>{' '}
                Downstream delivery confirmed by authenticated delivery service with verified SHA-256 integrity and deployment governance sign-off.
              </div>
            )}
            {explanation.delivery_status && explanation.delivery_status.startsWith('BLOCKED_') && explanation.delivery_status !== 'BLOCKED_VERIFICATION_FAILED' && (
              <div
                style={{
                  padding: '0.6rem 0.85rem',
                  backgroundColor: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.25)',
                  borderRadius: 'var(--radius-xs)',
                  fontSize: '0.78rem',
                  color: 'var(--text-secondary)',
                }}
              >
                <strong style={{ color: '#ef4444' }}>Delivery Gate Blocked ({explanation.delivery_status}):</strong>{' '}
                {explanation.eligibility_reason}
              </div>
            )}

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

          {/* Pending Delivery Confirmation Gate Card */}
          {explanation.delivery_status === 'PENDING_DELIVERY_CONFIRMATION' && (
            <Card
              title="Awaiting Downstream Delivery Confirmation"
              subtitle="Verification tests and deployment governance have cleared; delivery confirmation is required to unlock post-delivery code understanding"
              action={
                <Button
                  variant="primary"
                  size="sm"
                  icon={CheckCircle2}
                  onClick={handleSimulateDelivery}
                  loading={confirmingDelivery}
                >
                  Authorize Dev Delivery Simulation
                </Button>
              }
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                <p style={{ margin: 0 }}>
                  This artifact has <strong>passed all authorized test specifications</strong> and satisfied release governance policies.
                  In accordance with the post-delivery XAI architecture, human-facing code understanding explanations are published exclusively
                  after confirmed deployment to prevent generating premature explanations for unreleased artifacts.
                </p>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Click <em>"Authorize Dev Delivery Simulation"</em> to record a clearly labeled non-production delivery event and synthesize the software-understanding package.
                </div>
              </div>
            </Card>
          )}

          {/* Blocked Verification Warning */}
          {explanation.delivery_status === 'BLOCKED_VERIFICATION_FAILED' && (
            <div
              style={{
                padding: '0.85rem 1rem',
                backgroundColor: 'rgba(239, 68, 68, 0.06)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.82rem',
                color: 'var(--text-secondary)',
                lineHeight: 1.5,
              }}
            >
              <strong style={{ color: 'var(--status-failed)' }}>Internal Repair Mode Active:</strong>{' '}
              User-facing code explanations are withheld during intermediate repair cycles.
              Structured technical feedback has been routed to Component 3 for automated correction.
              Audit defect records remain accessible in the <strong>Defects</strong> tab.
            </div>
          )}

          {/* Post-Delivery Software Understanding Package (Unlocked upon Confirmed Delivery) */}
          {explanation.post_delivery_explanation && (() => {
            const pdx = explanation.post_delivery_explanation;
            const prov = pdx.inference_provenance || explanation.inference_provenance;
            return (
              <Card
                title="Post-Delivery Code Understanding Console"
                subtitle={`Verified Software: ${pdx.software_name} — All ${pdx.verified_test_count} tests passed`}
                action={
                  <div style={{ display: 'flex', gap: '0.4rem' }}>
                    <Button
                      variant={explanationLevel === 'beginner' ? 'primary' : 'outline'}
                      size="sm"
                      icon={User}
                      onClick={() => setExplanationLevel('beginner')}
                      style={{ fontSize: '0.75rem', height: '28px' }}
                    >
                      Beginner View
                    </Button>
                    <Button
                      variant={explanationLevel === 'technical' ? 'primary' : 'outline'}
                      size="sm"
                      icon={FileCode2}
                      onClick={() => setExplanationLevel('technical')}
                      style={{ fontSize: '0.75rem', height: '28px' }}
                    >
                      Technical View
                    </Button>
                  </div>
                }
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  {/* Provenance and Integrity Banner */}
                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '0.75rem',
                      padding: '0.65rem 0.85rem',
                      background: 'rgba(255, 255, 255, 0.02)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 'var(--radius-xs)',
                      fontSize: '0.75rem',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                      {prov?.genuine_inference ? (
                        <Badge variant="success">
                          <Sparkles size={12} style={{ marginRight: '0.25rem', verticalAlign: 'middle' }} />
                          Hybrid Synthesis: Ollama Narrative ({prov.model || 'qwen2.5-coder:3b'}) + Verified AST Invariants
                        </Badge>
                      ) : prov?.fallback_used ? (
                        <Badge variant="warning">
                          <FileCode2 size={12} style={{ marginRight: '0.25rem', verticalAlign: 'middle' }} />
                          Deterministic AST Fallback (Ollama Offline)
                        </Badge>
                      ) : (
                        <Badge variant="neutral">
                          <FileCode2 size={12} style={{ marginRight: '0.25rem', verticalAlign: 'middle' }} />
                          Deterministic AST Synthesis
                        </Badge>
                      )}
                      <span style={{ color: 'var(--text-secondary)' }}>
                        {pdx.evidence_manifest?.analyzed_source_files?.length || 1} module(s) · {pdx.evidence_manifest?.analyzed_line_count || 0} LOC · {pdx.verified_test_count} tests verified
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>
                        {prov?.genuine_inference ? 'Narrative: Ollama + AST validation' : 'Narrative: Deterministic AST'} · Invariants: Verified artifact
                      </span>
                      {prov?.duration_ms && (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem' }}>
                          Inference latency: {(prov.duration_ms / 1000).toFixed(1)}s
                        </span>
                      )}
                    </div>
                  </div>

                  {explanationLevel === 'beginner' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      <div style={{ padding: '0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                        <h4 style={{ margin: '0 0 0.4rem', fontSize: '0.875rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <BookOpen size={15} /> Software Purpose
                        </h4>
                        <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.6 }}>
                          {pdx.beginner_level.overview}
                        </p>
                      </div>

                      <div style={{ padding: '0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                        <h4 style={{ margin: '0 0 0.4rem', fontSize: '0.875rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <Cpu size={15} /> What It Does
                        </h4>
                        <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.6 }}>
                          {pdx.beginner_level.what_it_does}
                        </p>
                      </div>

                      {pdx.beginner_level.key_capabilities && pdx.beginner_level.key_capabilities.length > 0 && (
                        <div style={{ padding: '0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                          <h4 style={{ margin: '0 0 0.6rem', fontSize: '0.875rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <ShieldCheck size={15} /> Key Verified Capabilities
                          </h4>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                            {pdx.beginner_level.key_capabilities.map((cap, i) => (
                              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                                <CheckCircle2 size={15} style={{ color: 'var(--status-passed)', flexShrink: 0, marginTop: '2px' }} />
                                <span>{cap}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {pdx.beginner_level.realistic_example && (
                        <div style={{ padding: '0.85rem', background: 'rgba(99, 102, 241, 0.04)', border: '1px solid rgba(99, 102, 241, 0.2)', borderRadius: 'var(--radius-xs)' }}>
                          <h4 style={{ margin: '0 0 0.4rem', fontSize: '0.875rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <FileCode2 size={15} /> Practical Usage Scenario (Illustrative — Grounded in Delivered Signatures)
                          </h4>
                          <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.6, overflowWrap: 'anywhere', whiteSpace: 'pre-line' }}>
                            {pdx.beginner_level.realistic_example}
                          </p>
                        </div>
                      )}

                      <div style={{ padding: '0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                        <h4 style={{ margin: '0 0 0.4rem', fontSize: '0.875rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <ArrowRightCircle size={15} /> How to Use
                        </h4>
                        <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.6 }}>
                          {pdx.beginner_level.how_to_use}
                        </p>
                      </div>

                      {pdx.beginner_level.safety_and_boundaries && (
                        <div style={{ padding: '0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                          <h4 style={{ margin: '0 0 0.4rem', fontSize: '0.875rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <ShieldCheck size={15} /> Safety Guardrails & Verified Limits
                          </h4>
                          <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.6 }}>
                            {pdx.beginner_level.safety_and_boundaries}
                          </p>
                        </div>
                      )}

                      {pdx.beginner_level.test_confidence && (
                        <div style={{ padding: '0.85rem', background: 'rgba(16, 185, 129, 0.06)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: 'var(--radius-xs)' }}>
                          <h4 style={{ margin: '0 0 0.4rem', fontSize: '0.875rem', color: 'var(--status-passed)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <CheckCircle2 size={15} /> What the Tests Tell Us
                          </h4>
                          <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.6 }}>
                            {pdx.beginner_level.test_confidence}
                          </p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                      {/* Dimension 1: Purpose & Overview */}
                      <div>
                        <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <BookOpen size={16} /> 1. Software Overview & Engineering Scope
                        </h4>
                        <div style={{ padding: '0.85rem 1rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                          <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.65, whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>
                            {pdx.software_overview}
                          </p>
                        </div>
                      </div>

                      {/* Dimension 2: Architecture & Modules */}
                      <div>
                        <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <Layers size={16} /> 2. Architecture & Module Decomposition
                        </h4>
                        <div style={{ padding: '0.85rem 1rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)', marginBottom: '0.75rem' }}>
                          <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>
                            {pdx.architecture_explanation}
                          </p>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          {pdx.module_responsibilities?.map((m, idx) => (
                            <div key={idx} style={{ padding: '0.7rem 0.9rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.35rem' }}>
                                <code style={{ color: 'var(--primary-300)', fontSize: '0.84rem', fontWeight: 600 }}>{m.file_path}</code>
                                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                                  <Badge variant="neutral">{m.line_count} LOC</Badge>
                                </div>
                              </div>
                              <div style={{ fontSize: '0.8rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                                {m.primary_responsibility}
                              </div>
                              {m.exported_symbols && m.exported_symbols.length > 0 && (
                                <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.4rem', alignItems: 'center' }}>
                                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Exposed symbols:</span>
                                  {m.exported_symbols.map((sym, sIdx) => (
                                    <code key={sIdx} style={{ fontSize: '0.72rem', background: 'rgba(255, 255, 255, 0.04)', padding: '1px 5px', borderRadius: '3px', color: 'var(--text-secondary)' }}>
                                      {sym}
                                    </code>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Dimension 3: Important Functions & Behavioral Contracts */}
                      <div>
                        <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <FileCode2 size={16} /> 3. Important Functions & Behavioral Contracts
                        </h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                          {pdx.important_functions?.map((fn, idx) => (
                            <div key={idx} style={{ padding: '0.85rem 1rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.4rem' }}>
                                <code style={{ fontSize: '0.86rem', color: '#818cf8', fontWeight: 600, overflowWrap: 'anywhere' }}>{fn.signature}</code>
                                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                                  {fn.return_type && (
                                    <Badge variant="outline" style={{ fontSize: '0.7rem' }}>returns {fn.return_type}</Badge>
                                  )}
                                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                    Line {fn.line_number}–{fn.end_line_number || fn.line_number}
                                  </span>
                                </div>
                              </div>
                              <p style={{ margin: '0 0 0.5rem', fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.55 }}>
                                {fn.technical_behavior}
                              </p>
                              {fn.parameters && fn.parameters.length > 0 && (
                                <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.4rem', alignItems: 'center' }}>
                                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Parameters:</span>
                                  {fn.parameters.map((p, pIdx) => (
                                    <span key={pIdx} style={{ fontSize: '0.72rem', background: 'rgba(255, 255, 255, 0.04)', padding: '2px 6px', borderRadius: '3px', color: 'var(--text-secondary)' }}>
                                      <code>{p.name}</code>: {p.type_annotation || 'Any'}{p.default_value !== undefined && p.default_value !== null ? ` = ${p.default_value}` : ''}
                                    </span>
                                  ))}
                                </div>
                              )}
                              {fn.verified_by_tests && fn.verified_by_tests.length > 0 && (
                                <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.4rem', alignItems: 'center' }}>
                                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Verified by:</span>
                                  {fn.verified_by_tests.map((tName, tIdx) => (
                                    <Badge key={tIdx} variant="success" style={{ fontSize: '0.68rem', padding: '1px 6px' }}>{tName}</Badge>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Dimension 4: Callable Interfaces & Data Flow */}
                      <div>
                        <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <ArrowRightCircle size={16} /> 4. Callable Interfaces & Data Flow
                        </h4>
                        <div style={{ padding: '0.85rem 1rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                          <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.6, whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>
                            {pdx.api_and_data_flow}
                          </p>
                        </div>
                      </div>

                      {/* Dimension 5: Verified Behavior & Test Evidence */}
                      <div>
                        <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <CheckCircle2 size={16} /> 5. Verified Behavior & Test Evidence
                        </h4>
                        <p style={{ margin: '0 0 0.6rem', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                          Passing tests support their exercised scenarios; they do not prove complete correctness.
                        </p>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          {pdx.test_evidence?.map((item, idx) => (
                            <div key={item.test_id || idx} style={{ padding: '0.7rem 0.9rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.3rem' }}>
                                <code style={{ overflowWrap: 'anywhere', fontSize: '0.82rem', fontWeight: 600 }}>{item.test_name}</code>
                                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                                  {item.duration_ms !== null && item.duration_ms !== undefined && (
                                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{Number(item.duration_ms).toFixed(1)} ms</span>
                                  )}
                                  <Badge variant="success">{item.test_type} · {item.status}</Badge>
                                </div>
                              </div>
                              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                                <strong style={{ color: 'var(--text-primary)' }}>Demonstrated scope:</strong> {item.demonstrated_scope}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Dimension 6: Measured Performance & SLA Evidence */}
                      <div>
                        <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <Clock size={16} /> 6. Measured Performance & SLA Evidence
                        </h4>
                        <div style={{ padding: '0.85rem 1rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                          {pdx.measured_sla?.available ? (
                            <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
                                <span>Latency p95: <strong style={{ color: 'var(--text-primary)' }}>{Number(pdx.measured_sla.latency_p95_ms).toFixed(2)} ms</strong></span>
                                <span>Threshold: <strong style={{ color: 'var(--text-primary)' }}>{Number(pdx.measured_sla.threshold_latency_ms).toFixed(2)} ms</strong></span>
                                {pdx.measured_sla.sample_size && <span>Sample size: <strong style={{ color: 'var(--text-primary)' }}>{pdx.measured_sla.sample_size}</strong></span>}
                                <Badge variant={pdx.measured_sla.verdict === 'PASSED' ? 'success' : 'danger'}>{pdx.measured_sla.verdict}</Badge>
                              </div>
                              <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.76rem' }}>
                                {pdx.measured_sla.environment_note}
                              </p>
                            </div>
                          ) : (
                            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                              {pdx.measured_sla?.environment_note || 'No measured SLA evidence is available.'}
                            </p>
                          )}
                        </div>
                      </div>

                      {/* Dimension 7: Algorithms & Observable Design Decisions */}
                      <div>
                        <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <Cpu size={16} /> 7. Observable Design Decisions & Algorithmic Patterns
                        </h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          {pdx.algorithms_and_design_decisions?.map((item, idx) => (
                            <div key={idx} style={{ padding: '0.75rem 0.9rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '0.25rem' }}>
                                <strong style={{ fontSize: '0.82rem', color: 'var(--text-primary)' }}>{item.topic}: {item.decision}</strong>
                                {item.traceability_seam && (
                                  <Badge variant="neutral" style={{ fontSize: '0.68rem' }}>{item.traceability_seam}</Badge>
                                )}
                              </div>
                              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                                {item.rationale}
                              </div>
                              <div style={{ marginTop: '0.3rem', fontSize: '0.74rem', color: 'var(--text-muted)', overflowWrap: 'anywhere' }}>
                                <strong>Code evidence:</strong> {item.evidence_in_code}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Dimension 8: Assumptions, Limitations & Verification Scope */}
                      <div>
                        <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <AlertTriangle size={16} /> 8. Assumptions, Limitations & Verification Scope
                        </h4>
                        <div style={{ padding: '0.85rem 1rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border-color)' }}>
                          <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.6, whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>
                            {pdx.limitations_and_verification_scope}
                          </p>
                        </div>
                      </div>

                      {/* Supporting Setup & Usage */}
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <h4 style={{ margin: 0, fontSize: '0.9rem', color: 'var(--primary-400)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <FileCode2 size={16} /> Supporting Setup & Usage Guide
                          </h4>
                          <Button
                            variant="outline"
                            size="sm"
                            icon={copiedSetupSnippet ? Check : Copy}
                            onClick={handleCopySetupSnippet}
                            style={{ height: '24px', fontSize: '0.6875rem' }}
                          >
                            {copiedSetupSnippet ? 'Copied' : 'Copy Code Snippet'}
                          </Button>
                        </div>
                        <pre style={{ margin: 0, padding: '0.85rem 1rem', background: '#050608', borderRadius: 'var(--radius-xs)', fontSize: '0.75rem', color: 'var(--text-secondary)', overflowX: 'auto', border: '1px solid var(--border-color)', lineHeight: 1.5 }}>
                          {pdx.setup_and_usage}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            );
          })()}

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
