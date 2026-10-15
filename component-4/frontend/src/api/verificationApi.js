import apiClient from './client';

/**
 * Initiates a verification run for a submission.
 * @param {Object} payload
 * @param {string} payload.submission_id
 * @param {string} [payload.triggered_by='manual']
 * @param {string[]} [payload.test_types=['unit', 'integration', 'performance']]
 */
export async function createVerificationRun(payload) {
  const response = await apiClient.post('/api/v1/verifications', payload);
  return response.data;
}

/**
 * Lists verification runs, optionally filtered by submission ID.
 * @param {Object} [params]
 * @param {string} [params.submission_id]
 * @param {number} [params.skip=0]
 * @param {number} [params.limit=50]
 */
export async function getVerificationRuns({ submission_id, skip = 0, limit = 50 } = {}) {
  const params = { skip, limit };
  if (submission_id) {
    params.submission_id = submission_id;
  }
  const response = await apiClient.get('/api/v1/verifications', { params });
  return response.data;
}

/**
 * Retrieves full details of a verification run.
 * @param {string} runId
 */
export async function getVerificationRunById(runId) {
  const response = await apiClient.get(`/api/v1/verifications/${encodeURIComponent(runId)}`);
  return response.data;
}

/**
 * Retrieves the current status of a verification run.
 * @param {string} runId
 */
export async function getVerificationStatus(runId) {
  const response = await apiClient.get(`/api/v1/verifications/${encodeURIComponent(runId)}/status`);
  return response.data;
}

/**
 * Triggers execution of a verification run in the isolated Docker container sandbox.
 * @param {string} runId
 * @param {Object} [payload]
 * @param {string} [payload.trusted_test_cases]
 */
export async function executeVerificationRun(runId, payload = {}) {
  const response = await apiClient.post(
    `/api/v1/verifications/${encodeURIComponent(runId)}/execute`,
    payload
  );
  return response.data;
}

/**
 * Retrieves evidence-based defect reports for a specific verification run.
 * @param {string} runId
 */
export async function getVerificationDefects(runId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/defects`
  );
  return response.data;
}


