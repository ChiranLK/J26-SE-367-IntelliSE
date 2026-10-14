import { DEFAULT_BASE_URL } from './api.js'

const PREFIX = '/api/v1/component-1/projects'
const OBJECT_ID = /^[a-f0-9]{24}$/i
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const pendingClassifications = new Set()
const nonblank = (value) => typeof value === 'string' && Boolean(value.trim())
const validDate = (value) => typeof value === 'string' && Number.isFinite(Date.parse(value))

export class ProjectApiError extends Error {
  constructor(message, kind = 'error', status = null) {
    super(message)
    this.name = 'ProjectApiError'
    this.kind = kind
    this.status = status
  }
}

function invalid() {
  return new ProjectApiError('The backend response does not match the saved project contract.', 'invalid_response')
}

function projectPath(projectId) {
  if (!OBJECT_ID.test(projectId)) throw new ProjectApiError('Enter a valid 24-character project ID.', 'invalid_id')
  return `${PREFIX}/${projectId}`
}

function classificationPath(projectId, runId) {
  if (!UUID.test(runId)) throw invalid()
  return `${projectPath(projectId)}/extractions/${runId}/classifications`
}

async function request(path, { baseUrl = DEFAULT_BASE_URL, signal, method = 'GET', timeoutMs = 10000 } = {}) {
  const controller = new AbortController()
  let timedOut = false
  const cancel = () => controller.abort(signal.reason)
  if (signal?.aborted) cancel()
  else signal?.addEventListener('abort', cancel, { once: true })
  const timer = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)
  try {
    let url
    try { url = new URL(baseUrl) } catch { throw new ProjectApiError('The backend URL is not configured correctly.', 'configuration') }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new ProjectApiError('The backend URL is not configured correctly.', 'configuration')
    }
    const [pathname, query = ''] = path.split('?')
    url.pathname = `${url.pathname.replace(/\/+$/, '')}${pathname}`
    url.search = query
    const response = await fetch(url, { method, signal: controller.signal, credentials: 'omit', cache: 'no-store', headers: { Accept: 'application/json' } })
    let data
    try { data = await response.json() } catch (error) {
      if (controller.signal.aborted) throw error
      throw invalid()
    }
    if (!response.ok) {
      if (response.status === 404) {
        const kind = data?.detail === 'No classification found for this extraction run.' ? 'no_classification'
          : data?.detail === 'No extraction found for this project.' ? 'no_extraction' : 'not_found'
        throw new ProjectApiError('The requested saved record was not found.', kind, 404)
      }
      if (response.status === 503) {
        if (typeof data?.detail === 'string' && data.detail.startsWith('FR/NFR classifier unavailable.')) {
          throw new ProjectApiError('The FR/NFR model is unavailable. Ask the backend operator to check its trained model configuration.', 'model_unavailable', 503)
        }
        throw new ProjectApiError('Saved project data is unavailable. Check backend database availability.', 'unavailable', 503)
      }
      throw new ProjectApiError(`The backend returned HTTP ${response.status}.`, 'error', response.status)
    }
    return data
  } catch (error) {
    if (signal?.aborted) throw error
    if (timedOut) throw new ProjectApiError(method === 'POST'
      ? 'Classification timed out. It may still have been saved; check saved results before submitting again.'
      : 'Loading saved data timed out. Please retry.', 'timeout')
    if (error instanceof ProjectApiError) throw error
    throw new ProjectApiError(method === 'POST'
      ? 'The classification response could not be received. Check saved results before submitting again.'
      : 'Could not load saved data. Check the backend connection and CORS.', 'network')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', cancel)
  }
}

export async function listProjects({ offset = 0, ...options } = {}) {
  const data = await request(`${PREFIX}?limit=20&offset=${offset}`, options)
  if (!data || !Array.isArray(data.items) || data.offset !== offset || data.limit !== 20 || typeof data.has_more !== 'boolean'
      || data.items.some((p) => !p || !OBJECT_ID.test(p.id) || !nonblank(p.name))) throw invalid()
  return data
}

export async function getProject(projectId, options) {
  const data = await request(projectPath(projectId), options)
  if (!data || data.id !== projectId.toLowerCase() || !nonblank(data.name) || typeof data.discussion_text !== 'string') throw invalid()
  return data
}

export async function getLatestExtraction(projectId, options) {
  let data
  try { data = await request(`${projectPath(projectId)}/extractions/latest`, options) } catch (error) {
    if (error.kind === 'no_extraction') return null
    throw error
  }
  if (!data || data.project_id !== projectId.toLowerCase() || !UUID.test(data.run_id) || !Array.isArray(data.candidates)
      || data.candidates.some((c) => !c || !nonblank(c.requirement_id) || !nonblank(c.requirement_text))
      || new Set(data.candidates.map((c) => c.requirement_id)).size !== data.candidates.length) throw invalid()
  return data
}

export function classificationLabels(classification, extraction, projectId) {
  if (!classification || classification.project_id !== projectId.toLowerCase() || !nonblank(classification.classification_id)
      || !nonblank(classification.model_identifier) || !nonblank(classification.model_version)
      || !validDate(classification.classified_at) || !Array.isArray(classification.predictions)) throw invalid()
  if (classification.extraction_run_id !== extraction.run_id) {
    throw new ProjectApiError('These results belong to an older or different extraction run. Labels were not applied to the current requirements.', 'older_run')
  }
  const ids = new Set(extraction.candidates.map((c) => c.requirement_id))
  const labels = new Map()
  for (const prediction of classification.predictions) {
    if (!prediction || !ids.has(prediction.requirement_id) || labels.has(prediction.requirement_id) || !['FR', 'NFR'].includes(prediction.label)) throw invalid()
    labels.set(prediction.requirement_id, prediction.label)
  }
  if (labels.size !== ids.size) throw invalid()
  return labels
}

export async function getLatestClassification(projectId, extraction, options) {
  let data
  try { data = await request(`${classificationPath(projectId, extraction.run_id)}/latest`, options) } catch (error) {
    if (error.kind === 'no_classification') return null
    throw error
  }
  classificationLabels(data, extraction, projectId)
  return data
}

export async function classifyExtraction(projectId, extraction, options) {
  const path = classificationPath(projectId, extraction.run_id)
  if (pendingClassifications.has(path)) throw new ProjectApiError('Classification is already running for this extraction.', 'pending')
  pendingClassifications.add(path)
  try {
    const data = await request(path, { timeoutMs: 30000, ...options, method: 'POST' })
    classificationLabels(data, extraction, projectId)
    return data
  } finally { pendingClassifications.delete(path) }
}
