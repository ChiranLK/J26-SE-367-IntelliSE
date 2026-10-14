import { describe, it, expect, vi, beforeEach } from 'vitest';
import apiClient from '../api/client';
import { checkBackendHealth } from '../api/healthApi';
import { submitCode, uploadSourceFile, getSubmissions, getSubmissionById } from '../api/submissionApi';
import { createVerificationRun, getVerificationRuns, getVerificationRunById, getVerificationStatus } from '../api/verificationApi';

describe('API Client & Endpoints', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('checks backend health and measures latency', async () => {
    const mockHealth = {
      status: 'ok',
      service: 'INTELISE Component 4',
      storage_backend: 'memory',
      is_ephemeral_storage: true,
    };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockHealth });

    const result = await checkBackendHealth();
    expect(result.status).toBe('ok');
    expect(result.service).toBe('INTELISE Component 4');
    expect(result.latencyMs).toBeGreaterThanOrEqual(0);
  });

  it('calls POST /api/v1/submissions for manual submission', async () => {
    const payload = {
      code: 'print("hello")',
      language: 'python',
      filename: 'hello.py',
    };
    const mockResponse = { id: 'sub-test123', ...payload };
    vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: mockResponse });

    const res = await submitCode(payload);
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/submissions', payload);
    expect(res.id).toBe('sub-test123');
  });

  it('calls POST /api/v1/submissions/upload with FormData for file uploads', async () => {
    const mockFile = new File(['content'], 'test.py', { type: 'text/x-python' });
    const mockResponse = { id: 'sub-upload456', filename: 'test.py' };
    vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: mockResponse });

    const res = await uploadSourceFile({
      file: mockFile,
      language: 'python',
      requirement_ids: 'REQ-01',
    });

    expect(apiClient.post).toHaveBeenCalled();
    const [url, formData, config] = apiClient.post.mock.calls[0];
    expect(url).toBe('/api/v1/submissions/upload');
    expect(formData instanceof FormData).toBe(true);
    expect(config.headers['Content-Type']).toBe('multipart/form-data');
    expect(res.id).toBe('sub-upload456');
  });

  it('calls GET /api/v1/submissions with pagination parameters', async () => {
    const mockList = { total: 1, items: [{ id: 'sub-1' }] };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockList });

    const res = await getSubmissions({ skip: 10, limit: 20 });
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/submissions', {
      params: { skip: 10, limit: 20 },
    });
    expect(res.total).toBe(1);
  });

  it('calls GET /api/v1/submissions/:id', async () => {
    const mockSub = { id: 'sub-1', code: 'test' };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockSub });

    const res = await getSubmissionById('sub-1');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/submissions/sub-1');
    expect(res.id).toBe('sub-1');
  });

  it('calls POST /api/v1/verifications', async () => {
    const payload = {
      submission_id: 'sub-1',
      triggered_by: 'manual',
      test_types: ['unit'],
    };
    const mockRun = { id: 'run-1', status: 'PENDING', ...payload };
    vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: mockRun });

    const res = await createVerificationRun(payload);
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/verifications', payload);
    expect(res.status).toBe('PENDING');
  });

  it('calls GET /api/v1/verifications with submission_id filter', async () => {
    const mockRuns = { total: 1, items: [{ id: 'run-1', submission_id: 'sub-1' }] };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockRuns });

    const res = await getVerificationRuns({ submission_id: 'sub-1', skip: 0, limit: 50 });
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/verifications', {
      params: { submission_id: 'sub-1', skip: 0, limit: 50 },
    });
    expect(res.items.length).toBe(1);
  });

  it('calls GET /api/v1/verifications/:id/status', async () => {
    const mockStatus = { id: 'run-1', submission_id: 'sub-1', status: 'PENDING' };
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockStatus });

    const res = await getVerificationStatus('run-1');
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/verifications/run-1/status');
    expect(res.status).toBe('PENDING');
  });
});
