import { ApiError, request } from './api.js'
import { classificationLabels } from './projectApi.js'

const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const label = (value) => ['FR', 'NFR'].includes(value)
const stamp = (value) => typeof value === 'string' && Number.isFinite(Date.parse(value))
const hash = async (text) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))), (byte) => byte.toString(16).padStart(2, '0')).join('')

function context(projectId, extraction, classification) {
  const labels = classificationLabels(classification, extraction, projectId)
  if (!/^[a-f0-9]{24}$/i.test(projectId) || !uuid.test(extraction.run_id) || !uuid.test(classification.classification_id)) {
    throw new ApiError('Invalid saved classification identity. Refresh saved results.', { code: 'review-context' })
  }
  return { labels, path: `/projects/${projectId}/extractions/${extraction.run_id}/classifications/${classification.classification_id}` }
}

async function validReview(review, projectId, extraction, classification, labels) {
  const candidate = extraction.candidates.find((item) => item.requirement_id === review?.requirement_id)
  return !!candidate && uuid.test(review.review_id) && uuid.test(review.submission_id)
    && review.project_id === projectId && review.extraction_run_id === extraction.run_id
    && review.classification_id === classification.classification_id
    && review.original_prediction === labels.get(candidate.requirement_id) && label(review.reviewed_label)
    && review.model_identifier === classification.model_identifier && review.model_version === classification.model_version
    && review.source_discussion_hash === extraction.source_discussion_hash
    && review.requirement_text_hash === await hash(candidate.requirement_text)
    && typeof review.reviewer_id === 'string' && !!review.reviewer_id.trim() && review.reviewer_id.length <= 120
    && typeof review.note === 'string' && review.note.length <= 2000 && stamp(review.reviewed_at)
    && review.review_status === 'user_reviewed' && review.reviewer_identity_status === 'self_reported'
}

export function getLabelReviews(projectId, extraction, classification, options = {}) {
  const { labels, path } = context(projectId, extraction, classification)
  return request(`${path}/reviews`, { ...options, validate: async (page) => {
    if (page?.project_id !== projectId || page.extraction_run_id !== extraction.run_id
      || page.classification_id !== classification.classification_id || !Array.isArray(page.reviews)
      || page.reviews.length > extraction.candidates.length) return false
    const ids = new Set()
    for (const review of page.reviews) {
      if (ids.has(review?.requirement_id) || !await validReview(review, projectId, extraction, classification, labels)) return false
      ids.add(review.requirement_id)
    }
    return true
  } })
}

export function saveLabelReview(projectId, extraction, classification, requirementId, input, options = {}) {
  const { labels, path } = context(projectId, extraction, classification)
  if (!labels.has(requirementId) || !uuid.test(input.submission_id) || !label(input.reviewed_label)
    || typeof input.reviewer_id !== 'string' || !input.reviewer_id.trim() || input.reviewer_id.length > 120
    || typeof input.note !== 'string' || input.note.length > 2000) {
    throw new ApiError('Select FR or NFR and enter your reviewer name or ID.', { code: 'review-input' })
  }
  const body = { submission_id: input.submission_id, reviewed_label: input.reviewed_label, reviewer_id: input.reviewer_id.trim(), note: input.note }
  return request(`${path}/requirements/${encodeURIComponent(requirementId)}/reviews`, {
    ...options, method: 'POST', body, validate: async (review) =>
      await validReview(review, projectId, extraction, classification, labels) && review.requirement_id === requirementId
      && Object.entries(body).every(([key, value]) => review[key] === value),
  })
}
