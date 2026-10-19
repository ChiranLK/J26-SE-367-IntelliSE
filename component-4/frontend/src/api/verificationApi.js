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

/**
 * Retrieves read-only technical feedback preview and eligibility decision for a verification run.
 * @param {string} runId
 */
export async function getFeedbackPreview(runId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/feedback-preview`
  );
  return response.data;
}

/**
 * Explicitly records a technical feedback iteration for an eligible verification run.
 * @param {string} runId
 * @param {string} [notes]
 */
export async function recordFeedbackIteration(runId, notes) {
  const params = notes ? { notes } : {};
  const response = await apiClient.post(
    `/api/v1/verifications/${encodeURIComponent(runId)}/feedback-iterations`,
    null,
    { params }
  );
  return response.data;
}

/**
 * Retrieves human-facing Explainable AI (XAI) explanation for a verification run.
 * Intended for the human engineer; strictly decoupled from Component 3 automated feedback.
 * @param {string} runId
 */
export async function getXaiExplanation(runId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/explanation`,
    { timeout: 90000 }
  );
  return response.data;
}

/**
 * Confirms downstream delivery for a verified, governance-approved artifact version.
 * Unlocks post-delivery software understanding explanations.
 * @param {string} runId
 * @param {Object} [payload]
 */
export async function confirmDelivery(runId, payload = {}) {
  const response = await apiClient.post(
    `/api/v1/verifications/${encodeURIComponent(runId)}/delivery-confirmation`,
    payload
  );
  return response.data;
}

/**
 * Retrieves delivery confirmation status for a verification run.
 * @param {string} runId
 */
export async function getDeliveryConfirmation(runId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/delivery-confirmation`
  );
  return response.data;
}

/**
 * Retrieves the dedicated 8-dimension post-delivery software understanding package.
 * Available exclusively upon confirmed delivery of verified software.
 * @param {string} runId
 */
export async function getPostDeliveryExplanation(runId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/post-delivery-explanation`,
    { timeout: 90000 }
  );
  return response.data;
}

/**
 * Retrieves Component 3 connectivity, configuration, and contract readiness status.
 */
export async function getComponent3Status() {
  const response = await apiClient.get('/api/v1/verifications/integrations/component-3/status');
  return response.data;
}

/**
 * Explicitly records human approval for an eligible verification run's technical feedback.
 * @param {string} runId
 * @param {Object} [payload]
 * @param {string} [payload.approver='human_engineer']
 * @param {string} [payload.notes]
 */
export async function approveFeedback(runId, payload = {}) {
  const response = await apiClient.post(
    `/api/v1/verifications/${encodeURIComponent(runId)}/approve-feedback`,
    payload
  );
  return response.data;
}

/**
 * Dispatches an approved technical feedback package to Component 3.
 * Fails closed safely if Component 3 is not ready or integration is disabled.
 * @param {string} runId
 * @param {Object} [payload]
 * @param {boolean} [payload.approved=true]
 * @param {string} [payload.approver='human_engineer']
 * @param {string} [payload.notes]
 * @param {boolean} [payload.force_retry=false]
 */
export async function dispatchFeedback(runId, payload = {}) {
  const response = await apiClient.post(
    `/api/v1/verifications/${encodeURIComponent(runId)}/dispatch-feedback`,
    payload
  );
  return response.data;
}

/**
 * Ingests corrected source code for a failed verification run.
 * @param {string} runId
 * @param {Object} payload
 * @param {string} payload.corrected_code
 * @param {string} [payload.filename='solution.py']
 * @param {string} [payload.feedback_iteration_id]
 * @param {string} [payload.repair_source='LOCAL_MANUAL']
 * @param {string} [payload.notes]
 */
export async function ingestRepairResponse(runId, payload) {
  const response = await apiClient.post(
    `/api/v1/verifications/${encodeURIComponent(runId)}/repair-responses`,
    payload
  );
  return response.data;
}

/**
 * Triggers re-verification for an ingested repair attempt.
 * @param {string} runId
 * @param {string} repairId
 * @param {Object} [options]
 * @param {boolean} [options.force_reverify=false]
 */
export async function reverifyRepair(runId, repairId, { force_reverify = false } = {}) {
  const response = await apiClient.post(
    `/api/v1/verifications/${encodeURIComponent(runId)}/repair-responses/${encodeURIComponent(repairId)}/re-verify`,
    null,
    { params: { force_reverify } }
  );
  return response.data;
}

/**
 * Lists all repair attempts associated with a verification run.
 * @param {string} runId
 */
export async function getRepairAttempts(runId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/repair-responses`
  );
  return response.data;
}

/**
 * Retrieves details of a specific repair attempt.
 * @param {string} runId
 * @param {string} repairId
 */
export async function getRepairAttemptById(runId, repairId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/repair-responses/${encodeURIComponent(repairId)}`
  );
  return response.data;
}

/**
 * Retrieves defect and test resolution comparison for a re-verified repair attempt.
 * @param {string} runId
 * @param {string} repairId
 */
export async function getRepairComparison(runId, repairId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/repair-responses/${encodeURIComponent(repairId)}/comparison`
  );
  return response.data;
}

/**
 * Retrieves the Module Convergence Risk Report for a verification run (SO5, FR10).
 * @param {string} runId
 */
export async function getConvergenceRiskReport(runId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/convergence-risk-report`
  );
  return response.data;
}

/**
 * Retrieves the formal Deployment Readiness Report for a verification run (FR11, NFR01).
 * @param {string} runId
 */
export async function getDeploymentReadinessReport(runId) {
  const response = await apiClient.get(
    `/api/v1/verifications/${encodeURIComponent(runId)}/deployment-readiness-report`
  );
  return response.data;
}

/**
 * Retrieves local AI engine / Ollama availability and model status.
 */
export async function getAiEngineStatus() {
  const response = await apiClient.get('/api/v1/verifications/status/ai-engine');
  return response.data;
}







