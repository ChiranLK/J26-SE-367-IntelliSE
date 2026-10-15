import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import DashboardPage from '../pages/DashboardPage';
import ManualSubmissionPage from '../pages/ManualSubmissionPage';
import FileUploadPage from '../pages/FileUploadPage';
import SubmissionHistoryPage from '../pages/SubmissionHistoryPage';
import VerificationRunsPage from '../pages/VerificationRunsPage';
import DefectReportsPage from '../pages/DefectReportsPage';
import XaiExplanationsPage from '../pages/XaiExplanationsPage';
import FeedbackHistoryPage from '../pages/FeedbackHistoryPage';

function renderWithRouter(ui) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

describe('Frontend Pages Requirements', () => {
  it('renders DashboardPage without runtime reference errors', async () => {
    renderWithRouter(<DashboardPage />);
    expect(screen.getByText('Operational Telemetry')).toBeInTheDocument();
  });

  it('renders SubmissionHistoryPage without errors', () => {
    renderWithRouter(<SubmissionHistoryPage />);
    expect(screen.getByText('Submission Repository')).toBeInTheDocument();
  });

  it('renders VerificationRunsPage without errors', () => {
    renderWithRouter(<VerificationRunsPage />);
    expect(screen.getByText('Verification Pipelines')).toBeInTheDocument();
  });
  it('renders ManualSubmissionPage with language selection and prevents empty submission', async () => {
    renderWithRouter(<ManualSubmissionPage />);
    expect(screen.getByText('Manual Code Submission')).toBeInTheDocument();
    expect(screen.getByLabelText(/programming language/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/source code/i)).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', { name: /submit code/i });
    fireEvent.click(submitBtn);

    // Should display client validation error or prevent empty submission
    expect(await screen.findByText(/provide non-empty source code/i)).toBeInTheDocument();
  });

  it('renders FileUploadPage with dropzone and allowed extension indicators', () => {
    renderWithRouter(<FileUploadPage />);
    expect(screen.getByText('Source File Upload')).toBeInTheDocument();
    expect(screen.getByText(/click to select or drag and drop/i)).toBeInTheDocument();
    expect(screen.getByText(/allowed file extensions:/i)).toBeInTheDocument();
    expect(screen.getByText('.py')).toBeInTheDocument();
  });

  it('renders DefectReportsPage with evidence-based defect analysis description', () => {
    renderWithRouter(<DefectReportsPage />);
    expect(screen.getByText('Defect Reports')).toBeInTheDocument();
    expect(screen.getByText(/evidence-based defect analysis/i)).toBeInTheDocument();
  });

  it('renders XaiExplanationsPage with engineering explanations header', () => {
    renderWithRouter(<XaiExplanationsPage />);
    expect(screen.getByText('Human-Facing XAI Explanations')).toBeInTheDocument();
    expect(screen.getByText(/engineering explanations/i)).toBeInTheDocument();
  });

  it('renders FeedbackHistoryPage with repair integration badge and workflow', () => {
    renderWithRouter(<FeedbackHistoryPage />);
    expect(screen.getByText('Feedback Loop History')).toBeInTheDocument();
    expect(screen.getByText('Repair Integration')).toBeInTheDocument();
    expect(screen.getByText(/repair feedback workflow/i)).toBeInTheDocument();
  });
});
