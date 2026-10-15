import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import XaiExplanationsPage from '../pages/XaiExplanationsPage';
import VerificationRunsPage from '../pages/VerificationRunsPage';
import * as verificationApi from '../api/verificationApi';
import * as submissionApi from '../api/submissionApi';

const renderWithRouter = (ui) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

describe('Human-Facing XAI Explanations UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockFailedExplanation = {
    explanation_id: 'xai-test-fail-001',
    verification_run_id: 'run-calc-fail',
    submission_id: 'sub-calc-101',
    verification_status: 'FAILED',
    eligible: true,
    eligibility_reason: 'Verification run failed with 2 confirmed application-code defect report(s).',
    summary: 'Verification run run-calc-fail FAILED with 2 confirmed application-code defect(s).',
    what_failed: [
      "Test 'test_total_with_tax' failed at defective_calculator.py:14 -> assert 8.0 == 108.0",
      "Test 'test_total_without_tax' failed at defective_calculator.py:12 -> assert 0.0 == 100.0",
    ],
    confirmed_observations: [
      {
        test_name: 'test_total_with_tax',
        defect_id: 'def-calc-1',
        failure_category: 'ASSERTION_FAILURE',
        assertion_or_exception: 'assert 8.0 == 108.0',
        expected_value: '108.0',
        observed_value: '8.0',
        file_path: 'defective_calculator.py',
        line_number: 14,
        traceback_excerpt: 'defective_calculator.py:14: assert 8.0 == 108.0',
      },
      {
        test_name: 'test_total_without_tax',
        defect_id: 'def-calc-2',
        failure_category: 'ASSERTION_FAILURE',
        assertion_or_exception: 'assert 0.0 == 100.0',
        expected_value: '100.0',
        observed_value: '0.0',
        file_path: 'defective_calculator.py',
        line_number: 12,
        traceback_excerpt: 'defective_calculator.py:12: assert 0.0 == 100.0',
      },
    ],
    evidence_based_interpretation:
      "In test 'test_total_with_tax', the test oracle expected 108.0 but observed 8.0.\n\nCausal attribution caveat: The failing assertion identifies the symptom of divergence.",
    recommendation: {
      action: 'RETURN_TO_COMPONENT_3',
      recommended: true,
      reason: 'Component 4 recommends human approval to return the technical feedback payload to Component 3 for automated code repair.',
      target_audience: 'Human Engineer / Reviewer',
    },
    suggested_investigations: [
      "Review 'defective_calculator.py' (around line 14) for 'test_total_with_tax'.",
      "Verify that calculation formulas combine subtotal + tax.",
    ],
    evidence_references: { total_defects: 2 },
    explanation_method: 'deterministic_evidence_v1',
    provider: 'deterministic_evidence_v1',
    generated_at: '2026-10-15T12:00:00Z',
    schema_version: '1.0',
  };

  it('renders XAI Explanations page with run selector and full 5-part explanation for failed run', async () => {
    const mockRuns = [
      {
        id: 'run-calc-fail',
        submission_id: 'sub-calc-101',
        status: 'FAILED',
        defect_reports: [{ defect_id: 'def-calc-1' }, { defect_id: 'def-calc-2' }],
        created_at: '2026-10-15T10:00:00Z',
      },
    ];

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: mockRuns,
    });
    vi.spyOn(verificationApi, 'getXaiExplanation').mockResolvedValue(mockFailedExplanation);

    renderWithRouter(<XaiExplanationsPage />);

    // Header & Target Callout
    expect(await screen.findByText('Human-Facing XAI Explanations')).toBeInTheDocument();
    expect(screen.getByText(/Target: Reviewer/i)).toBeInTheDocument();
    expect(screen.getByText(/Engineering Explanations/i)).toBeInTheDocument();

    // Section 1: Executive Summary
    expect(await screen.findByText('1. Executive Findings Summary')).toBeInTheDocument();
    expect(
      screen.getByText(/Verification run run-calc-fail FAILED with 2 confirmed application-code defect\(s\)\./i)
    ).toBeInTheDocument();

    // Section 2: What Failed?
    expect(screen.getByText('2. What Failed?')).toBeInTheDocument();
    expect(screen.getByText(/Test 'test_total_with_tax' failed/i)).toBeInTheDocument();
    expect(screen.getByText(/Test 'test_total_without_tax' failed/i)).toBeInTheDocument();

    // Section 3: Confirmed Observations
    expect(screen.getByText('3. Confirmed Observations')).toBeInTheDocument();
    expect(screen.getByText('108.0')).toBeInTheDocument();
    expect(screen.getByText('8.0')).toBeInTheDocument();
    expect(screen.getByText('100.0')).toBeInTheDocument();
    expect(screen.getByText('0.0')).toBeInTheDocument();

    // Section 4: Evidence-Based Interpretation
    expect(screen.getByText('4. Evidence-Based Interpretation')).toBeInTheDocument();
    expect(screen.getByText(/Causal attribution caveat/i)).toBeInTheDocument();

    // Section 5: Action Recommendation
    expect(screen.getByText('5. Action Recommendation for Engineering Review')).toBeInTheDocument();
    expect(screen.getByText('SEND FOR REPAIR')).toBeInTheDocument();
    expect(
      screen.getByText(/Component 4 recommends human approval to return the technical feedback payload/i)
    ).toBeInTheDocument();

    // Section 6: Suggested Next Investigations
    expect(screen.getByText('6. Suggested Next Investigations')).toBeInTheDocument();
    expect(
      screen.getByText(/Review 'defective_calculator\.py' \(around line 14\)/i)
    ).toBeInTheDocument();
  });

  it('renders passed verification run explanation with accept recommendation', async () => {
    const mockPassedExplanation = {
      explanation_id: 'xai-test-pass-002',
      verification_run_id: 'run-calc-pass',
      submission_id: 'sub-calc-pass-1',
      verification_status: 'PASSED',
      eligible: false,
      eligibility_reason: 'Verification run passed successfully; zero defects detected, so corrective feedback is not applicable.',
      summary: 'All 2 executed test case(s) in the authorized test suite passed successfully.',
      what_failed: [],
      confirmed_observations: [],
      evidence_based_interpretation:
        'The implementation produced outputs matching all expected values across 2 executed test case(s). Scope qualification: passing tests does not constitute an exhaustive mathematical proof.',
      recommendation: {
        action: 'ACCEPT_VERIFICATION',
        recommended: false,
        reason: 'All authorized test cases passed without failure. No corrective cycle with Component 3 is required.',
        target_audience: 'Human Engineer / Reviewer',
      },
      suggested_investigations: [
        'Review test suite coverage to confirm edge cases were tested.',
      ],
      evidence_references: { total_tests: 2 },
      explanation_method: 'deterministic_evidence_v1',
      provider: 'deterministic_evidence_v1',
      generated_at: '2026-10-15T12:00:00Z',
      schema_version: '1.0',
    };

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'run-calc-pass',
          submission_id: 'sub-calc-pass-1',
          status: 'PASSED',
          defect_reports: [],
          created_at: '2026-10-15T10:00:00Z',
        },
      ],
    });
    vi.spyOn(verificationApi, 'getXaiExplanation').mockResolvedValue(mockPassedExplanation);

    renderWithRouter(<XaiExplanationsPage />);

    expect(await screen.findByText('ACCEPT VERIFICATION (PASS)')).toBeInTheDocument();
    expect(
      screen.getByText(/All 2 executed test case\(s\) in the authorized test suite passed successfully/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Scope qualification: passing tests does not constitute an exhaustive mathematical proof/i)).toBeInTheDocument();
  });

  it('renders empty state when no verification runs exist', async () => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 0,
      items: [],
    });

    renderWithRouter(<XaiExplanationsPage />);

    expect(await screen.findByText(/No Verification Runs Detected/i)).toBeInTheDocument();
  });

  it('renders error state when explanation retrieval fails', async () => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'run-err',
          submission_id: 'sub-err',
          status: 'FAILED',
          created_at: '2026-10-15T10:00:00Z',
        },
      ],
    });
    vi.spyOn(verificationApi, 'getXaiExplanation').mockRejectedValue(new Error('Network error'));

    renderWithRouter(<XaiExplanationsPage />);

    expect(await screen.findByText(/Explanation Retrieval Error/i)).toBeInTheDocument();
    expect(screen.getByText(/Failed to retrieve XAI explanation/i)).toBeInTheDocument();
  });

  it('renders compact Human-Facing XAI Explanation section inside VerificationRunsPage details modal', async () => {
    const mockRun = {
      id: 'run-modal-xai-1',
      submission_id: 'sub-modal-1',
      status: 'FAILED',
      requested_test_types: ['UNIT'],
      triggered_by: 'manual',
      created_at: '2026-10-15T10:00:00Z',
      test_results: [],
      defect_reports: [],
      feedback_iterations: [],
    };

    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [mockRun],
    });
    vi.spyOn(verificationApi, 'getVerificationRunById').mockResolvedValue(mockRun);
    vi.spyOn(verificationApi, 'getFeedbackPreview').mockResolvedValue({
      eligible: false,
      reason: 'No defects',
      feedback: null,
    });
    vi.spyOn(verificationApi, 'getXaiExplanation').mockResolvedValue(mockFailedExplanation);
    vi.spyOn(submissionApi, 'getSubmissionById').mockResolvedValue({
      id: 'sub-modal-1',
      filename: 'defective_calculator.py',
      language: 'PYTHON',
    });

    renderWithRouter(<VerificationRunsPage />);

    // Open detail modal
    const detailsBtn = await screen.findByRole('button', { name: /Details/i });
    fireEvent.click(detailsBtn);

    // Verify modal header
    expect(await screen.findByText(/Pipeline Details: run-modal-xai-1/i)).toBeInTheDocument();

    // Verify Human-Facing XAI Explanation section in modal
    expect(screen.getByText('Human-Facing XAI Explanation')).toBeInTheDocument();
    expect(screen.getByText('Action: Send for Repair')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Open Full XAI Explanation Page/i })).toBeInTheDocument();
  });
});
