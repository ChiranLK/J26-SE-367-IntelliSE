import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import UnifiedSubmissionPage from '../pages/UnifiedSubmissionPage';
import * as submissionApi from '../api/submissionApi';

// Mock submission API calls
vi.mock('../api/submissionApi', () => ({
  submitCode: vi.fn(),
  uploadSourceFile: vi.fn(),
}));

function SubmissionRouteProbe() {
  const location = useLocation();
  return <div>Submissions List Page {location.search}</div>;
}

function renderUnifiedSubmission(initialRoute = '/submissions/new') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/submissions/new" element={<UnifiedSubmissionPage />} />
        <Route path="/submissions/upload" element={<UnifiedSubmissionPage />} />
        <Route path="/submissions" element={<SubmissionRouteProbe />} />
        <Route path="/verifications" element={<div>Verifications Page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('Unified Code Submission Interface (Task 9 Regression Suite)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // 1. Paste-only submission
  it('1. submits pasted code via submitCode endpoint', async () => {
    submissionApi.submitCode.mockResolvedValueOnce({
      id: 'sub-test-paste-01',
      code: 'def add(a, b): return a + b\n',
      language: 'python',
      filename: 'sample.py',
      created_at: '2026-10-20T10:00:00Z',
    });

    renderUnifiedSubmission();
    const textarea = screen.getByPlaceholderText(/paste your code or attach files to verify/i);
    fireEvent.change(textarea, { target: { value: 'def add(a, b): return a + b\n' } });

    const submitBtn = screen.getByRole('button', { name: /upload (submission|project)/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(submissionApi.submitCode).toHaveBeenCalledWith(
        expect.objectContaining({
          code: 'def add(a, b): return a + b\n',
          language: 'python',
        })
      );
    });

    expect(await screen.findByText('sub-test-paste-01')).toBeInTheDocument();
  });

  // 2. Single-file attachment
  it('2. submits single attached source file via uploadSourceFile endpoint', async () => {
    submissionApi.uploadSourceFile.mockResolvedValueOnce({
      id: 'sub-single-file-02',
      filename: 'auth.py',
      language: 'python',
      created_at: '2026-10-20T10:00:00Z',
      metadata: { original_filename: 'auth.py', is_multi_file: false },
    });

    const { container } = renderUnifiedSubmission();
    const fileInput = container.querySelector('input[type="file"][multiple]');
    expect(fileInput).not.toBeNull();

    const file = new File(['def authenticate(): pass\n'], 'auth.py', { type: 'text/x-python' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    // Attachment chip should appear
    expect(await screen.findByText('auth.py')).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', { name: /upload (submission|project)/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(submissionApi.uploadSourceFile).toHaveBeenCalledWith(
        expect.objectContaining({
          file,
        })
      );
    });

    expect(await screen.findByText('sub-single-file-02')).toBeInTheDocument();
  });

  // 3. Multiple-file attachment (packaged into ZIP)
  it('3. packages multiple attached files into a project ZIP and uploads to multi-file endpoint', async () => {
    submissionApi.uploadSourceFile.mockResolvedValueOnce({
      id: 'sub-multi-files-03',
      filename: 'project_submission.zip',
      language: 'python',
      created_at: '2026-10-20T10:00:00Z',
      metadata: { is_multi_file: true, total_project_files: 2, entrypoint: 'main.py' },
    });

    const { container } = renderUnifiedSubmission();
    const fileInput = container.querySelector('input[type="file"][multiple]');

    const file1 = new File(['def solve(): return 1\n'], 'main.py', { type: 'text/x-python' });
    const file2 = new File(['def helper(): return 2\n'], 'utils.py', { type: 'text/x-python' });

    fireEvent.change(fileInput, { target: { files: [file1, file2] } });

    expect(await screen.findByText('main.py')).toBeInTheDocument();
    expect(await screen.findByText('utils.py')).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', { name: /upload project/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(submissionApi.uploadSourceFile).toHaveBeenCalledWith(
        expect.objectContaining({
          file: expect.any(File),
        })
      );
    });

    const callArgs = submissionApi.uploadSourceFile.mock.calls[0][0];
    expect(callArgs.file.name).toBe('project_submission.zip');
    expect(callArgs.file.type).toBe('application/zip');
  });

  // 4. ZIP project attachment
  it('4. uploads attached ZIP project archive directly to multi-file endpoint', async () => {
    submissionApi.uploadSourceFile.mockResolvedValueOnce({
      id: 'sub-zip-proj-04',
      filename: 'login_system.zip',
      language: 'python',
      created_at: '2026-10-20T10:00:00Z',
      metadata: { is_multi_file: true, total_project_files: 5, entrypoint: 'auth/service.py' },
    });

    const { container } = renderUnifiedSubmission();
    const zipInput = container.querySelector('input[type="file"][accept=".zip"]');
    expect(zipInput).not.toBeNull();

    const zipFile = new File(['PK\x03\x04mockzipdata'], 'login_system.zip', { type: 'application/zip' });
    fireEvent.change(zipInput, { target: { files: [zipFile] } });

    expect(await screen.findByText('login_system.zip')).toBeInTheDocument();
    expect(screen.getByText('Project ZIP')).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', { name: /upload project/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(submissionApi.uploadSourceFile).toHaveBeenCalledWith(
        expect.objectContaining({
          file: zipFile,
        })
      );
    });

    expect(await screen.findByText('sub-zip-proj-04')).toBeInTheDocument();
  });

  // 5. Mixed-input handling
  it('5. handles mixed input by bundling pasted code and attached files into combined archive', async () => {
    submissionApi.uploadSourceFile.mockResolvedValueOnce({
      id: 'sub-mixed-05',
      filename: 'project_submission.zip',
      language: 'python',
      created_at: '2026-10-20T10:00:00Z',
      metadata: { is_multi_file: true, total_project_files: 2, entrypoint: 'sample.py' },
    });

    const { container } = renderUnifiedSubmission();
    const textarea = screen.getByPlaceholderText(/paste your code or attach files to verify/i);
    fireEvent.change(textarea, { target: { value: 'def entry(): return True\n' } });

    const fileInput = container.querySelector('input[type="file"][multiple]');
    const attachedFile = new File(['def helper(): pass\n'], 'helper.py', { type: 'text/x-python' });
    fireEvent.change(fileInput, { target: { files: [attachedFile] } });

    // Should render mixed mode callout
    expect(await screen.findByText(/mixed mode:/i)).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', { name: /upload project/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(submissionApi.uploadSourceFile).toHaveBeenCalledWith(
        expect.objectContaining({
          file: expect.any(File),
        })
      );
    });
  });

  // 6. Attachment removal
  it('6. removes attachment when chip remove button is clicked', async () => {
    const { container } = renderUnifiedSubmission();
    const fileInput = container.querySelector('input[type="file"][multiple]');
    const file = new File(['a = 1\n'], 'data.py', { type: 'text/x-python' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    expect(await screen.findByText('data.py')).toBeInTheDocument();

    const removeBtn = screen.getByRole('button', { name: /remove data\.py/i });
    fireEvent.click(removeBtn);

    expect(screen.queryByText('data.py')).not.toBeInTheDocument();
  });

  // 7. Language-aware sample loading
  it('7. loads valid sample code corresponding to the selected language', async () => {
    renderUnifiedSubmission();
    const langSelect = screen.getByRole('combobox');
    const loadSampleBtn = screen.getByRole('button', { name: /load sample/i });
    const textarea = screen.getByPlaceholderText(/paste your code or attach files to verify/i);

    // Python sample
    fireEvent.click(loadSampleBtn);
    expect(textarea.value).toContain('def calculate_metrics');

    // Java sample
    fireEvent.change(langSelect, { target: { value: 'java' } });
    fireEvent.click(loadSampleBtn);
    expect(textarea.value).toContain('public class Sample');

    // Go sample
    fireEvent.change(langSelect, { target: { value: 'go' } });
    fireEvent.click(loadSampleBtn);
    expect(textarea.value).toContain('package main');
  });

  // 8. Filename synchronization
  it('8. updates default filename extension when language changes', () => {
    renderUnifiedSubmission();
    const langSelect = screen.getByRole('combobox');
    const loadSampleBtn = screen.getByRole('button', { name: /load sample/i });

    // Load Python sample -> sample.py
    fireEvent.click(loadSampleBtn);

    // Open Advanced Options to inspect filename
    const advToggle = screen.getByText('Advanced Verification Options');
    fireEvent.click(advToggle);

    const filenameInput = screen.getByPlaceholderText(/sample\.py/i);
    expect(filenameInput.value).toBe('sample.py');

    // Change to rust and load sample -> main.rs
    fireEvent.change(langSelect, { target: { value: 'rust' } });
    fireEvent.click(loadSampleBtn);
    expect(filenameInput.value).toBe('main.rs');
  });

  // 9. Overwrite confirmation
  it('9. prompts user confirmation before replacing custom code with sample', () => {
    renderUnifiedSubmission();
    const textarea = screen.getByPlaceholderText(/paste your code or attach files to verify/i);
    fireEvent.change(textarea, { target: { value: '# My Custom Important Logic' } });

    const loadSampleBtn = screen.getByRole('button', { name: /load sample/i });

    // Reject overwrite
    vi.spyOn(window, 'confirm').mockReturnValueOnce(false);
    fireEvent.click(loadSampleBtn);
    expect(textarea.value).toBe('# My Custom Important Logic');

    // Accept overwrite
    vi.spyOn(window, 'confirm').mockReturnValueOnce(true);
    fireEvent.click(loadSampleBtn);
    expect(textarea.value).toContain('def calculate_metrics');
  });

  // 10. Advanced options (Requirement IDs & Test Suite)
  it('10. allows expanding advanced options and providing requirement IDs and test code', async () => {
    renderUnifiedSubmission();
    const advToggle = screen.getByText('Advanced Verification Options');
    fireEvent.click(advToggle);

    expect(screen.getByLabelText(/requirement identifiers/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/trusted test suite/i)).toBeInTheDocument();

    const tagInput = screen.getByPlaceholderText(/e\.g\. REQ-AUTH-01/i);
    fireEvent.change(tagInput, { target: { value: 'REQ-SEC-01' } });
    fireEvent.keyDown(tagInput, { key: 'Enter', code: 'Enter' });

    expect(screen.getByText('REQ-SEC-01')).toBeInTheDocument();
  });

  // 11. Backend validation errors
  it('11. displays backend validation errors clearly', async () => {
    submissionApi.submitCode.mockRejectedValueOnce(
      new Error('Invalid syntax in code submission.')
    );

    renderUnifiedSubmission();
    const textarea = screen.getByPlaceholderText(/paste your code or attach files to verify/i);
    fireEvent.change(textarea, { target: { value: 'invalid syntax ??' } });

    const submitBtn = screen.getByRole('button', { name: /upload (submission|project)/i });
    fireEvent.click(submitBtn);

    expect(await screen.findByText('Invalid syntax in code submission.')).toBeInTheDocument();
  });

  // 12. Submission success navigation
  it('12. displays submission ID and navigates to the submitted record', async () => {
    submissionApi.submitCode.mockResolvedValueOnce({
      id: 'sub-nav-12',
      code: 'def test(): pass',
      language: 'python',
      created_at: '2026-10-20T10:00:00Z',
    });

    renderUnifiedSubmission();
    const textarea = screen.getByPlaceholderText(/paste your code or attach files to verify/i);
    fireEvent.change(textarea, { target: { value: 'def test(): pass' } });

    const submitBtn = screen.getByRole('button', { name: /upload (submission|project)/i });
    fireEvent.click(submitBtn);

    expect(await screen.findByText('sub-nav-12')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run verification/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /view submission/i }));
    expect(await screen.findByText(/Submissions List Page \?view=sub-nav-12/i)).toBeInTheDocument();
  });

  // 13. Duplicate-submit prevention
  it('13. prevents duplicate submits while request is in-flight', async () => {
    let resolveSubmit;
    submissionApi.submitCode.mockReturnValueOnce(
      new Promise((res) => {
        resolveSubmit = res;
      })
    );

    renderUnifiedSubmission();
    const textarea = screen.getByPlaceholderText(/paste your code or attach files to verify/i);
    fireEvent.change(textarea, { target: { value: 'def sleep(): pass' } });

    const submitBtn = screen.getByRole('button', { name: /upload (submission|project)/i });
    fireEvent.click(submitBtn);

    // Button should be disabled during in-flight submission
    expect(submitBtn).toBeDisabled();

    resolveSubmit({ id: 'sub-done', code: 'def sleep(): pass', language: 'python' });
    await waitFor(() => expect(screen.getByText('sub-done')).toBeInTheDocument());
  });

  // 14. Legacy route compatibility (/submissions/upload renders unified page)
  it('14. supports legacy route /submissions/upload as alias to unified submission page', () => {
    renderUnifiedSubmission('/submissions/upload');
    expect(screen.getByText('New Submission')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/paste your code or attach files to verify/i)).toBeInTheDocument();
  });

  // 15. Empty submission validation
  it('15. rejects empty submission when neither code nor attachments are provided', async () => {
    renderUnifiedSubmission();
    const submitBtn = screen.getByRole('button', { name: /upload (submission|project)/i });
    expect(submitBtn).toBeDisabled(); // Disabled by default when empty
  });
});
