import assert from 'node:assert/strict'
import { test } from 'node:test'
import { checkBackendHealth } from '../src/services/api.js'

const health = { status: 'ok', component: 'component-1', service: 'requirement-engineering' }

test('accepts the contract and builds the exact health URL', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url.href, 'http://localhost:8001/api/v1/component-1/health')
    assert.equal(options.credentials, 'omit')
    return Response.json(health)
  })
  assert.deepEqual(await checkBackendHealth({ baseUrl: 'http://localhost:8001/' }), health)
})

test('rejects HTTP errors', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 503 }))
  await assert.rejects(checkBackendHealth(), /HTTP 503/)
})

test('rejects non-JSON responses', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<html>not an API</html>'))
  await assert.rejects(checkBackendHealth(), /invalid response/)
})

test('rejects incorrect and incomplete contracts', async (t) => {
  for (const data of [null, {}, { ...health, status: 'ready' }, { ...health, component: 'component-3' }, { ...health, service: 'other' }]) {
    const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(data))
    await assert.rejects(checkBackendHealth(), /health contract/)
    mock.mock.restore()
  }
})

test('reports unreachable backend', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch') })
  await assert.rejects(checkBackendHealth(), /Could not reach the backend/)
})

function waitForAbort(_url, { signal }) {
  return new Promise((_resolve, reject) => {
    if (signal.aborted) reject(signal.reason)
    else signal.addEventListener('abort', () => reject(signal.reason), { once: true })
  })
}

test('times out pending requests', async (t) => {
  t.mock.method(globalThis, 'fetch', waitForAbort)
  await assert.rejects(checkBackendHealth({ timeoutMs: 15 }), /timed out/)
})

test('supports cancellation for cleanup', async (t) => {
  t.mock.method(globalThis, 'fetch', waitForAbort)
  const controller = new AbortController()
  const pending = checkBackendHealth({ signal: controller.signal })
  controller.abort()
  await assert.rejects(pending, { name: 'AbortError' })
})

test('rejects invalid configuration before requesting', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => Response.json(health))
  for (const baseUrl of ['', 'invalid', 'ftp://localhost', 'http://user:password@localhost', 'http://localhost?key=value']) {
    await assert.rejects(checkBackendHealth({ baseUrl }), /not configured correctly/)
  }
  assert.equal(fetchMock.mock.callCount(), 0)
})
