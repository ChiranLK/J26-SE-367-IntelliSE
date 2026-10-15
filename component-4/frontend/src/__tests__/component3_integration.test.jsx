import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import VerificationRunsPage from '../pages/VerificationRunsPage';
import FeedbackHistoryPage from '../pages/FeedbackHistoryPage';
import * as verificationApi from '../api/verificationApi';
import * as submissionApi from '../api/submissionApi';

const renderWithRouter = (ui) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

describe('Repair Feedback Integration UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockC3Status = {
    configured: true,
    enabled: false,
    base_url: 'http://127.0.0.1:8000',
    endpoint: '/api/v1/correction-feedback',
    contract_status: 'UNDER_DEVELOPMENT',
    dispatch_allowed: false,
    reason: 'Component 3 code correction contract is currently under development.',
  };

  const mockRun = {
    id: 'run-c3-integration-01',
    submission_id: 'sub-c3-calc',
    status: 'FAILED',
    test_results: [
      {
        test_id: 'test_tax',
        name: 'test_tax',
        status: 'FAILED',
        duration_ms: 10.0,
        error_message: 'assert 8.0 == 108.0',
      },
    ],
    requested_test_types: ['UNIT'],
    triggered_by: 'manual',
    created_at: '2026-10-15T12:00:00Z',
    defect_reports: [
      {
        defect_id: 'def-1',
        title: 'Tax assertion failure',
        failed_test: 'test_tax',
        failure_category: 'ASSERTION_FAILURE',
        severity: 'HIGH',
        file_path: 'calc.py',
        line_number: 5,
        expected_value: '108.0',
        actual_value: '8.0',
        assertion_or_exception: 'assert 8.0 == 108.0',
      },
    ],
    feedback_iterations: [],
  };

  const mockFeedbackPreview = {
    eligible: true,
    reason: 'Failed with 1 application defect.',
    feedback: {
      feedback_id: 'fb-c3-test',
      verification_run_id: 'run-c3-integration-01',
      submission_id: 'sub-c3-calc',
      verification_status: 'FAILED',
      affected_files: ['calc.py'],
      failed_tests: ['test_tax'],
      failed_assertions: ['assert 8.0 == 108.0'],
      value_comparisons: [
        {
          test_name: 'test_tax',
          defect_id: 'def-1',
          expected: '108.0',
          observed: '8.0',
          assertion: 'assert 8.0 == 108.0',
        },
      ],
      error_logs: ['assert 8.0 == 108.0'],
      defect_ids: ['def-1'],
      evidence_references: { total_tests: 1, failed_tests_count: 1 },
      generated_at: '2026-10-15T12:00:00Z',
      schema_version: '1.0',
    },
  };

  it('renders repair integration status banner and approval button inside details modal', async () => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue(mockFeedbackPreview);
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue(mockC3Status);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue({
      id: 'sub-c3-calc',
      filename: 'calc.py',
      language: 'PYTHON',
    });

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    // Verify Repair Integration Status
    expect(await screen.findByText(/Repair Integration Status:/i)).toBeInTheDocument();
    expect(screen.getByText(/Contract: UNDER_DEVELOPMENT/i)).toBeInTheDocument();
    expect(screen.getByText(/Delivery: Disabled \(Safety Lock\)/i)).toBeInTheDocument();

    // Verify Human Review & Dispatch Authorization header & Approve button
    expect(screen.getByText(/Human Review & Dispatch Authorization/i)).toBeInTheDocument();
    const approveBtn = screen.getByRole('button', { name: /Approve for Repair/i });
    expect(approveBtn).toBeInTheDocument();

    // Verify Dispatch button is disabled when dispatch_allowed is false
    const dispatchBtn = screen.getByRole('button', { name: /Send for Repair \(Unavailable\)/i });
    expect(dispatchBtn).toBeDisabled();
  });

  it('handles human approval flow correctly in UI', async () => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue(mockFeedbackPreview);
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue(mockC3Status);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue({
      id: 'sub-c3-calc',
      filename: 'calc.py',
      language: 'PYTHON',
    });

    const approveSpy = vi.spyOn(verificationApi, 'approveFeedback').mockResolvedValue({
      iteration_id: 'iter-c3-001',
      iteration_number: 1,
      verification_run_id: 'run-c3-integration-01',
      submission_id: 'sub-c3-calc',
      approval_status: 'APPROVED',
      approved_by: 'human_engineer',
      delivery_status: 'NOT_DISPATCHED',
    });

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    const approveBtn = await screen.findByRole('button', { name: /Approve for Repair/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(approveSpy).toHaveBeenCalledWith('run-c3-integration-01', {
        approver: 'human_engineer',
        notes: expect.stringContaining('Approved via Verification Explorer'),
      });
    });

    expect(await screen.findByText(/Feedback iteration #1 successfully approved by human reviewer/i)).toBeInTheDocument();
  });

  it('triggers fail-closed test dispatch and displays safety response', async () => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue(mockFeedbackPreview);
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue(mockC3Status);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue({
      id: 'sub-c3-calc',
      filename: 'calc.py',
      language: 'PYTHON',
    });

    const dispatchSpy = vi.spyOn(verificationApi, 'dispatchFeedback').mockResolvedValue({
      verification_run_id: 'run-c3-integration-01',
      feedback_id: 'fb-c3-test',
      dispatch_attempt_id: 'disp-test-fail-closed',
      approval_status: 'APPROVED',
      delivery_status: 'NOT_DISPATCHED',
      component_3_acknowledged: false,
      correlation_id: 'corr-test-123',
      message: 'Component 3 integration is disabled in configuration',
      error_category: 'COMPONENT_3_DISABLED',
    });

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    const failClosedBtn = await screen.findByRole('button', { name: /Test Fail-Closed/i });
    fireEvent.click(failClosedBtn);

    await waitFor(() => {
      expect(dispatchSpy).toHaveBeenCalledWith('run-c3-integration-01', {
        approved: true,
        approver: 'human_engineer',
      });
    });

    expect(await screen.findByText(/Safe fail-closed: Component 3 integration is disabled in configuration/i)).toBeInTheDocument();
  });

  it('renders FeedbackHistoryPage with recorded feedback iterations and repair discovery diagnostic', async () => {
    const mockRunWithIteration = {
      ...mockRun,
      feedback_iterations: [
        {
          iteration_id: 'iter-c3-persisted-1',
          iteration_number: 1,
          verification_run_id: 'run-c3-integration-01',
          submission_id: 'sub-c3-calc',
          defects_count: 1,
          approval_status: 'APPROVED',
          approved_by: 'lead_dev@intelise.ai',
          approved_at: '2026-10-15T13:00:00Z',
          delivery_status: 'NOT_DISPATCHED',
          component_3_acknowledged: false,
          error_category: 'COMPONENT_3_DISABLED',
          correlation_id: 'corr-trace-9876',
          dispatch_attempt_id: 'disp-att-5432',
          created_at: '2026-10-15T13:00:00Z',
          updated_at: '2026-10-15T13:00:00Z',
        },
      ],
    };

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRunWithIteration],
    });
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue(mockC3Status);

    renderWithRouter(<FeedbackHistoryPage />);

    // Verify diagnostic banner
    expect(await screen.findByText(/Repair Integration Status/i)).toBeInTheDocument();
    expect(screen.getByText(/Contract: UNDER_DEVELOPMENT/i)).toBeInTheDocument();

    // Verify iteration card rendered with full IDs and badges
    expect(await screen.findByText('#1')).toBeInTheDocument();
    expect(screen.getByText('APPROVED')).toBeInTheDocument();
    expect(screen.getByText('by lead_dev@intelise.ai')).toBeInTheDocument();
    expect(screen.getByText('NOT_DISPATCHED')).toBeInTheDocument();
    expect(screen.getByText('COMPONENT_3_DISABLED')).toBeInTheDocument();
    expect(screen.getByText(/Delivery Unavailable/i)).toBeInTheDocument();

    // Verify un-truncated identifiers are present in the card
    expect(screen.getByText('run-c3-integration-01')).toBeInTheDocument();
    expect(screen.getByText('sub-c3-calc')).toBeInTheDocument();
    expect(screen.getByText('corr-trace-9876')).toBeInTheDocument();
    expect(screen.getByText('disp-att-5432')).toBeInTheDocument();

    // Verify Inspect Run action button
    const inspectBtn = screen.getByRole('button', { name: /Inspect Run/i });
    expect(inspectBtn).toBeInTheDocument();
  });

  it('allows copying identifiers and filtering iteration cards in FeedbackHistoryPage', async () => {
    const mockRunWithIterations = {
      ...mockRun,
      feedback_iterations: [
        {
          iteration_id: 'iter-c3-card-01',
          iteration_number: 1,
          verification_run_id: 'run-c3-filter-01',
          submission_id: 'sub-filter-01',
          defects_count: 2,
          approval_status: 'APPROVED',
          approved_by: 'lead_dev',
          delivery_status: 'ACKNOWLEDGED',
          component_3_acknowledged: true,
          component_3_job_id: 'c3-job-success-777',
          correlation_id: 'corr-filter-alpha',
          created_at: '2026-10-15T13:00:00Z',
        },
        {
          iteration_id: 'iter-c3-card-02',
          iteration_number: 2,
          verification_run_id: 'run-c3-filter-02',
          submission_id: 'sub-filter-02',
          defects_count: 1,
          approval_status: 'NOT_REQUESTED',
          delivery_status: 'NOT_DISPATCHED',
          component_3_acknowledged: false,
          created_at: '2026-10-15T14:00:00Z',
        },
      ],
    };

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRunWithIterations],
    });
    vi.spyOn(verificationApi, 'getComponent3Status').mockResolvedValue(mockC3Status);

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    renderWithRouter(<FeedbackHistoryPage />);

    // Both cards should initially be visible
    expect(await screen.findByText('run-c3-filter-01')).toBeInTheDocument();
    expect(screen.getByText('run-c3-filter-02')).toBeInTheDocument();

    // Click copy button on run ID
    const copyBtns = screen.getAllByTitle('Copy Run ID');
    fireEvent.click(copyBtns[0]);
    expect(writeTextMock).toHaveBeenCalledWith('run-c3-filter-02');

    // Search filter
    const searchInput = screen.getByPlaceholderText(/Search run, sub, approver/i);
    fireEvent.change(searchInput, { target: { value: 'run-c3-filter-01' } });

    // Card 1 matches, card 2 should be filtered out
    await waitFor(() => {
      expect(screen.getByText('run-c3-filter-01')).toBeInTheDocument();
      expect(screen.queryByText('run-c3-filter-02')).not.toBeInTheDocument();
    });
  });
});
