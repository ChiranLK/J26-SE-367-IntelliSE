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

describe('Technical Feedback Preview UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders technical feedback preview for eligible failed verification run', async () => {
    const mockRun = {
      id: 'run-failed-feedback-1',
      submission_id: 'sub-calc-1',
      status: 'FAILED',
      test_results: [
        {
          test_id: 'test_total_with_tax',
          name: 'test_total_with_tax',
          status: 'FAILED',
          duration_ms: 12.0,
          error_message: 'assert 8.0 == 108.0',
        },
      ],
      requested_test_types: ['UNIT'],
      triggered_by: 'manual',
      created_at: '2026-10-15T10:00:00Z',
      defect_reports: [
        {
          defect_id: 'def-calc-101',
          title: 'Assertion failure in test_total_with_tax',
          failed_test: 'test_total_with_tax',
          failure_category: 'ASSERTION_FAILURE',
          severity: 'HIGH',
          file_path: 'defective_calculator.py',
          line_number: 14,
          expected_value: '108.0',
          actual_value: '8.0',
          assertion_or_exception: 'assert 8.0 == 108.0',
        },
      ],
      feedback_iterations: [],
    };

    const mockFeedbackPreview = {
      eligible: true,
      reason: 'Verification run failed with 1 confirmed application-code defect report(s).',
      feedback: {
        feedback_id: 'fb-calc-test-01',
        verification_run_id: 'run-failed-feedback-1',
        submission_id: 'sub-calc-1',
        verification_status: 'FAILED',
        affected_files: ['defective_calculator.py'],
        failed_tests: ['test_total_with_tax'],
        failed_assertions: ['assert 8.0 == 108.0'],
        value_comparisons: [
          {
            test_name: 'test_total_with_tax',
            defect_id: 'def-calc-101',
            expected: '108.0',
            observed: '8.0',
            assertion: 'assert 8.0 == 108.0',
          },
        ],
        error_logs: ['assert 8.0 == 108.0'],
        defect_ids: ['def-calc-101'],
        evidence_references: {
          total_tests: 1,
          failed_tests_count: 1,
          defect_count: 1,
          exit_code: 1,
        },
        generated_at: '2026-10-15T12:00:00Z',
        schema_version: '1.0',
      },
      generated_at: '2026-10-15T12:00:00Z',
    };

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue(mockFeedbackPreview);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue({
      id: 'sub-calc-1',
      filename: 'defective_calculator.py',
      language: 'PYTHON',
    });

    renderWithRouter(<VerificationRunsPage />);

    // Wait for list to load and click Inspect Details
    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    // Verify modal header
    expect(await screen.findByText(/Pipeline Details: run-failed-feedback-1/i)).toBeInTheDocument();

    // Verify Technical Feedback Section Header and Target
    expect(screen.getByText('Machine-Readable Feedback Preview')).toBeInTheDocument();
    expect(screen.getByText('Target: Component 3')).toBeInTheDocument();

    // Verify Eligibility status badge & reason
    expect(screen.getByText('Eligible for Component 3 Feedback')).toBeInTheDocument();
    expect(
      screen.getByText(/Verification run failed with 1 confirmed application-code defect report/i)
    ).toBeInTheDocument();

    // Verify summary pills
    expect(screen.getByText('fb-calc-test-01')).toBeInTheDocument();
    expect(screen.getAllByText('defective_calculator.py').length).toBeGreaterThan(0);
    expect(screen.getByText(/1 statement\(s\)/i)).toBeInTheDocument();

    // Verify JSON preview card and copy button
    expect(screen.getByText(/payload\.json \(Schema v1\.0\)/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Copy JSON/i })).toBeInTheDocument();

    // Verify unavailable repair dispatch button is disabled
    const dispatchBtn = screen.getByRole('button', { name: /Component 3 Integration Unavailable/i });
    expect(dispatchBtn).toBeInTheDocument();
    expect(dispatchBtn).toBeDisabled();
  });

  it('renders ineligible notice for PASSED verification run', async () => {
    const mockRun = {
      id: 'run-passed-1',
      submission_id: 'sub-calc-passed',
      status: 'PASSED',
      test_results: [
        {
          test_id: 'test_total_with_tax',
          name: 'test_total_with_tax',
          status: 'PASSED',
          duration_ms: 10.0,
        },
      ],
      requested_test_types: ['UNIT'],
      triggered_by: 'manual',
      created_at: '2026-10-15T10:00:00Z',
      defect_reports: [],
      feedback_iterations: [],
    };

    const mockFeedbackPreview = {
      eligible: false,
      reason: 'Verification run passed; zero code defects detected.',
      feedback: null,
      generated_at: '2026-10-15T12:00:00Z',
    };

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue(mockFeedbackPreview);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue({
      id: 'sub-calc-passed',
      filename: 'calculator.py',
      language: 'PYTHON',
    });

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    expect(await screen.findByText(/Pipeline Details: run-passed-1/i)).toBeInTheDocument();
    expect(screen.getByText('Machine-Readable Feedback Preview')).toBeInTheDocument();
    expect(screen.getByText('Corrective Feedback Ineligible')).toBeInTheDocument();
    expect(screen.getByText(/Verification run passed; zero code defects detected/i)).toBeInTheDocument();

    // JSON payload card should NOT be rendered when ineligible
    expect(screen.queryByText(/payload\.json/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Copy JSON/i })).not.toBeInTheDocument();
  });

  it('copies feedback JSON to clipboard when Copy JSON is clicked', async () => {
    const mockRun = {
      id: 'run-failed-copy',
      submission_id: 'sub-calc-copy',
      status: 'FAILED',
      test_results: [],
      requested_test_types: ['UNIT'],
      triggered_by: 'manual',
      created_at: '2026-10-15T10:00:00Z',
      defect_reports: [
        {
          defect_id: 'def-1',
          title: 'Assertion failure',
          failed_test: 'test_foo',
          failure_category: 'ASSERTION_FAILURE',
          severity: 'HIGH',
          file_path: 'foo.py',
          line_number: 1,
          assertion_or_exception: 'assert 1 == 2',
        },
      ],
      feedback_iterations: [],
    };

    const payloadObj = {
      feedback_id: 'fb-copy-test',
      verification_run_id: 'run-failed-copy',
      submission_id: 'sub-calc-copy',
      verification_status: 'FAILED',
      affected_files: ['foo.py'],
      failed_tests: ['test_foo'],
      failed_assertions: ['assert 1 == 2'],
      value_comparisons: [],
      error_logs: [],
      defect_ids: ['def-1'],
      evidence_references: {},
      generated_at: '2026-10-15T12:00:00Z',
      schema_version: '1.0',
    };

    const mockFeedbackPreview = {
      eligible: true,
      reason: 'Failed with defect reports.',
      feedback: payloadObj,
      generated_at: '2026-10-15T12:00:00Z',
    };

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue(mockFeedbackPreview);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue({
      id: 'sub-calc-copy',
      filename: 'foo.py',
      language: 'PYTHON',
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    renderWithRouter(<VerificationRunsPage />);

    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    const copyBtn = await screen.findByRole('button', { name: /Copy JSON/i });
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(JSON.stringify(payloadObj, null, 2));
    });
    expect(await screen.findByRole('button', { name: /Copied/i })).toBeInTheDocument();
  });
});
