import assert from 'node:assert/strict'
import { test } from 'node:test'
import { once } from 'node:events'
import { createServer } from 'node:http'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { classifyRequirement } from '../src/services/api.js'
import { createModelRunner, modelMiddleware, ModelError, MODEL_PATH } from '../scripts/local-model-plugin.mjs'

const text = 'Search results shall appear within two seconds.'
const prediction = { requirement_text: text, label: 'NFR', model_identifier: 'tfidf-logistic-regression', model_version: 'a'.repeat(64), classified_at: '2026-10-15T00:00:00Z', processing_seconds: 0.04 }
const baseUrl = 'http://localhost:5173'

test('single-requirement client sends exact text only to the local adapter', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url.href, baseUrl + MODEL_PATH)
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), { requirement_text: text })
    return Response.json(prediction)
  })
  assert.deepEqual(await classifyRequirement(text, { baseUrl }), prediction)
})

test('invalid requirement is rejected before inference', (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => assert.fail('No request expected'))
  for (const value of ['', ' \n ', null, 'x'.repeat(5001)]) assert.throws(() => classifyRequirement(value, { baseUrl }), /between 1 and 5,000/)
  assert.equal(fetch.mock.callCount(), 0)
})

test('mismatched text, invented labels and invalid metadata never become a displayed result', async (t) => {
  for (const response of [null, { ...prediction, requirement_text: 'Other input' }, { ...prediction, label: 'BERT' }, { ...prediction, model_version: '' }, { ...prediction, model_identifier: 'other-model' }, { ...prediction, processing_seconds: -1 }]) {
    const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(response))
    await assert.rejects(classifyRequirement(text, { baseUrl }), /invalid response/)
    fetch.mock.restore()
  }
})

test('unavailable model is actionable and never automatically retried', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Local model unavailable.' }, { status: 503 }))
  await assert.rejects(classifyRequirement(text, { baseUrl }), /Local model unavailable/)
  assert.equal(fetch.mock.callCount(), 1)
})

test('local adapter validates input, rejects cross-origin calls and propagates worker errors', async (t) => {
  let calls = 0
  const server = createServer(modelMiddleware({ predict: async (value) => {
    calls++
    assert.equal(value, text)
    if (calls === 2) throw new ModelError(429, 'Model busy.')
    return prediction
  } }))
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  t.after(() => { server.closeAllConnections(); server.close() })
  const url = `http://127.0.0.1:${server.address().port}${MODEL_PATH}`
  const post = (body, headers = {}) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) })
  assert.equal((await post({ requirement_text: ' ' })).status, 422)
  assert.equal((await post({ requirement_text: text, model: 'fake' })).status, 422)
  assert.equal((await post({ requirement_text: text }, { Origin: 'https://other.test' })).status, 403)
  assert.equal(calls, 0)
  assert.deepEqual(await (await post({ requirement_text: text })).json(), prediction)
  assert.equal((await post({ requirement_text: text })).status, 429)
})

// A pipe fixture verifies lifecycle/protocol behavior, not real model accuracy.
async function fixtureWorker(t, source, timeoutMs = 1000) {
  const dir = await mkdtemp(join(tmpdir(), 'c1-model-worker-'))
  const workerPath = join(dir, 'worker.mjs')
  await writeFile(workerPath, source)
  const runner = createModelRunner({ python: process.execPath, workerPath, modelDir: 'unused-fixture', timeoutMs })
  t.after(async () => { runner.close(); await rm(dir, { recursive: true, force: true }) })
  return runner
}

test('worker is reused and rejects simultaneous submissions', async (t) => {
  const runner = await fixtureWorker(t, `import readline from 'node:readline'; let count=0; readline.createInterface({input:process.stdin}).on('line', () => setTimeout(() => console.log(JSON.stringify({ count: ++count })), 20))`)
  const first = runner.predict(text)
  await assert.rejects(runner.predict(text), { status: 429 })
  assert.equal((await first).count, 1)
  assert.equal((await runner.predict(text)).count, 2)
})

test('worker timeout terminates the request without retrying', async (t) => {
  const runner = await fixtureWorker(t, 'process.stdin.resume()', 30)
  await assert.rejects(runner.predict(text), { status: 504 })
})

test('invalid worker output fails cleanly without exposing source or paths', async (t) => {
  const runner = await fixtureWorker(t, `process.stdin.once('data', () => console.log('null'))`)
  await assert.rejects(runner.predict(text), (error) => error.status === 503 && !error.message.includes(text) && !error.message.includes(tmpdir()))
})

test('missing interpreter is reported as model unavailable', async (t) => {
  const runner = createModelRunner({ python: '/nonexistent/c1-test-python' })
  t.after(() => runner.close())
  await assert.rejects(runner.predict(text), { status: 503 })
})
