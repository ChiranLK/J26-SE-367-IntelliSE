// Verified against component-1-backend e78da735, not inferred from UI fixtures.
import { validProjectProvenance } from './projectProvenance.js'
export const PROJECT_LIMITS = { name: 120, description: 2000, discussion_text: 100000 }
export const PAGE_LIMIT = 10
export const MAX_OFFSET = 10000
export const characterCount = (text) => Array.from(text).length
// Python str.strip includes these control characters; JavaScript trim differs.
// eslint-disable-next-line no-control-regex
const blank = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value)
const text = (value, max, min = 1) => typeof value === 'string' && characterCount(value) >= min && characterCount(value) <= max
const date = (value) => typeof value === 'string' && /(Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
export const validProjectId = (value) => typeof value === 'string' && /^[a-f\d]{24}$/i.test(value)

export function validateProjectInput(input) {
  const errors = {}
  for (const [field, max] of Object.entries(PROJECT_LIMITS)) {
    const value = input[field]
    if (field === 'description' && value === null) continue
    if (typeof value !== 'string') errors[field] = 'Enter text in this field.'
    else if (field !== 'description' && blank.test(value)) errors[field] = field === 'name' ? 'Enter a project name.' : 'Enter the original client discussion.'
    else if (characterCount(value) > max) errors[field] = `Use ${max.toLocaleString('en-US')} characters or fewer.`
  }
  return errors
}

export function validProject(value, full = true) {
  return object(value) && validProjectId(value.id) && text(value.name, 120) && !blank.test(value.name)
    && (value.description === null || text(value.description, 2000, 0))
    && value.status === 'draft' && date(value.created_at) && date(value.updated_at)
    && (!full || (text(value.discussion_text, 100000) && !blank.test(value.discussion_text)
      && (value.transcription_provenance == null || validProjectProvenance(value.transcription_provenance))))
}

export function validProjectPage(value, limit, offset) {
  return object(value) && Array.isArray(value.items) && value.items.length <= limit
    && value.items.every((item) => validProject(item, false))
    && value.limit === limit && value.offset === offset && typeof value.has_more === 'boolean'
}

export function validExtraction(value, projectId, discussion) {
  if (!object(value) || !text(value.run_id, 200) || value.project_id !== projectId.toLowerCase()
    || typeof value.source_discussion_hash !== 'string' || !/^[a-f\d]{64}$/.test(value.source_discussion_hash) || !date(value.created_at)
    || !text(value.model_identifier, 200) || !text(value.prompt_version, 200)
    || !Array.isArray(value.candidates) || value.candidates.length > 100) return false
  const source = Array.from(discussion)
  const ids = new Set()
  return value.candidates.every((candidate) => {
    if (!object(candidate) || !text(candidate.requirement_id, 200) || ids.has(candidate.requirement_id)
      || !text(candidate.requirement_text, 2000) || blank.test(candidate.requirement_text)
      || candidate.review_status !== 'unreviewed' || !Array.isArray(candidate.evidence)
      || candidate.evidence.length < 1 || candidate.evidence.length > 8) return false
    ids.add(candidate.requirement_id)
    if (!candidate.evidence.every((span) => object(span) && text(span.quote, 4000)
      && Number.isInteger(span.start) && Number.isInteger(span.end)
      && span.start >= 0 && span.end > span.start && span.end <= source.length
      && source.slice(span.start, span.end).join('') === span.quote)) return false
    return [['actor', 200], ['action', 500]].every(([field, max]) => candidate[field] === null
      || (text(candidate[field], max) && !blank.test(candidate[field])
        && candidate.evidence.some((span) => span.quote.includes(candidate[field]))))
  })
}
