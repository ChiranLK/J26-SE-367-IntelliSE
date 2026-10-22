import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiError, createProject, extractRequirements, EXTRACTION_TIMEOUT_MS, getLatestExtraction, getProject, isNoExtraction, listProjects } from '../src/services/api.js'
import { characterCount, validateProjectInput, validExtraction } from '../src/services/contracts.js'
import { projectFromHash } from '../src/services/navigation.js'

const id = '507f1f77bcf86cd799439011'
const discussion = 'Hi 👋\r\nGuests must not delete reports.'
const quote = 'Guests must not delete reports.'
const start = Array.from(discussion).length - quote.length
const project = { id, name: 'Portal', description: null, status: 'draft', created_at: '2026-10-12T00:00:00Z', updated_at: '2026-10-12T00:00:00Z', discussion_text: discussion }
const run = { run_id: 'run-1', project_id: id, source_discussion_hash: 'a'.repeat(64), created_at: project.created_at, model_identifier: 'mock-model', prompt_version: 'c1-atomic-evidence-v1', candidates: [{ requirement_id: 'requirement-1', requirement_text: quote, actor: 'Guests', action: 'delete', review_status: 'unreviewed', evidence: [{ quote, start, end: start + quote.length }] }] }

test('create sends exact discussion and optional description with configured base URL', async (t) => {
  const input = { name: 'Portal', description: null, discussion_text: discussion }
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url.href, 'https://example.test/backend/api/v1/component-1/projects')
    assert.equal(options.method, 'POST')
    assert.equal(options.credentials, 'omit')
    assert.deepEqual(JSON.parse(options.body), input)
    return Response.json(project, { status: 201 })
  })
  assert.deepEqual(await createProject(input, { baseUrl: 'https://example.test/backend/' }), project)
})

test('list requests and verifies actual limit/offset/has_more pagination', async (t) => {
  const summary = { ...project }
  delete summary.discussion_text
  const page = { items: [summary], limit: 10, offset: 20, has_more: true }
  t.mock.method(globalThis, 'fetch', async (url) => {
    assert.equal(url.search, '?limit=10&offset=20')
    return Response.json(page)
  })
  assert.deepEqual(await listProjects({ limit: 10, offset: 20 }), page)
})

test('rejects invalid paging and malformed IDs before sending requests', (t) => {
  const fetch = t.mock.method(globalThis, 'fetch')
  for (const options of [{ limit: 0 }, { limit: 101 }, { offset: -1 }, { offset: 10001 }, { offset: 0.5 }]) {
    assert.throws(() => listProjects(options), ApiError)
  }
  assert.throws(() => getProject('bad-id'), ApiError)
  assert.equal(fetch.mock.callCount(), 0)
})

test('detail and latest GETs use canonical IDs and exact endpoints', async (t) => {
  const requests = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push([url.pathname, options.method])
    return Response.json(url.pathname.endsWith('/latest') ? run : project)
  })
  assert.deepEqual(await getProject(id.toUpperCase()), project)
  assert.deepEqual(await getLatestExtraction(id, discussion), run)
  assert.deepEqual(requests, [[`/api/v1/component-1/projects/${id}`, 'GET'], [`/api/v1/component-1/projects/${id}/extractions/latest`, 'GET']])
})

test('extraction is one bodyless POST and valid empty candidates are accepted', async (t) => {
  const empty = { ...run, candidates: [] }
  const fetch = t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url.pathname, `/api/v1/component-1/projects/${id}/extractions`)
    assert.equal(options.method, 'POST')
    assert.equal(options.body, undefined)
    return Response.json(empty, { status: 201 })
  })
  assert.deepEqual(await extractRequirements(id, discussion), empty)
  assert.equal(fetch.mock.callCount(), 1)
  assert.ok(EXTRACTION_TIMEOUT_MS > 180000)
})

test('only missing-run 404 represents no extraction yet', async (t) => {
  for (const detail of ['No extraction found for this project.', 'Project not found.']) {
    const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail }, { status: 404 }))
    await assert.rejects(getLatestExtraction(id, discussion), (error) => isNoExtraction(error) === detail.startsWith('No extraction'))
    fetch.mock.restore()
  }
})

test('FastAPI validation details report fields and messages without echoing input', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: [{ loc: ['body', 'name'], msg: 'Too long', input: 'private client input' }] }, { status: 422 }))
  await assert.rejects(createProject({}), (error) => error.status === 422 && error.message.includes('name: Too long') && !error.message.includes('private client input'))
})

test('HTTP provider and database failures never retry extraction', async (t) => {
  for (const status of [413, 502, 503, 504]) {
    const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Unavailable test fixture.' }, { status }))
    await assert.rejects(extractRequirements(id, discussion), (error) => error.status === status && error.message.includes('Unavailable test fixture.'))
    assert.equal(fetch.mock.callCount(), 1)
    fetch.mock.restore()
  }
})

test('timeout and network failure mark POST completion uncertain; no automatic retry', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true })
  }))
  await assert.rejects(extractRequirements(id, discussion, { timeoutMs: 15 }), (error) => error.code === 'timeout' && error.uncertain)
  assert.equal(fetch.mock.callCount(), 1)
  fetch.mock.restore()
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('private driver message') })
  await assert.rejects(extractRequirements(id, discussion), (error) => error.uncertain && !error.message.includes('private driver message'))
})

test('malformed project pages and mismatched IDs are rejected', async (t) => {
  for (const data of [null, {}, { ...project, id: 'bad' }, { ...project, status: 'approved' }]) {
    const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(data))
    await assert.rejects(getProject(id), /invalid response/)
    fetch.mock.restore()
  }
  t.mock.method(globalThis, 'fetch', async () => Response.json({ items: [], limit: 10, offset: 100, has_more: false }))
  await assert.rejects(listProjects(), /invalid response/)
})

test('evidence validation uses Unicode characters, supports multiple spans and rejects altered offsets', () => {
  assert.equal(validExtraction(run, id, discussion), true)
  const multiple = structuredClone(run)
  multiple.candidates[0].evidence.push({ quote: 'Hi 👋\r\n', start: 0, end: 6 })
  assert.equal(validExtraction(multiple, id, discussion), true)
  for (const change of [{ quote: 'invented' }, { start: start + 1 }, { end: 999 }, { start: '6' }]) {
    const invalid = structuredClone(run)
    Object.assign(invalid.candidates[0].evidence[0], change)
    assert.equal(validExtraction(invalid, id, discussion), false)
  }
  assert.equal(run.candidates[0].requirement_text, 'Guests must not delete reports.')
})

test('malformed model results and incorrect review status never become successful extractions', async (t) => {
  for (const change of [{ candidates: null }, { project_id: 'another-project' }, { candidates: [{ ...run.candidates[0], review_status: 'approved' }] }, { candidates: [...run.candidates, ...run.candidates] }]) {
    const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ ...run, ...change }))
    await assert.rejects(extractRequirements(id, discussion), (error) => error.code === 'invalid-response' && error.uncertain)
    fetch.mock.restore()
  }
})

test('input validation follows backend Unicode limits and preserves source text', () => {
  const input = { name: '👋'.repeat(120), description: '', discussion_text: ' \r\nExact discussion.\t ' }
  assert.deepEqual(validateProjectInput(input), {})
  assert.equal(characterCount(input.name), 120)
  assert.equal(validateProjectInput({ ...input, name: '👋'.repeat(121) }).name, 'Use 120 characters or fewer.')
  for (const name of [' ', '\u0085', '\u001c']) assert.ok(validateProjectInput({ ...input, name }).name)
  assert.ok(validateProjectInput({ ...input, discussion_text: '\t\n' }).discussion_text)
  assert.ok(validateProjectInput({ ...input, description: 'x'.repeat(2001) }).description)
  assert.ok(validateProjectInput({ ...input, discussion_text: 'x'.repeat(100001) }).discussion_text)
  assert.equal(input.discussion_text, ' \r\nExact discussion.\t ')
})

test('project URL fragments can be restored after refresh', () => {
  assert.equal(projectFromHash(`#projects/${id}`), id)
  assert.equal(projectFromHash('#new-project'), null)
  assert.equal(projectFromHash(''), null)
})


test('confirmed provider timeout permits explicit recovery without an uncertain-save lock', async (t) => {
  let calls = 0
  const detail = 'Requirement extraction provider timed out. Check server performance, model load time and C1_LLM_TIMEOUT_SECONDS. No automatic retry was attempted.'
  t.mock.method(globalThis, 'fetch', async () => { calls++; return Response.json({ detail }, { status: 504 }) })
  await assert.rejects(extractRequirements(id, discussion), error => error.status === 504 && error.code === 'extraction-timeout' && !error.uncertain)
  assert.equal(calls, 1)
})

test('unknown gateway timeout still requires retrieval because persistence is uncertain', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Gateway timed out' }, { status: 504 }))
  await assert.rejects(extractRequirements(id, discussion), error => error.status === 504 && error.uncertain)
})
