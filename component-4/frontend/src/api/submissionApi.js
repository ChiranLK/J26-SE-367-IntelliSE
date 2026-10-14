import apiClient from './client';

/**
 * Creates a code submission manually via JSON payload.
 * @param {Object} payload
 * @param {string} payload.code
 * @param {string} payload.language
 * @param {string} [payload.filename]
 * @param {string[]} [payload.requirement_ids]
 * @param {Object} [payload.metadata]
 */
export async function submitCode(payload) {
  const response = await apiClient.post('/api/v1/submissions', payload);
  return response.data;
}

/**
 * Uploads a source code file using multipart/form-data.
 * @param {Object} params
 * @param {File} params.file
 * @param {string} [params.language]
 * @param {string} [params.requirement_ids] - Comma-separated requirement IDs
 * @param {Function} [params.onUploadProgress]
 */
export async function uploadSourceFile({ file, language, requirement_ids, onUploadProgress }) {
  const formData = new FormData();
  formData.append('file', file);
  if (language) {
    formData.append('language', language);
  }
  if (requirement_ids) {
    formData.append('requirement_ids', requirement_ids);
  }

  const response = await apiClient.post('/api/v1/submissions/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress,
  });
  return response.data;
}

/**
 * Lists submissions with pagination.
 * @param {Object} [params]
 * @param {number} [params.skip=0]
 * @param {number} [params.limit=50]
 */
export async function getSubmissions({ skip = 0, limit = 50 } = {}) {
  const response = await apiClient.get('/api/v1/submissions', {
    params: { skip, limit },
  });
  return response.data;
}

/**
 * Retrieves a single submission by its ID.
 * @param {string} submissionId
 */
export async function getSubmissionById(submissionId) {
  const response = await apiClient.get(`/api/v1/submissions/${encodeURIComponent(submissionId)}`);
  return response.data;
}
