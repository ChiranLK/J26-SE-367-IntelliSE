import assert from 'node:assert/strict'
import { test } from 'node:test'
import { deleteProject } from '../src/services/api.js'

const id = '507f1f77bcf86cd799439011'
test('DELETE uses exact project URL, no request body and accepts 204', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url.pathname, `/api/v1/component-1/projects/${id}`)
    assert.equal(options.method, 'DELETE')
    assert.equal(options.body, undefined)
    return new Response(null, { status: 204 })
  })
  assert.equal(await deleteProject(id), null)
})

test('invalid project ID never issues deletion', (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; return new Response(null, { status: 204 }) })
  assert.throws(() => deleteProject('bad'), { status: 422 })
  assert.equal(calls, 0)
})

test('database error or network timeout never automatically retries deletion', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; return Response.json({ detail: 'Persistence unavailable' }, { status: 503 }) })
  await assert.rejects(deleteProject(id), { status: 503, uncertain: true })
  assert.equal(calls, 1)
  t.mock.method(globalThis, 'fetch', async () => { calls++; throw new TypeError('offline') })
  await assert.rejects(deleteProject(id), { code: 'network', uncertain: true })
  assert.equal(calls, 2)
})

test('missing/old backend is an error; no optimistic false success', async (t) => {
  for (const status of [404, 405]) {
    t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Not Found' }, { status }))
    await assert.rejects(deleteProject(id), { status })
  }
  t.mock.method(globalThis, 'fetch', async () => Response.json(null))
  await assert.rejects(deleteProject(id), { code: 'invalid-response' })
})
