import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import ExpandableDiagnostic from '../components/common/ExpandableDiagnostic';
import VerificationRunsPage from '../pages/VerificationRunsPage';
import * as verificationApi from '../api/verificationApi';
import * as submissionApi from '../api/submissionApi';

const renderWithRouter = (ui) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

describe('Task 1 — Diagnostic Message Display Improvements', () => {
  it('displays short diagnostic message without any expansion toggle control', () => {
    const shortMessage = 'assert 5 == 5';
    render(<ExpandableDiagnostic text={shortMessage} maxLength={80} />);

    expect(screen.getByText(shortMessage)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /view details/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /hide details/i })).not.toBeInTheDocument();
  });

  it('renders fallback for empty or whitespace-only diagnostic message without controls', () => {
    const { rerender } = render(<ExpandableDiagnostic text={null} emptyFallback="None" />);
    expect(screen.getByText('None')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();

    rerender(<ExpandableDiagnostic text="" emptyFallback="—" />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();

    rerender(<ExpandableDiagnostic text="   " emptyFallback="No errors" />);
    expect(screen.getByText('No errors')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('displays concise preview for long message and expands to complete text on user interaction', () => {
    const longMessage =
      'AssertionError: Expected computed tax 15.0 to strictly match invoice balance 10.0 on test case test_invoice_calculation at line 84';
    render(<ExpandableDiagnostic text={longMessage} maxLength={60} variant="danger" />);

    // Collapsed state: preview with ellipsis and toggle button
    const toggleBtn = screen.getByRole('button', { name: /view details/i });
    expect(toggleBtn).toBeInTheDocument();
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');

    // Click to expand
    fireEvent.click(toggleBtn);

    // Expanded state: full original text in accessible region and hide button
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/hide details/i)).toBeInTheDocument();
    const fullPre = screen.getByRole('region', { name: /full diagnostic message/i });
    expect(fullPre).toBeInTheDocument();
    expect(fullPre).toHaveTextContent(longMessage);

    // Click to collapse back
    fireEvent.click(toggleBtn);
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText(/view details/i)).toBeInTheDocument();
  });

  it('preserves whitespace, indentation, and line breaks in multiline diagnostics', () => {
    const multilineTrace = [
      'Traceback (most recent call last):',
      '  File "test_billing.py", line 42, in test_tax_calculation',
      '    assert calculate_tax(100, 0.15) == 15.0',
      'AssertionError: assert 0.0 == 15.0',
    ].join('\n');

    render(<ExpandableDiagnostic text={multilineTrace} variant="danger" />);

    // Toggle button should be present for multiline content even if first line is short
    const toggleBtn = screen.getByRole('button', { name: /view details/i });
    expect(toggleBtn).toBeInTheDocument();

    // Expand to verify preserved formatting
    fireEvent.click(toggleBtn);

    const fullPre = screen.getByRole('region', { name: /full diagnostic message/i });
    expect(fullPre).toBeInTheDocument();
    expect(fullPre).toHaveStyle({ whiteSpace: 'pre-wrap' });
    expect(fullPre.textContent).toBe(multilineTrace);
  });

  it('handles long unbroken strings safely with break-word and overflow-wrap', () => {
    const unbrokenToken =
      'E_INVALID_STATE_LONG_HASH_TOKEN_ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890';
    const { container } = render(<ExpandableDiagnostic text={unbrokenToken} maxLength={50} />);

    // Verify preview has break-word styling
    const preview = container.querySelector('.diagnostic-preview');
    expect(preview).toHaveStyle({ wordBreak: 'break-word', overflowWrap: 'anywhere' });

    // Expand and verify full pre also has break-word styling
    const toggleBtn = screen.getByRole('button', { name: /view details/i });
    fireEvent.click(toggleBtn);

    const fullPre = screen.getByRole('region', { name: /full diagnostic message/i });
    expect(fullPre).toHaveStyle({ wordBreak: 'break-word', overflowWrap: 'anywhere' });
  });
});

describe('Task 2 — Forced Re-Verification Confirmation Workflow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockRun = {
    id: 'run-475a39076d8e',
    submission_id: 'sub-01057496e861',
    status: 'FAILED',
    test_results: [
      {
        test_id: 't1',
        name: 'test_total_with_tax',
        status: 'FAILED',
        duration_ms: 12.0,
        error_message: 'assert 100 == 110',
      },
    ],
    requested_test_types: ['UNIT'],
    triggered_by: 'manual',
    created_at: '2026-10-15T12:00:00Z',
  };

  const mockSubmission = {
    id: 'sub-01057496e861',
    code: 'def calculate_total(s, t): return s\n',
    language: 'python',
    filename: 'billing.py',
  };

  const mockReverifiedAttempt = {
    repair_id: 'rep-rev-99',
    id: 'rep-rev-99',
    original_run_id: 'run-475a39076d8e',
    original_submission_id: 'sub-01057496e861',
    feedback_iteration_id: 'iter-efbb1924c93f',
    corrected_submission_id: 'sub-corr-99',
    corrected_run_id: 'run-corr-run-99',
    status: 'REVERIFIED',
    repair_source: 'LOCAL_MANUAL',
    comparison: {
      original_run_id: 'run-475a39076d8e',
      corrected_run_id: 'run-corr-run-99',
      verdict: 'RESOLVED',
      original_defects_count: 1,
      resolved_defects_count: 1,
      remaining_defects_count: 0,
      resolution_rate: 1.0,
      test_comparisons: [
        {
          test_name: 'test_total_with_tax',
          original_status: 'FAILED',
          corrected_status: 'PASSED',
          resolution_status: 'RESOLVED',
          notes: 'Assertion resolved in corrected source code',
        },
      ],
    },
    created_at: '2026-10-15T12:00:00Z',
  };

  const setupMocks = (repairAttempts = [mockReverifiedAttempt]) => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue(mockSubmission);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue({ eligible: true });
    vi.spyOn(verificationApi, 'getXaiExplanation').mockResolvedValue({ summary: 'Notice' });
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue({ dispatch_allowed: false });
    vi.spyOn(verificationApi, 'getRepairAttempts').mockResolvedValue({
      total: repairAttempts.length,
      items: repairAttempts,
    });
  };

  it('opens forced re-verification confirmation modal with required information and no immediate API call', async () => {
    setupMocks();
    const reverifySpy = vi.spyOn(verificationApi, 'reverifyRepair').mockResolvedValue({});

    renderWithRouter(<VerificationRunsPage />);

    // Open detail modal
    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    // Locate "Run Again (Force)" button
    const forceBtn = await screen.findByRole('button', { name: /Run Again \(Force\)/i });
    expect(forceBtn).toBeInTheDocument();

    // Click "Run Again (Force)"
    fireEvent.click(forceBtn);

    // Verify confirmation modal opens
    expect(await screen.findByText('Confirm Re-Verification Execution')).toBeInTheDocument();

    // Verify required dialog communications
    expect(screen.getByText(/The corrected code will be tested again/i)).toBeInTheDocument();
    expect(screen.getByText(/A new execution will be started/i)).toBeInTheDocument();
    expect(screen.getByText(/Existing verification evidence and history will be preserved/i)).toBeInTheDocument();
    expect(screen.getByText(/The operation may take some time/i)).toBeInTheDocument();

    // Verify buttons
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run Verification Again' })).toBeInTheDocument();

    // Must NOT have called API upon opening the dialog
    expect(reverifySpy).not.toHaveBeenCalled();
  });

  it('cancels confirmation modal without sending any API request', async () => {
    setupMocks();
    const reverifySpy = vi.spyOn(verificationApi, 'reverifyRepair').mockResolvedValue({});

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    const forceBtn = await screen.findByRole('button', { name: /Run Again \(Force\)/i });
    fireEvent.click(forceBtn);

    expect(await screen.findByText('Confirm Re-Verification Execution')).toBeInTheDocument();

    // Click Cancel
    const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
    fireEvent.click(cancelBtn);

    // Modal should close
    await waitFor(() => {
      expect(screen.queryByText('Confirm Re-Verification Execution')).not.toBeInTheDocument();
    });

    // Zero API requests dispatched
    expect(reverifySpy).not.toHaveBeenCalled();
  });

  it('confirms re-verification and executes exactly one request with force_reverify: true', async () => {
    setupMocks();
    const reverifySpy = vi.spyOn(verificationApi, 'reverifyRepair').mockResolvedValue({
      repair_id: 'rep-rev-99',
      status: 'REVERIFIED',
      comparison: { verdict: 'RESOLVED' },
    });

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    const forceBtn = await screen.findByRole('button', { name: /Run Again \(Force\)/i });
    fireEvent.click(forceBtn);

    const confirmBtn = await screen.findByRole('button', { name: 'Run Verification Again' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(reverifySpy).toHaveBeenCalledTimes(1);
      expect(reverifySpy).toHaveBeenCalledWith('run-475a39076d8e', 'rep-rev-99', { force_reverify: true });
      expect(screen.getByText(/Re-verification completed\. Resolution comparison updated below\./i)).toBeInTheDocument();
    });
  });

  it('prevents duplicate submissions while re-verification request is in-flight', async () => {
    setupMocks();

    let resolveReverify;
    const pendingPromise = new Promise((resolve) => {
      resolveReverify = resolve;
    });

    const reverifySpy = vi.spyOn(verificationApi, 'reverifyRepair').mockReturnValue(pendingPromise);

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    const forceBtn = await screen.findByRole('button', { name: /Run Again \(Force\)/i });
    fireEvent.click(forceBtn);

    const confirmBtn = await screen.findByRole('button', { name: 'Run Verification Again' });
    const cancelBtn = screen.getByRole('button', { name: 'Cancel' });

    // Initial click
    fireEvent.click(confirmBtn);

    // Immediate subsequent clicks while in-flight
    fireEvent.click(confirmBtn);
    fireEvent.click(confirmBtn);

    // Confirm button and Cancel button should be disabled while pending
    expect(confirmBtn).toBeDisabled();
    expect(cancelBtn).toBeDisabled();

    // Only 1 API request should have been dispatched despite multiple clicks
    expect(reverifySpy).toHaveBeenCalledTimes(1);

    // Resolve in-flight promise
    resolveReverify({
      repair_id: 'rep-rev-99',
      status: 'REVERIFIED',
      comparison: { verdict: 'RESOLVED' },
    });

    await waitFor(() => {
      expect(screen.queryByText('Confirm Re-Verification Execution')).not.toBeInTheDocument();
    });
  });

  it('handles backend errors gracefully when re-verification fails', async () => {
    setupMocks();
    const reverifySpy = vi
      .spyOn(verificationApi, 'reverifyRepair')
      .mockRejectedValue(new Error('Container sandbox execution timed out after 30000ms'));

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    const forceBtn = await screen.findByRole('button', { name: /Run Again \(Force\)/i });
    fireEvent.click(forceBtn);

    const confirmBtn = await screen.findByRole('button', { name: 'Run Verification Again' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(reverifySpy).toHaveBeenCalledTimes(1);
      // Dialog closes and error banner displays backend error message
      expect(screen.getByText('Container sandbox execution timed out after 30000ms')).toBeInTheDocument();
    });
  });
});
