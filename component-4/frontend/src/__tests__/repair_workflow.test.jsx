import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import VerificationRunsPage from '../pages/VerificationRunsPage';
import * as verificationApi from '../api/verificationApi';
import * as submissionApi from '../api/submissionApi';

const renderWithRouter = (ui) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

describe('Repair Ingestion & Re-Verification UI Workflow', () => {
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
      {
        test_id: 't2',
        name: 'test_total_without_tax',
        status: 'FAILED',
        duration_ms: 8.0,
        error_message: 'assert 0 == 50',
      },
    ],
    requested_test_types: ['UNIT'],
    triggered_by: 'manual',
    created_at: '2026-10-15T12:00:00Z',
    defect_reports: [
      {
        defect_id: 'def-01',
        title: 'Tax calculation failure',
        failed_test: 'test_total_with_tax',
      },
    ],
    feedback_iterations: [
      {
        iteration_id: 'iter-efbb1924c93f',
        iteration_number: 1,
        approval_status: 'APPROVED',
        approved_by: 'lead_engineer',
      },
    ],
  };

  const mockSubmission = {
    id: 'sub-01057496e861',
    code: 'def calculate_total(s, t): return s\n',
    language: 'python',
    filename: 'billing.py',
  };

  it('renders the Corrected Code Re-Verification section in details modal', async () => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue(mockSubmission);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue({
      eligible: true,
      reason: 'Empirical defects recorded',
      feedback: { feedback_id: 'fb-01', affected_files: ['billing.py'] },
    });
    vi.spyOn(verificationApi, 'getXaiExplanation').mockResolvedValue({
      summary: 'Fix tax formula in calculate_total',
    });
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue({
      dispatch_allowed: false,
    });
    vi.spyOn(verificationApi, 'getRepairAttempts').mockResolvedValue({
      total: 0,
      items: [],
    });

    renderWithRouter(<VerificationRunsPage />);

    // Open detail modal
    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    await waitFor(() => {
      expect(screen.getByText(/Corrected Code Re-Verification/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Submit Corrected Code/i })).toBeInTheDocument();
    });
  });

  it('allows user to enter corrected code and submit a local repair', async () => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue(mockSubmission);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue({ eligible: true });
    vi.spyOn(verificationApi, 'getXaiExplanation').mockResolvedValue({ summary: 'Fix needed' });
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue({ dispatch_allowed: false });
    vi.spyOn(verificationApi, 'getRepairAttempts').mockResolvedValue({
      total: 0,
      items: [],
    });

    const ingestSpy = vi.spyOn(verificationApi, 'ingestRepairResponse').mockResolvedValue({
      repair_id: 'rep-new-01',
      original_run_id: 'run-475a39076d8e',
      original_submission_id: 'sub-01057496e861',
      feedback_iteration_id: 'iter-efbb1924c93f',
      corrected_submission_id: 'sub-new-02',
      status: 'INGESTED',
      corrected_filename: 'billing.py',
      created_at: '2026-10-15T12:30:00Z',
    });

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    const submitCodeBtn = await screen.findByRole('button', { name: /Submit Corrected Code/i });
    expect(submitCodeBtn).toBeInTheDocument();

    // Click Submit Corrected Code to open form
    fireEvent.click(submitCodeBtn);

    const codeTextarea = screen.getByPlaceholderText(/Paste corrected Python implementation here/i);
    expect(codeTextarea).toBeInTheDocument();

    fireEvent.change(codeTextarea, {
      target: { value: 'def calculate_total(s, t):\n    return s * (1 + t)\n' },
    });

    // Click Ingest Corrected Code
    const submitBtn = screen.getByRole('button', { name: /Ingest Corrected Code/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(ingestSpy).toHaveBeenCalledWith('run-475a39076d8e', expect.objectContaining({
        corrected_code: 'def calculate_total(s, t):\n    return s * (1 + t)\n',
        filename: 'billing.py',
      }));
    });
  });

  it('renders re-verified repair attempt with defect resolution verdict and comparison table', async () => {
    const mockReverifiedAttempt = {
      repair_id: 'rep-resolved-01',
      original_run_id: 'run-475a39076d8e',
      original_submission_id: 'sub-01057496e861',
      feedback_iteration_id: 'iter-efbb1924c93f',
      corrected_submission_id: 'sub-corr-99',
      corrected_run_id: 'run-corr-100',
      status: 'REVERIFIED',
      repair_source: 'LOCAL_MANUAL',
      created_at: '2026-10-15T12:30:00Z',
      comparison: {
        original_run_id: 'run-475a39076d8e',
        corrected_run_id: 'run-corr-100',
        verdict: 'FULLY_RESOLVED',
        original_defects_count: 2,
        resolved_defects_count: 2,
        remaining_defects_count: 0,
        new_defects_count: 0,
        resolution_rate: 100.0,
        test_comparisons: [
          {
            test_name: 'test_total_with_tax',
            original_status: 'FAILED',
            corrected_status: 'PASSED',
            resolution_status: 'RESOLVED',
            notes: 'Previously failing test now demonstrably passes.',
          },
          {
            test_name: 'test_total_without_tax',
            original_status: 'FAILED',
            corrected_status: 'PASSED',
            resolution_status: 'RESOLVED',
            notes: 'Previously failing test now demonstrably passes.',
          },
        ],
      },
    };

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue(mockSubmission);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue({ eligible: true });
    vi.spyOn(verificationApi, 'getXaiExplanation').mockResolvedValue({ summary: 'Resolved' });
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue({ dispatch_allowed: false });
    vi.spyOn(verificationApi, 'getRepairAttempts').mockResolvedValue({
      total: 1,
      items: [mockReverifiedAttempt],
    });

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    await waitFor(() => {
      expect(screen.getByText('rep-resolved-01')).toBeInTheDocument();
      expect(screen.getByText(/All Defects Resolved/i)).toBeInTheDocument();
      expect(screen.getByText('Resolution Rate: 100%')).toBeInTheDocument();
      expect(screen.getAllByText('test_total_with_tax').length).toBeGreaterThan(0);
      expect(screen.getAllByText('test_total_without_tax').length).toBeGreaterThan(0);
      expect(screen.getByText('Run Again (Force)')).toBeInTheDocument();
    });
  });

  it('renders BLOCKED state with warning and guards action when test suite is missing', async () => {
    const mockBlockedAttempt = {
      repair_id: 'rep-blocked-01',
      original_run_id: 'run-475a39076d8e',
      original_submission_id: 'sub-01057496e861',
      feedback_iteration_id: 'iter-efbb1924c93f',
      corrected_submission_id: 'sub-corr-02',
      corrected_run_id: null,
      status: 'BLOCKED',
      repair_source: 'LOCAL_MANUAL',
      notes: 'Original trusted test suite is unavailable; cannot safely execute re-verification.',
      created_at: '2026-10-15T12:30:00Z',
      comparison: {
        original_run_id: 'run-475a39076d8e',
        corrected_run_id: null,
        verdict: 'INCONCLUSIVE',
        original_defects_count: 2,
        resolved_defects_count: 0,
        remaining_defects_count: 0,
        new_defects_count: 0,
        resolution_rate: 0.0,
        notes: 'Original trusted test suite is unavailable; cannot safely execute re-verification.',
        test_comparisons: [],
        defect_comparisons: [],
      },
    };

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue(mockSubmission);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue({ eligible: true });
    vi.spyOn(verificationApi, 'getXaiExplanation').mockResolvedValue({ summary: 'Blocked test' });
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue({ dispatch_allowed: false });
    vi.spyOn(verificationApi, 'getRepairAttempts').mockResolvedValue({
      total: 1,
      items: [mockBlockedAttempt],
    });

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    await waitFor(() => {
      expect(screen.getByText('rep-blocked-01')).toBeInTheDocument();
      // Should show BLOCKED badge
      expect(screen.getAllByText('BLOCKED').length).toBeGreaterThan(0);
      // Should show disabled button preventing unsafe repeat execution
      const blockedBtn = screen.getByRole('button', { name: /Blocked \(Test Suite Required\)/i });
      expect(blockedBtn).toBeInTheDocument();
      expect(blockedBtn).toBeDisabled();
      // Should show informative notice explaining why re-verification is blocked
      expect(screen.getByText(/Verification Blocked: Authorized Test Suite Unavailable/i)).toBeInTheDocument();
      expect(screen.getByText(/Resolution Rate: Inconclusive/i)).toBeInTheDocument();
    });
  });

  it('correctly handles re-verification call that returns BLOCKED without showing green success', async () => {
    const mockIngestedAttempt = {
      repair_id: 'rep-ingested-01',
      original_run_id: 'run-475a39076d8e',
      original_submission_id: 'sub-01057496e861',
      feedback_iteration_id: 'iter-efbb1924c93f',
      corrected_submission_id: 'sub-corr-03',
      corrected_run_id: null,
      status: 'INGESTED',
      repair_source: 'LOCAL_MANUAL',
      created_at: '2026-10-15T12:30:00Z',
    };

    const mockBlockedResult = {
      repair_id: 'rep-ingested-01',
      original_run_id: 'run-475a39076d8e',
      original_submission_id: 'sub-01057496e861',
      feedback_iteration_id: 'iter-efbb1924c93f',
      corrected_submission_id: 'sub-corr-03',
      corrected_run_id: null,
      status: 'BLOCKED',
      repair_source: 'LOCAL_MANUAL',
      notes: 'Original trusted test suite is unavailable; cannot safely execute re-verification.',
      comparison: {
        original_run_id: 'run-475a39076d8e',
        corrected_run_id: null,
        verdict: 'INCONCLUSIVE',
        original_defects_count: 2,
        resolved_defects_count: 0,
        remaining_defects_count: 0,
        resolution_rate: 0.0,
        notes: 'Original trusted test suite is unavailable; cannot safely execute re-verification.',
      },
    };

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
      total: 1,
      items: [mockIngestedAttempt],
    });

    const reverifySpy = vi.spyOn(verificationApi, 'reverifyRepair').mockResolvedValue(mockBlockedResult);

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    const runAgainBtn = await screen.findByRole('button', { name: /Run Verification Again/i });
    fireEvent.click(runAgainBtn);

    await waitFor(() => {
      expect(reverifySpy).toHaveBeenCalledWith('run-475a39076d8e', 'rep-ingested-01', { force_reverify: false });
      // Must NOT display generic green success message
      expect(screen.queryByText(/Re-verification completed\. Resolution comparison updated below\./i)).not.toBeInTheDocument();
      // Must display the warning message explaining the blocked status
      expect(screen.getByText(/Original trusted test suite is unavailable; cannot safely execute re-verification\./i)).toBeInTheDocument();
    });
  });
});
