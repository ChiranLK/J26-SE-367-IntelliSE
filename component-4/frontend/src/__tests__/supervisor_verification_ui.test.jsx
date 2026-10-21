import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import VerificationRunsPage from '../pages/VerificationRunsPage';
import * as verificationApi from '../api/verificationApi';
import * as submissionApi from '../api/submissionApi';

const baseRun = {
  id: 'run-friday-demo',
  submission_id: 'sub-friday-demo',
  requested_test_types: ['unit', 'integration', 'performance'],
  triggered_by: 'manual',
  created_at: '2026-10-21T08:00:00Z',
  feedback_iterations: [],
  execution_telemetry: {
    docker_ready: true,
    duration_ms: 48.5,
    agent_reports: {
      unit: { status: 'PASSED', total_tests: 2, passed_tests: 2, failed_tests: 0, duration_ms: 12 },
      integration: { status: 'PASSED', total_interactions: 1, passed_interactions: 1, failed_interactions: 0, duration_ms: 18 },
      performance: {
        status: 'PASSED',
        metrics: { sample_size: 10, duration_ms: 18.5, latency_p95_ms: 3.2, threshold_latency_ms: 50, is_breached: false },
      },
    },
  },
};

function arrange(run, xai) {
  vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({ total: 1, items: [run] });
  vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(run);
  vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue({ eligible: run.status === 'FAILED', feedback: null });
  vi.spyOn(verificationApi, 'getXaiExplanation').mockResolvedValue(xai);
  vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue({ dispatch_allowed: false });
  vi.spyOn(verificationApi, 'getRepairAttempts').mockResolvedValue({ total: 0, items: [] });
  vi.spyOn(verificationApi, 'getConvergenceRiskReport').mockResolvedValue({ risk_level: 'LOW' });
  vi.spyOn(verificationApi, 'getDeploymentReadinessReport').mockResolvedValue({
    readiness_status: run.status === 'PASSED' ? 'READY' : 'BLOCKED',
    is_ready_for_deployment: run.status === 'PASSED',
  });
  vi.spyOn(verificationApi, 'getAiEngineStatus').mockResolvedValue({ ollama_connected: true });
  vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue({
    id: run.submission_id,
    filename: 'shop.py',
    language: 'python',
    code: 'def total():\n    return 42\n',
  });

  render(<BrowserRouter><VerificationRunsPage /></BrowserRouter>);
}

describe('Supervisor verification results UI', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('shows failed verification evidence while keeping advanced controls collapsed and XAI locked', async () => {
    const failedRun = {
      ...baseRun,
      status: 'FAILED',
      test_results: [{ name: 'test_checkout_total', test_type: 'unit', status: 'FAILED', duration_ms: 4, error_message: 'assert 40 == 42' }],
      defect_reports: [{
        defect_id: 'def-1',
        title: 'Checkout total mismatch',
        failed_test: 'test_checkout_total',
        failure_category: 'ASSERTION_FAILURE',
        defect_category: 'functional_bug',
        severity: 'HIGH',
        file_path: 'shop.py',
        line_number: 2,
        assertion_or_exception: 'assert 40 == 42',
      }],
      execution_telemetry: {
        ...baseRun.execution_telemetry,
        agent_reports: {
          ...baseRun.execution_telemetry.agent_reports,
          unit: { status: 'FAILED', total_tests: 2, passed_tests: 1, failed_tests: 1, duration_ms: 12 },
        },
      },
    };
    arrange(failedRun, { delivery_status: 'BLOCKED_VERIFICATION_FAILED' });

    fireEvent.click(await screen.findByRole('button', { name: /details/i }));

    expect(await screen.findByText('Verification Overview')).toBeInTheDocument();
    expect(screen.getAllByText('Unit Testing').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Integration Testing').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Performance Testing').length).toBeGreaterThan(0);
    expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    expect(screen.getByText(/Post-delivery XAI locked/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /View Software Explanation/i })).not.toBeInTheDocument();

    const component3Details = screen.getByText('Advanced — Component 3 Feedback Integration').closest('details');
    const governanceDetails = screen.getByText('Advanced — Governance & Research Diagnostics').closest('details');
    expect(component3Details).not.toHaveAttribute('open');
    expect(governanceDetails).not.toHaveAttribute('open');
  });

  it('separates a passed result from delivery and exposes XAI only for confirmed delivery', async () => {
    const passedRun = {
      ...baseRun,
      status: 'PASSED',
      test_results: [{ name: 'test_checkout_total', test_type: 'unit', status: 'PASSED', duration_ms: 4 }],
      defect_reports: [],
    };
    arrange(passedRun, {
      delivery_status: 'CONFIRMED_PRODUCTION_DELIVERY',
      post_delivery_explanation: { explanation_id: 'pdx-demo' },
    });

    fireEvent.click(await screen.findByRole('button', { name: /details/i }));

    expect(await screen.findByText('No defects detected by the executed tests.')).toBeInTheDocument();
    expect(screen.getByText('Verification Passed')).toBeInTheDocument();
    expect(screen.getByText(/Governance decision: READY/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /View Software Explanation/i })).toBeInTheDocument();
  });
});
