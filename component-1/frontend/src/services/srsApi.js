import { ApiError, request } from './api.js'
import { requirementExportFilename } from './requirementExport.js'

const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const hash = /^[a-f0-9]{64}$/
const decisions = ['accepted', 'request_changes', 'needs_clarification']
const stamp = (value) => typeof value === 'string' && Number.isFinite(Date.parse(value))

function path(projectId) {
  if (!/^[a-f0-9]{24}$/.test(projectId)) throw new ApiError('Invalid project ID.', { code: 'srs-input' })
  return `/projects/${projectId}/srs`
}

export function validSrsState(data, projectId) {
  if (data?.schema_version !== 'c1-srs-v1' || data.project_id !== projectId || !Number.isInteger(data.revision) || data.revision < 0
    || !Array.isArray(data.versions) || data.versions.length > 20) return false
  const ids = new Set()
  return data.versions.every((version, index) => {
    if (!uuid.test(version?.version_id) || ids.has(version.version_id) || version.version_number !== index + 1
      || version.parent_version_id !== (index ? data.versions[index - 1].version_id : null)
      || !['draft', 'approved'].includes(version.status) || !hash.test(version.content_hash)
      || !uuid.test(version.extraction_run_id) || !uuid.test(version.classification_id) || !hash.test(version.source_discussion_hash)
      || typeof version.project_title !== 'string' || !version.project_title.trim()
      || !(version.project_description === null || typeof version.project_description === 'string')
      || !stamp(version.created_at) || typeof version.created_by !== 'string'
      || !['reviewed-requirements-template-v1', 'classified-requirements-template-v2'].includes(version.generation_method)
      || !Array.isArray(version.requirements) || !version.requirements.length || version.requirements.length > 100
      || !Array.isArray(version.feedback) || version.feedback.length > 500) return false
    ids.add(version.version_id)
    const requirementIds = new Set()
    for (const item of version.requirements) {
      if (typeof item?.requirement_id !== 'string' || !item.requirement_id || requirementIds.has(item.requirement_id)
        || !['FR', 'NFR'].includes(item.label) || typeof item.text !== 'string' || !item.text.trim() || item.text.length > 4000
        || typeof item.original_text !== 'string' || !hash.test(item.source_text_hash) || !(item.label_review_id === null || uuid.test(item.label_review_id))
        || typeof item.authored_revision !== 'boolean') return false
      requirementIds.add(item.requirement_id)
    }
    const latest = new Map()
    for (const feedback of version.feedback) {
      if (!uuid.test(feedback?.feedback_id) || !requirementIds.has(feedback.requirement_id) || !decisions.includes(feedback.decision)
        || typeof feedback.comment !== 'string' || typeof feedback.reviewer_id !== 'string' || !feedback.reviewer_id.trim()
        || !stamp(feedback.recorded_at) || feedback.identity_status !== 'self_reported') return false
      latest.set(feedback.requirement_id, feedback.decision)
    }
    return version.status === 'draft' ? version.approval === null
      : version.approval?.content_hash === version.content_hash && stamp(version.approval.approved_at)
        && version.approval.identity_status === 'self_reported' && typeof version.approval.reviewer_id === 'string'
        && [...requirementIds].every((id) => latest.get(id) === 'accepted')
  })
}

export function getSrs(projectId, options = {}) {
  return request(path(projectId), { ...options, validate: (data) => validSrsState(data, projectId) })
}

export function saveSrsAction(projectId, operation, body, options = {}) {
  if (!['draft', 'feedback', 'revisions', 'approval', 'accept-remaining'].includes(operation) || !uuid.test(body?.submission_id)
    || !Number.isInteger(body.expected_revision) || body.expected_revision < 0 || typeof body.reviewer_id !== 'string' || !body.reviewer_id.trim()) {
    throw new ApiError('Enter a reviewer name and refresh the SRS before saving.', { code: 'srs-input' })
  }
  return request(`${path(projectId)}${operation === 'draft' ? '' : `/${operation}`}`, {
    ...options, method: 'POST', body, validate: (data) => validSrsState(data, projectId),
  }).catch((error) => {
    if (operation === 'draft' && error.status === 409 && error.message.includes('Review and save every FR/NFR label')) {
      throw new ApiError('The running backend still has the old SRS policy. Restart the Component 01 launcher to load optional label corrections, then generate again. You do not need to review every label.', { status: 409, code: 'srs-stale-backend' })
    }
    throw error
  })
}

export function srsText(version) {
  const latest = new Map(version.feedback.map((item) => [item.requirement_id, item]))
  const lines = [`${version.project_title} — SRS version ${version.version_number}`, `Status: ${version.status}`, version.project_description ?? '', '',
    'Scope: reviewed requirement snapshot. Other SRS sections have not been inferred.', '']
  for (const label of ['FR', 'NFR']) {
    lines.push(label === 'FR' ? 'FUNCTIONAL REQUIREMENTS' : 'NON-FUNCTIONAL REQUIREMENTS')
    version.requirements.filter((item) => item.label === label).forEach((item) => {
      const feedback = latest.get(item.requirement_id)
      lines.push(`${item.requirement_id}: ${item.text}`, `Label source: ${item.authored_revision ? 'authored revision' : item.label_review_id ? 'human correction/review' : 'model prediction (not label-reviewed)'}`, `Client decision: ${feedback?.decision ?? 'pending'}`)
      if (feedback?.comment) lines.push(`Comment: ${feedback.comment}`)
      if (item.authored_revision) lines.push(`Authored revision: ${item.change_reason}`)
    })
    lines.push('')
  }
  lines.push(`Content SHA-256: ${version.content_hash}`, `Source extraction: ${version.extraction_run_id}`,
    `Source classification: ${version.classification_id}`, `Source discussion SHA-256: ${version.source_discussion_hash}`)
  if (version.approval) lines.push(`Approved by: ${version.approval.reviewer_id} (self-reported)`, `Approved at: ${version.approval.approved_at}`)
  lines.push('', 'Client identities are self-reported. This template is not a complete standards-compliant SRS or independently verified approval.')
  return lines.join('\n')
}

export function downloadSrs(version, format) {
  if (!['json', 'txt'].includes(format)) throw new Error('Choose JSON or text.')
  const url = URL.createObjectURL(new Blob([format === 'json' ? JSON.stringify({ schema_version: 'c1-srs-version-v1', ...version }, null, 2) : srsText(version)],
    { type: format === 'json' ? 'application/json;charset=utf-8' : 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = requirementExportFilename(`${version.project_title} SRS v${version.version_number}`, format)
  document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
