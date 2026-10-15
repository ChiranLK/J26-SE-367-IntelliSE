import { createHash } from 'node:crypto'
import { transcriptionJob } from './transcription-fixture.js'

// Compact fixture of the inspected backend OpenAPI. No provider/model behavior implied.
const properties = Object.fromEntries(['transcription_id', 'provider', 'model', 'language', 'original_transcript',
  'original_transcript_hash', 'reviewed_discussion_hash', 'segments', 'audio_duration_seconds', 'processing_seconds',
  'transcription_created_at', 'transcription_completed_at', 'review_recorded_at'].map((name) => [name, {}]))
export const provenanceContract = {
  openapi: '3.1.0', paths: {
    '/api/v1/component-1/projects': { post: {
      requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/ProjectCreate' } } } },
      responses: { 201: { content: { 'application/json': { schema: { $ref: '#/components/schemas/ProjectRecord' } } } } },
    } },
    '/api/v1/component-1/projects/{project_id}': { get: { responses: { 200: { content: { 'application/json': { schema: { $ref: '#/components/schemas/ProjectRecord' } } } } } } },
  }, components: { schemas: {
    ProjectCreate: { properties: { name: { type: 'string' }, discussion_text: { type: 'string' }, transcription_id: { anyOf: [{ type: 'string', format: 'uuid' }, { type: 'null' }] } } },
    ProjectRecord: { properties: { discussion_text: { type: 'string' }, transcription_provenance: { anyOf: [{ $ref: '#/components/schemas/TranscriptionProvenance' }, { type: 'null' }] } } },
    TranscriptionProvenance: { properties: { ...properties, schema_version: { const: 'c1-transcription-provenance-v1' }, review_status: { const: 'user_reviewed' } } },
  } },
}

export function projectProvenance(discussion, job = transcriptionJob(), recorded = job.updated_at) {
  const digest = (text) => createHash('sha256').update(text, 'utf8').digest('hex')
  return { schema_version: 'c1-transcription-provenance-v1', provider: 'whisper',
    transcription_id: job.transcription_id, model: job.model, language: job.language,
    original_transcript: job.original_transcript, original_transcript_hash: digest(job.original_transcript),
    reviewed_discussion_hash: digest(discussion), segments: job.segments,
    audio_duration_seconds: job.audio_duration_seconds, processing_seconds: job.processing_seconds,
    transcription_created_at: job.created_at, transcription_completed_at: job.updated_at,
    review_recorded_at: recorded, review_status: 'user_reviewed' }
}
