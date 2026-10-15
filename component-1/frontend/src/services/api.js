import { MAX_OFFSET, validExtraction, validProject, validProjectId, validProjectPage } from './contracts.js'
import { validJobAccepted, validTranscription, validTranscriptionId, validateAudioFile } from './transcriptionContracts.js'
import { supportsProjectProvenance, verifyProjectProvenance } from './projectProvenance.js'

const PREFIX = '/api/v1/component-1'
export const DEFAULT_BASE_URL = import.meta.env?.VITE_API_BASE_URL ?? 'http://localhost:8001'
export const EXTRACTION_TIMEOUT_MS = 200000 // Backend provider permits up to 180 seconds, plus persistence.

export class BackendConnectionError extends Error {
  constructor(message) {
    super(message)
    this.name = 'BackendConnectionError'
  }
}

export class ApiError extends BackendConnectionError {
  constructor(message, { status = null, detail = null, code = 'http', uncertain = false } = {}) {
    super(message)
    this.name = 'ApiError'
    Object.assign(this, { status, detail, code, uncertain })
  }
}

function errorDetail(detail) {
  if (typeof detail === 'string') return detail.slice(0, 600)
  if (Array.isArray(detail)) return detail.slice(0, 5).map((item) => {
    const field = Array.isArray(item?.loc) ? item.loc.filter((part) => part !== 'body').join('.') : ''
    return `${field ? `${field}: ` : ''}${typeof item?.msg === 'string' ? item.msg.slice(0, 160) : 'Invalid input.'}`
  }).join(' ')
  return ''
}

async function request(path, {
  baseUrl = DEFAULT_BASE_URL, signal, timeoutMs = 15000, method = 'GET', body,
  validate = () => true, query = {}, componentPath = true,
} = {}) {
  const controller = new AbortController()
  let timedOut = false
  const cancel = () => controller.abort(signal.reason)
  if (signal?.aborted) cancel()
  else signal?.addEventListener('abort', cancel, { once: true })
  const timeout = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)
  const writing = method === 'POST'
  try {
    let url
    try { url = new URL(baseUrl) } catch { throw new ApiError('The backend URL is not configured correctly.', { code: 'config' }) }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new ApiError('The backend URL is not configured correctly.', { code: 'config' })
    }
    url.pathname = `${url.pathname.replace(/\/+$/, '')}${componentPath ? PREFIX : ''}${path}`
    for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value)
    const multipart = body instanceof FormData
    const response = await fetch(url, {
      method, signal: controller.signal, credentials: 'omit', cache: 'no-store',
      headers: { Accept: 'application/json', ...(body === undefined || multipart ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: multipart ? body : JSON.stringify(body) }),
    })
    let data
    try { data = await response.json() } catch (error) {
      if (controller.signal.aborted) throw error
      if (!response.ok) throw new ApiError(`The backend returned HTTP ${response.status}.`, {
        status: response.status, uncertain: writing && response.status >= 500,
      })
      throw new ApiError('The backend returned an invalid response.', { code: 'invalid-response', uncertain: writing })
    }
    if (!response.ok) {
      const detail = errorDetail(data?.detail)
      throw new ApiError(`The backend returned HTTP ${response.status}.${detail ? ` ${detail}` : ''}`, {
        status: response.status, detail: data?.detail,
        uncertain: writing && response.status >= 500 && response.status !== 502,
      })
    }
    if (!await validate(data)) throw new ApiError('The backend returned an invalid response.', { code: 'invalid-response', uncertain: writing })
    return data
  } catch (error) {
    if (signal?.aborted) throw error
    if (timedOut) throw new ApiError('The backend request timed out.', { code: 'timeout', uncertain: writing })
    if (error instanceof BackendConnectionError) throw error
    throw new ApiError('Could not reach the backend. It may be offline or blocked by CORS.', { code: 'network', uncertain: writing })
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', cancel)
  }
}

export async function checkBackendHealth(options = {}) {
  const data = await request('/health', { timeoutMs: 5000, ...options })
  if (!data || data.status !== 'ok' || data.component !== 'component-1' || data.service !== 'requirement-engineering') {
    throw new BackendConnectionError('The response does not match the Component 01 health contract.')
  }
  return data
}

function projectPath(id) {
  if (!validProjectId(id)) throw new ApiError('The project ID must contain 24 hexadecimal characters.', { status: 422 })
  return `/projects/${id.toLowerCase()}`
}

export async function checkProjectProvenanceContract(options = {}) {
  const schema = await request('/openapi.json', { ...options, componentPath: false })
  return supportsProjectProvenance(schema)
}

export async function createProject(input, options = {}) {
  if (input.transcription_id != null) {
    if (!validTranscriptionId(input.transcription_id)) throw new ApiError('Invalid transcription job ID.', { status: 422 })
    if (!await checkProjectProvenanceContract(options)) throw new ApiError('This backend cannot save transcription provenance. Your discussion and source reference are retained.', { code: 'provenance-unavailable' })
  }
  return request('/projects', { ...options, method: 'POST', body: input, validate: async (data) =>
    validProject(data) && await verifyProjectProvenance(data)
    && (input.transcription_id == null || (data.transcription_provenance?.transcription_id === input.transcription_id
      && data.discussion_text === input.discussion_text)) })
}

export function listProjects({ limit = 10, offset = 0, ...options } = {}) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100 || !Number.isInteger(offset) || offset < 0 || offset > MAX_OFFSET) {
    throw new ApiError('Invalid project pagination.', { status: 422 })
  }
  return request('/projects', { ...options, query: { limit, offset }, validate: (data) => validProjectPage(data, limit, offset) })
}

export const getProject = (id, options = {}) => request(projectPath(id), { ...options, validate: async (data) => validProject(data) && data.id === id.toLowerCase() && await verifyProjectProvenance(data) })
export const extractRequirements = (id, discussion, options = {}) => request(`${projectPath(id)}/extractions`, {
  timeoutMs: EXTRACTION_TIMEOUT_MS, ...options, method: 'POST', validate: (data) => validExtraction(data, id, discussion),
})
export const getLatestExtraction = (id, discussion, options = {}) => request(`${projectPath(id)}/extractions/latest`, {
  ...options, validate: (data) => validExtraction(data, id, discussion),
})

// Only this exact 404 detail means "no extraction yet"; missing projects remain errors.
export const isNoExtraction = (error) => error instanceof ApiError && error.status === 404
  && error.detail === 'No extraction found for this project.'

export function transcribeAudio(file, options = {}) {
  const invalid = validateAudioFile(file)
  if (invalid) throw new ApiError(invalid, { code: 'audio-input' })
  const body = new FormData()
  body.append('audio', file, file.name)
  return request('/transcriptions', { timeoutMs: 60000, ...options, method: 'POST', body, validate: validJobAccepted })
}

export function getTranscription(id, options = {}) {
  if (!validTranscriptionId(id)) throw new ApiError('Invalid transcription job ID.', { status: 422 })
  return request(`/transcriptions/${id}`, { ...options, validate: (data) => validTranscription(data, id) })
}
