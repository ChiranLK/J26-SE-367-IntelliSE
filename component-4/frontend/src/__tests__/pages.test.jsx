import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import ManualSubmissionPage from '../pages/ManualSubmissionPage';
import FileUploadPage from '../pages/FileUploadPage';
import DefectReportsPage from '../pages/DefectReportsPage';
import XaiExplanationsPage from '../pages/XaiExplanationsPage';
import FeedbackHistoryPage from '../pages/FeedbackHistoryPage';

function renderWithRouter(ui) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

describe('Frontend Pages Requirements', () => {
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

  it('renders DefectReportsPage with Phase 2 reserved notification', () => {
    renderWithRouter(<DefectReportsPage />);
    expect(screen.getByText('Defect Reports')).toBeInTheDocument();
    expect(screen.getByText(/automated defect detection not active in phase 2a/i)).toBeInTheDocument();
  });

  it('renders XaiExplanationsPage with Phase 3 reserved notification', () => {
    renderWithRouter(<XaiExplanationsPage />);
    expect(screen.getByText('XAI Explanations')).toBeInTheDocument();
    expect(screen.getByText(/explainable ai model integration reserved for phase 3/i)).toBeInTheDocument();
  });

  it('renders FeedbackHistoryPage with Phase 3 reserved notification', () => {
    renderWithRouter(<FeedbackHistoryPage />);
    expect(screen.getByText('Feedback Loop History')).toBeInTheDocument();
    expect(screen.getByText(/component 3 integration reserved for phase 3/i)).toBeInTheDocument();
  });
});
