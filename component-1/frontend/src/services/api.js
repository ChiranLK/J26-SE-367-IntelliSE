const HEALTH_PATH = '/api/v1/component-1/health'
const DEFAULT_BASE_URL = import.meta.env?.VITE_API_BASE_URL ?? 'http://localhost:8001'

export class BackendConnectionError extends Error {
  constructor(message) {
    super(message)
    this.name = 'BackendConnectionError'
  }
}

export async function checkBackendHealth({
  baseUrl = DEFAULT_BASE_URL,
  signal,
  timeoutMs = 5000,
} = {}) {
  const controller = new AbortController()
  let timedOut = false
  const cancel = () => controller.abort(signal.reason)
  if (signal?.aborted) cancel()
  else signal?.addEventListener('abort', cancel, { once: true })

  const timeout = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  try {
    let url
    try {
      url = new URL(baseUrl)
    } catch {
      throw new BackendConnectionError('The backend URL is not configured correctly.')
    }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new BackendConnectionError('The backend URL is not configured correctly.')
    }
    url.pathname = `${url.pathname.replace(/\/+$/, '')}${HEALTH_PATH}`
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
      credentials: 'omit',
      cache: 'no-store',
    })
    if (!response.ok) {
      throw new BackendConnectionError(`The backend returned HTTP ${response.status}.`)
    }
    let data
    try {
      data = await response.json()
    } catch (error) {
      if (controller.signal.aborted) throw error
      throw new BackendConnectionError('The backend returned an invalid response.')
    }
    if (
      !data ||
      data.status !== 'ok' ||
      data.component !== 'component-1' ||
      data.service !== 'requirement-engineering'
    ) {
      throw new BackendConnectionError('The response does not match the Component 01 health contract.')
    }
    return data
  } catch (error) {
    if (signal?.aborted) throw error
    if (timedOut) throw new BackendConnectionError('The backend request timed out. Please retry.')
    if (error instanceof BackendConnectionError) throw error
    throw new BackendConnectionError('Could not reach the backend. It may be offline or blocked by CORS.')
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', cancel)
  }
}
