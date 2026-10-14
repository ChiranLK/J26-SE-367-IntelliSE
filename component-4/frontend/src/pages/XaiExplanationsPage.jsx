import React from 'react';
import {
  BrainCircuit,
  Info,
  Sparkles,
  HelpCircle,
  Cpu,
  ShieldCheck,
  CheckCircle2,
  FileText,
  Network,
  Bot,
} from 'lucide-react';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';

export default function XaiExplanationsPage() {
  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h1 className="page-title">
              <BrainCircuit size={22} color="var(--primary-300)" />
              <span>XAI Explanations</span>
              <Badge variant="primary" style={{ fontSize: '0.6875rem' }}>
                Phase 3 Reserved
              </Badge>
            </h1>
            <p className="page-description">
              Explainable AI diagnostics providing transparent, causal root-cause reasoning for verified code defects.
            </p>
          </div>
        </div>
      </div>

      {/* Honest Upcoming-Feature Notice */}
      <Alert
        type="info"
        title="Phase 3 Explainability Architecture"
      >
        Explainable AI model integration reserved for Phase 3. In Phase 3, an Ollama-backed local open-weights LLM will analyze test execution traces and synthesize causal reasoning graphs. No fabricated explanations are generated.
      </Alert>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.25rem', marginTop: '1.25rem' }}>
        
        {/* Core Principles */}
        <Card title="Explainability Framework Objectives" subtitle="Grounded, deterministic root-cause reasoning">
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
            When testing failures occur, raw compiler errors and assert diffs are often cryptic. The Component 4 XAI engine will bridge the comprehension gap:
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            <div style={{ padding: '0.65rem 0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <Network size={14} color="var(--primary-300)" />
                <span>1. Causal Root-Cause Graph</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                Traces the execution path from initial parameter input to the failing assertion, isolating the specific line of algorithmic divergence.
              </p>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <ShieldCheck size={14} color="var(--status-passed)" />
                <span>2. Verification Grounding</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                Every explanation is strictly grounded in actual test assertions and requirement specifications; the engine will never hallucinate non-existent failure causes.
              </p>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <FileText size={14} color="var(--accent-cyan)" />
                <span>3. Human-in-the-Loop Transparency</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                Engineers can inspect explanation confidence levels, review highlighted source ranges, and approve feedback before transmission to Component 3.
              </p>
            </div>
          </div>
        </Card>

        {/* Inference Architecture */}
        <Card title="Inference Architecture" subtitle="Local open-weights model deployment">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ padding: '0.75rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <Bot size={15} color="var(--primary-300)" />
                <span>Ollama Engine Isolation</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                To maintain complete research data sovereignty and proprietary codebase confidentiality, all inference will run against local quantized models (e.g. CodeLlama or Qwen2.5-Coder) without cloud API telemetry.
              </p>
            </div>

            <div style={{ padding: '0.75rem', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
              <div style={{ fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem' }}>
                <Sparkles size={14} color="var(--status-pending)" />
                <span>Target Explanation Payload</span>
              </div>
              <pre
                style={{
                  marginTop: '0.5rem',
                  padding: '0.625rem',
                  background: '#07080b',
                  borderRadius: 'var(--radius-xs)',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.72rem',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text-primary)',
                  overflowX: 'auto',
                }}
              >
{`{
  "defect_id": "def-9e81b2c4",
  "causal_explanation": "Loop termination boundary off-by-one error",
  "confidence_score": 0.94,
  "affected_line_span": [14, 18],
  "suggested_patch_strategy": "Change <= to <"
}`}
              </pre>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
