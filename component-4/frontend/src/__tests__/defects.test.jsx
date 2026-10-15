import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import VerificationRunsPage from '../pages/VerificationRunsPage';
import DefectReportsPage from '../pages/DefectReportsPage';
import * as verificationApi from '../api/verificationApi';

const renderWithRouter = (ui) => {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
};

describe('Defect Reports UI Integration', () => {
  it('renders DefectReportsPage with severity filters and live defect view', async () => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'run-test-123',
          submission_id: 'sub-456',
          status: 'FAILED',
          defect_reports: [
            {
              defect_id: 'def-abc-1',
              title: 'Observed Assertion Failure in test_calc',
              failed_test: 'test_calc',
              failure_category: 'ASSERTION_FAILURE',
              severity: 'HIGH',
              file_path: 'calculator.py',
              line_number: 14,
              expected_value: '42',
              actual_value: '0',
              assertion_or_exception: 'assert 0 == 42',
            },
          ],
        },
      ],
    });

    renderWithRouter(<DefectReportsPage />);
    expect(screen.getByText('Defect Reports')).toBeInTheDocument();
    expect(screen.getByText(/Filter Severity:/i)).toBeInTheDocument();
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    expect(screen.getByText('HIGH')).toBeInTheDocument();

    // Defect details
    expect(await screen.findByText('test_calc')).toBeInTheDocument();
    expect(screen.getByText('ASSERTION_FAILURE')).toBeInTheDocument();
    expect(screen.getByText('calculator.py:14')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('assert 0 == 42')).toBeInTheDocument();
  });

  it('renders empty state in DefectReportsPage when no defects exist', async () => {
    vi.spyOn(verificationApi, 'getVerificationRuns').mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'run-pass-1',
          submission_id: 'sub-pass',
          status: 'PASSED',
          defect_reports: [],
        },
      ],
    });

    renderWithRouter(<DefectReportsPage />);
    expect(await screen.findByText(/No Defect Reports Detected/i)).toBeInTheDocument();
  });
});
