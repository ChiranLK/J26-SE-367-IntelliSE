import assert from 'node:assert/strict'
import { test } from 'node:test'
import { classifyExtraction, classificationLabels, getLatestClassification, getLatestExtraction, getProject, listProjects } from '../src/services/projectApi.js'

const projectId = '507f1f77bcf86cd799439011'
const runId = '7318a782-26cc-4608-9be8-9158aab5bdcf'
const extraction = { project_id: projectId, run_id: runId, candidates: [
  { requirement_id: 'req-one', requirement_text: 'Members can upload reports.' },
  { requirement_id: 'req-two', requirement_text: 'Reports must load within two seconds.' },
] }
const classification = { classification_id: 'fixture-classification', project_id: projectId, extraction_run_id: runId,
  model_identifier: 'tfidf-logistic-regression', model_version: 'a'.repeat(64), classified_at: '2026-10-14T14:00:00Z',
  predictions: [{ requirement_id: 'req-two', label: 'NFR' }, { requirement_id: 'req-one', label: 'FR' }] }

test('project requests use the real pagination query and preserve discussion text', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(options.credentials, 'omit')
    assert.equal(options.cache, 'no-store')
    if (!calls++) {
      assert.equal(url.href, 'http://localhost:8001/api/v1/component-1/projects?limit=20&offset=20')
      return Response.json({ items: [{ id: projectId, name: 'Fixture project' }], limit: 20, offset: 20, has_more: false })
    }
    assert.equal(url.pathname, `/api/v1/component-1/projects/${projectId}`)
    return Response.json({ id: projectId, name: 'Fixture project', discussion_text: 'Original fixture discussion.' })
  })
  assert.equal((await listProjects({ offset: 20 })).items[0].id, projectId)
  assert.equal((await getProject(projectId)).discussion_text, 'Original fixture discussion.')
})

test('explicit POST addresses the saved extraction; predictions map by ID, not position', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url.pathname, `/api/v1/component-1/projects/${projectId}/extractions/${runId}/classifications`)
    assert.equal(options.method, 'POST')
    assert.equal(options.body, undefined)
    return Response.json(classification, { status: 201 })
  })
  const labels = classificationLabels(await classifyExtraction(projectId, extraction), extraction, projectId)
  assert.equal(labels.get('req-one'), 'FR')
  assert.equal(labels.get('req-two'), 'NFR')
})

test('reopening retrieves saved classification for the exact extraction', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(options.method, 'GET')
    assert.equal(url.pathname, `/api/v1/component-1/projects/${projectId}/extractions/${runId}/classifications/latest`)
    return Response.json(classification)
  })
  assert.deepEqual(await getLatestClassification(projectId, extraction), classification)
  assert.deepEqual(await getLatestClassification(projectId, extraction), classification)
})

test('only the matching 404 details mean empty extraction or classification', async (t) => {
  let detail = 'No extraction found for this project.'
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail }, { status: 404 }))
  assert.equal(await getLatestExtraction(projectId), null)
  detail = 'No classification found for this extraction run.'
  assert.equal(await getLatestClassification(projectId, extraction), null)
  detail = 'Extraction run not found for this project.'
  await assert.rejects(getLatestClassification(projectId, extraction), { kind: 'not_found' })
})

test('valid empty extraction and saved empty predictions are supported', async (t) => {
  const empty = { ...extraction, candidates: [] }
  t.mock.method(globalThis, 'fetch', async () => Response.json(empty))
  assert.deepEqual(await getLatestExtraction(projectId), empty)
  assert.equal(classificationLabels({ ...classification, predictions: [] }, empty, projectId).size, 0)
})

test('rejects older extraction results even with matching requirement IDs', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ ...classification, extraction_run_id: 'another-run' }))
  await assert.rejects(getLatestClassification(projectId, extraction), { kind: 'older_run' })
})

test('rejects wrong project, incomplete ID mapping, duplicates, unknown labels and bad metadata', () => {
  for (const change of [
    { project_id: 'another-project' }, { model_identifier: '' }, { classified_at: 'not a date' },
    { predictions: [] }, { predictions: [{ requirement_id: 'req-one', label: 'FR' }] },
    { predictions: [{ requirement_id: 'req-one', label: 'FR' }, { requirement_id: 'req-one', label: 'FR' }] },
    { predictions: [{ requirement_id: 'invented-id', label: 'FR' }, classification.predictions[0]] },
    { predictions: [{ requirement_id: 'req-one', label: 'unsupported' }, classification.predictions[0]] },
  ]) assert.throws(() => classificationLabels({ ...classification, ...change }, extraction, projectId), { kind: 'invalid_response' })
})

test('model unavailable is distinct from database unavailable', async (t) => {
  let detail = 'FR/NFR classifier unavailable. Configure a trusted locally trained research model and matching baseline dependencies.'
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail }, { status: 503 }))
  await assert.rejects(classifyExtraction(projectId, extraction), { kind: 'model_unavailable' })
  detail = 'Project persistence is unavailable. Check MongoDB configuration and availability.'
  await assert.rejects(getLatestClassification(projectId, extraction), { kind: 'unavailable' })
})

test('in-flight duplicate protection sends one POST and releases after completion', async (t) => {
  let finish
  const mock = t.mock.method(globalThis, 'fetch', () => new Promise((resolve) => { finish = resolve }))
  const first = classifyExtraction(projectId, extraction)
  await assert.rejects(classifyExtraction(projectId, extraction), { kind: 'pending' })
  assert.equal(mock.mock.callCount(), 1)
  finish(Response.json(classification))
  await first
  const next = classifyExtraction(projectId, extraction)
  finish(Response.json(classification))
  await next
  assert.equal(mock.mock.callCount(), 2)
})

test('network failure releases guard without automatic retries', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Network failed') })
  await assert.rejects(classifyExtraction(projectId, extraction), { kind: 'network' })
  assert.equal(mock.mock.callCount(), 1)
  await assert.rejects(classifyExtraction(projectId, extraction), { kind: 'network' })
  assert.equal(mock.mock.callCount(), 2)
})

function waitForAbort(_url, { signal }) {
  return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }))
}

test('timeout warns about ambiguous persistence without retrying', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', waitForAbort)
  await assert.rejects(classifyExtraction(projectId, extraction, { timeoutMs: 10 }), /may still have been saved/)
  assert.equal(mock.mock.callCount(), 1)
})

test('read cancellation preserves AbortError for stale-response suppression', async (t) => {
  t.mock.method(globalThis, 'fetch', waitForAbort)
  const controller = new AbortController()
  const promise = getLatestClassification(projectId, extraction, { signal: controller.signal })
  controller.abort()
  await assert.rejects(promise, { name: 'AbortError' })
})

test('invalid configuration and malformed JSON never supply fake results', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response('<html>invalid</html>'))
  await assert.rejects(getProject('invalid'), { kind: 'invalid_id' })
  await assert.rejects(getProject(projectId, { baseUrl: 'http://user:secret@localhost' }), { kind: 'configuration' })
  assert.equal(mock.mock.callCount(), 0)
  await assert.rejects(getLatestClassification(projectId, extraction), { kind: 'invalid_response' })
})
