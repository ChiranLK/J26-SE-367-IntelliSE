import assert from 'node:assert/strict'
import { test } from 'node:test'
import { checkProjectProvenanceContract, createProject, getProject } from '../src/services/api.js'
import { supportsProjectProvenance, verifyProjectProvenance } from '../src/services/projectProvenance.js'
import { validProject } from '../src/services/contracts.js'
import { provenanceContract, projectProvenance } from './project-provenance-fixture.js'
import { transcriptionId } from './transcription-fixture.js'

const input = { name: 'Reviewed project', description: 'Kept', discussion_text: ' \r\nReviewed Café 👋 text.\t ', transcription_id: transcriptionId() }
const saved = () => ({ id: 'a'.repeat(24), name: input.name, description: input.description, discussion_text: input.discussion_text,
  status: 'draft', created_at: '2026-10-15T00:00:00Z', updated_at: '2026-10-15T00:00:00Z',
  transcription_provenance: projectProvenance(input.discussion_text) })

test('recognizes actual OpenAPI references/nullable provenance, rejects older or incomplete contracts', () => {
  assert.equal(supportsProjectProvenance(provenanceContract), true)
  for (const doc of [null, {}, { paths: {} }, { ...provenanceContract, components: {} }]) assert.equal(supportsProjectProvenance(doc), false)
  const doc = structuredClone(provenanceContract)
  delete doc.components.schemas.TranscriptionProvenance.properties.original_transcript_hash
  assert.equal(supportsProjectProvenance(doc), false)
})

test('loads OpenAPI from the configured deployment root', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => {
    assert.equal(url.href, 'http://localhost:8001/backend/openapi.json')
    return Response.json(provenanceContract)
  })
  assert.equal(await checkProjectProvenanceContract({ baseUrl: 'http://localhost:8001/backend/' }), true)
})

test('sends only reviewed text and reference; checks capability before audio save', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push(options.method)
    if (url.pathname.endsWith('/openapi.json')) return Response.json(provenanceContract)
    assert.deepEqual(JSON.parse(options.body), input)
    assert.equal(options.method, 'POST')
    return Response.json(saved(), { status: 201 })
  })
  assert.deepEqual(await createProject(input), saved())
  assert.deepEqual(calls, ['GET', 'POST'])
})

test('missing contract never causes an audio request or a text-only fallback', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json({ paths: {} }))
  await assert.rejects(createProject(input), (error) => error.code === 'provenance-unavailable')
  assert.equal(mock.mock.callCount(), 1)
})

test('failed capability lookup never submits a project', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Unavailable' }, { status: 503 }))
  await assert.rejects(createProject(input), /503/)
  assert.equal(mock.mock.callCount(), 1)
})

for (const status of [404, 409, 422]) test(`reference HTTP ${status} is surfaced without retry or dropping provenance`, async (t) => {
  let posts = 0
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    if (options.method === 'GET') return Response.json(provenanceContract)
    posts++
    assert.equal(JSON.parse(options.body).transcription_id, input.transcription_id)
    return Response.json({ detail: 'Reference rejected.' }, { status })
  })
  await assert.rejects(createProject(input), (error) => error.status === status)
  assert.equal(posts, 1)
})

test('missing or mismatched saved provenance cannot be accepted as a successful audio save', async (t) => {
  for (const change of [{ transcription_provenance: undefined },
    { transcription_provenance: { ...saved().transcription_provenance, transcription_id: transcriptionId(2) } },
    { discussion_text: 'Wrong discussion' }]) {
    const mock = t.mock.method(globalThis, 'fetch', async (_url, options) => options.method === 'GET'
      ? Response.json(provenanceContract) : Response.json({ ...saved(), ...change }, { status: 201 }))
    await assert.rejects(createProject(input), (error) => error.code === 'invalid-response' && error.uncertain)
    mock.mock.restore()
  }
})

test('validates separate UTF-8 hashes without normalizing review text', async () => {
  assert.equal(await verifyProjectProvenance(saved()), true)
  assert.equal(await verifyProjectProvenance({ ...saved(), discussion_text: input.discussion_text.trim() }), false)
  assert.equal(await verifyProjectProvenance({ ...saved(), transcription_provenance: { ...saved().transcription_provenance, original_transcript: 'Changed original' } }), false)
})

test('reopening rejects corrupt hashes instead of silently showing a text-only project', async (t) => {
  const project = saved()
  project.transcription_provenance.original_transcript_hash = 'a'.repeat(64)
  t.mock.method(globalThis, 'fetch', async () => Response.json(project))
  await assert.rejects(getProject(project.id), /invalid response/)
})

test('text-only creation does not require OpenAPI and preserves its payload/response', async (t) => {
  const plain = { ...saved() }
  delete plain.transcription_provenance
  const payload = { name: input.name, description: input.description, discussion_text: input.discussion_text }
  const mock = t.mock.method(globalThis, 'fetch', async (_url, options) => {
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), payload)
    return Response.json(plain, { status: 201 })
  })
  assert.deepEqual(await createProject(payload), plain)
  assert.equal(mock.mock.callCount(), 1)
})

test('invalid provenance versions/statuses are rejected without discarding the source', () => {
  for (const changed of [{ schema_version: 'v999' }, { review_status: 'verified' }, { segments: 'bad' }]) {
    assert.equal(validProject({ ...saved(), transcription_provenance: { ...saved().transcription_provenance, ...changed } }), false)
  }
})
