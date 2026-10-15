import { validTranscriptionId } from './transcriptionContracts.js'

const PREFIX = '/api/v1/component-1/projects'
const fields = ['schema_version', 'transcription_id', 'provider', 'model', 'language', 'original_transcript',
  'original_transcript_hash', 'reviewed_discussion_hash', 'segments', 'audio_duration_seconds',
  'processing_seconds', 'transcription_created_at', 'transcription_completed_at', 'review_recorded_at', 'review_status']

// Resolve only local OpenAPI references; no network traversal or execution.
export function supportsProjectProvenance(document) {
  function resolve(value, depth = 0) {
    if (!value || depth > 12) return null
    if (value.$ref) {
      if (!value.$ref.startsWith('#/')) return null
      const target = value.$ref.slice(2).split('/').reduce((node, key) => node?.[key.replace(/~1/g, '/').replace(/~0/g, '~')], document)
      return resolve(target, depth + 1)
    }
    if (value.anyOf) return resolve(value.anyOf.find((item) => item.type !== 'null'), depth + 1)
    return value
  }
  const input = resolve(document?.paths?.[PREFIX]?.post?.requestBody?.content?.['application/json']?.schema)
  const output = resolve(document?.paths?.[PREFIX]?.post?.responses?.['201']?.content?.['application/json']?.schema)
  const detail = resolve(document?.paths?.[`${PREFIX}/{project_id}`]?.get?.responses?.['200']?.content?.['application/json']?.schema)
  const id = resolve(input?.properties?.transcription_id)
  return Boolean(id?.type === 'string' && id.format === 'uuid'
    && ['name', 'discussion_text'].every((key) => input?.properties?.[key])
    && [output, detail].every((record) => {
      const provenance = resolve(record?.properties?.transcription_provenance)
      return record?.properties?.discussion_text && fields.every((key) => provenance?.properties?.[key])
        && resolve(provenance.properties.schema_version)?.const === 'c1-transcription-provenance-v1'
        && resolve(provenance.properties.review_status)?.const === 'user_reviewed'
    }))
}

const date = (value) => typeof value === 'string' && /(Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
const hash = (value) => typeof value === 'string' && /^[a-f\d]{64}$/.test(value)
const text = (value, max) => typeof value === 'string' && Array.from(value).length <= max

export function validProjectProvenance(p) {
  return Boolean(p && p.schema_version === 'c1-transcription-provenance-v1' && p.provider === 'whisper'
    && validTranscriptionId(p.transcription_id) && p.review_status === 'user_reviewed' && p.language === 'en'
    && text(p.model, 200) && p.model.trim() && text(p.original_transcript, 40000) && p.original_transcript.trim()
    && hash(p.original_transcript_hash) && hash(p.reviewed_discussion_hash)
    && Number.isFinite(p.audio_duration_seconds) && p.audio_duration_seconds > 0
    && Number.isFinite(p.processing_seconds) && p.processing_seconds >= 0
    && ['transcription_created_at', 'transcription_completed_at', 'review_recorded_at'].every((key) => date(p[key]))
    && Array.isArray(p.segments) && p.segments.length <= 500 && p.segments.every((s) => s
      && Number.isFinite(s.start) && s.start >= 0 && Number.isFinite(s.end) && s.end >= s.start
      && s.end <= p.audio_duration_seconds + .5 && text(s.text, 10000)))
}

export async function verifyProjectProvenance(project) {
  const p = project.transcription_provenance
  if (p == null) return true
  if (!validProjectProvenance(p) || !globalThis.crypto?.subtle) return false
  const digest = async (text) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))), (b) => b.toString(16).padStart(2, '0')).join('')
  return p.original_transcript_hash === await digest(p.original_transcript)
    && p.reviewed_discussion_hash === await digest(project.discussion_text)
}
