import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import Sidebar from '../components/layout/Sidebar';
import UnifiedSubmissionPage from '../pages/UnifiedSubmissionPage';
import * as submissionApi from '../api/submissionApi';
import * as verificationApi from '../api/verificationApi';

vi.mock('../api/submissionApi', () => ({
  submitCode: vi.fn(),
  uploadSourceFile: vi.fn(),
}));

vi.mock('../api/verificationApi', () => ({
  createVerificationRun: vi.fn(),
  executeVerificationRun: vi.fn(),
  getVerificationRunById: vi.fn(),
  getXaiExplanation: vi.fn(),
  confirmDelivery: vi.fn(),
  getDeliveryConfirmation: vi.fn(),
}));

function run(id, status = 'FAILED') {
  return {
    id,
    submission_id: `sub-${id}`,
    status,
    test_results: [],
    defect_reports: status === 'FAILED' ? [] : undefined,
    execution_telemetry: { duration_ms: 12, agent_reports: {} },
  };
}

function RouteControls() {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <div>
      <output data-testid="location">{location.pathname}{location.search}</output>
      <button onClick={() => navigate('/submissions/new')}>Remove run ID</button>
      <button onClick={() => navigate(-1)}>Back</button>
      <button onClick={() => navigate(1)}>Forward</button>
    </div>
  );
}

function renderPage(initialEntries = ['/submissions/new'], initialIndex = initialEntries.length - 1) {
  return render(
    <MemoryRouter initialEntries={initialEntries} initialIndex={initialIndex}>
      <Sidebar isOpen={false} onClose={() => {}} onToggleCollapse={() => {}} />
      <RouteControls />
      <Routes>
        <Route path="/submissions/new" element={<UnifiedSubmissionPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function deferred() {
  let resolve;
  const promise = new Promise((res) => { resolve = res; });
  return { promise, resolve };
}

describe('New Submission route-owned verification state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.setItem('intelise_active_verification_run_id', 'run-stale-session');
    verificationApi.getDeliveryConfirmation.mockResolvedValue({ is_delivered: false });
  });

  it('1. opens a fresh composer without restoring a cached verification result', async () => {
    renderPage();
    expect(screen.queryByText('Verification & Delivery Results')).not.toBeInTheDocument();
    expect(verificationApi.getVerificationRunById).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Source Code')).toHaveValue('');
    expect(screen.getByRole('link', { name: 'Software Explanations' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'XAI Explanations' })).not.toBeInTheDocument();
  });

  it('2. displays only the result produced by the current verification', async () => {
    submissionApi.submitCode.mockResolvedValue({ id: 'sub-new', language: 'python' });
    verificationApi.createVerificationRun.mockResolvedValue({ id: 'run-new' });
    verificationApi.executeVerificationRun.mockResolvedValue({ id: 'run-new' });
    verificationApi.getVerificationRunById.mockResolvedValue(run('run-new', 'PASSED'));

    renderPage();
    fireEvent.change(screen.getByLabelText('Source Code'), { target: { value: 'print("new")' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verify Code' }));

    expect(await screen.findByText('run-new')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/submissions/new?run_id=run-new');
    });
    expect(screen.queryByText('run-stale-session')).not.toBeInTheDocument();
  });

  it.each([
    ['3. clears a failed run when New Submission is clicked', 'FAILED', 'run-failed'],
    ['4. clears a passed run when New Submission is clicked', 'PASSED', 'run-passed'],
  ])('%s', async (_name, status, id) => {
    verificationApi.getVerificationRunById.mockResolvedValue(run(id, status));
    renderPage([`/submissions/new?run_id=${id}`]);
    expect(await screen.findByText(id)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: 'New Submission' }));
    await waitFor(() => expect(screen.queryByText(id)).not.toBeInTheDocument());
    expect(screen.getByTestId('location')).toHaveTextContent('/submissions/new');
  });

  it('5. loads the exact run requested by a valid deep link', async () => {
    verificationApi.getVerificationRunById.mockImplementation(async (id) => run(id));
    renderPage(['/submissions/new?run_id=run-explicit']);

    expect(await screen.findByText('run-explicit')).toBeInTheDocument();
    expect(verificationApi.getVerificationRunById).toHaveBeenCalledWith('run-explicit');
    expect(screen.queryByText('run-stale-session')).not.toBeInTheDocument();
  });

  it('6. clears the selected result when run_id is removed', async () => {
    verificationApi.getVerificationRunById.mockResolvedValue(run('run-remove'));
    renderPage(['/submissions/new?run_id=run-remove']);
    expect(await screen.findByText('run-remove')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove run ID' }));
    await waitFor(() => expect(screen.queryByText('run-remove')).not.toBeInTheDocument());
  });

  it('7. keeps Back and Forward synchronized with route-specific results', async () => {
    verificationApi.getVerificationRunById.mockResolvedValue(run('run-history'));
    renderPage(['/submissions/new', '/submissions/new?run_id=run-history']);
    expect(await screen.findByText('run-history')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() => expect(screen.queryByText('run-history')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Forward' }));
    expect(await screen.findByText('run-history')).toBeInTheDocument();
  });

  it('8. ignores a late historical-run response after navigating fresh', async () => {
    const pending = deferred();
    verificationApi.getVerificationRunById.mockReturnValue(pending.promise);
    renderPage(['/submissions/new?run_id=run-late']);
    expect(await screen.findByText(/Loading verification run run-late/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: 'New Submission' }));
    await act(async () => pending.resolve(run('run-late')));
    expect(screen.queryByText('run-late')).not.toBeInTheDocument();
    expect(screen.queryByText('Verification & Delivery Results')).not.toBeInTheDocument();
  });

  it('9. repeated New Submission clicks reset the composer even on the same route', async () => {
    renderPage();
    const editor = screen.getByLabelText('Source Code');
    fireEvent.change(editor, { target: { value: 'temporary code' } });
    fireEvent.click(screen.getByRole('link', { name: 'New Submission' }));
    await waitFor(() => expect(editor).toHaveValue(''));

    fireEvent.change(editor, { target: { value: 'temporary code again' } });
    fireEvent.click(screen.getByRole('link', { name: 'New Submission' }));
    await waitFor(() => expect(editor).toHaveValue(''));
  });

  it('10. preserves historical runs and reloads them after fresh navigation', async () => {
    verificationApi.getVerificationRunById.mockResolvedValue(run('run-preserved'));
    renderPage(['/submissions/new?run_id=run-preserved']);
    expect(await screen.findByText('run-preserved')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: 'New Submission' }));
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByText('run-preserved')).toBeInTheDocument();
    expect(verificationApi.getVerificationRunById).toHaveBeenCalledTimes(2);
  });
});
