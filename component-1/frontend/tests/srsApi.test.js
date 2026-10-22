import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { test } from 'node:test'
import { getSrs, saveSrsAction, srsText, validSrsState } from '../src/services/srsApi.js'

const projectId = '507f1f77bcf86cd799439011'
const version = { version_id: randomUUID(), version_number: 1, parent_version_id: null, project_title: 'GPA demo', project_description: 'Semester GPA',
  extraction_run_id: randomUUID(), classification_id: randomUUID(), source_discussion_hash: 'a'.repeat(64), created_at: '2026-10-20T00:00:00Z', created_by: 'Analyst', generation_method: 'reviewed-requirements-template-v1',
  status: 'draft', requirements: [{ requirement_id: 'R1', text: 'Students shall add courses.', original_text: 'Students shall add courses.', label: 'FR', label_review_id: randomUUID(), source_text_hash: 'b'.repeat(64), authored_revision: false, change_reason: null }], content_hash: 'c'.repeat(64), feedback: [], approval: null }
const state = { schema_version: 'c1-srs-v1', project_id: projectId, revision: 1, versions: [version] }

test('validates version identity, ordering and approval decisions', () => {
  assert.equal(validSrsState(state, projectId), true)
  for (const change of [{ version_number: 2 }, { parent_version_id: randomUUID() }, { content_hash: 'bad' }, { status: 'approved' }, { generation_method: 'llm-rag' }]) {
    assert.equal(validSrsState({ ...state, versions: [{ ...version, ...change }] }, projectId), false)
  }
  assert.equal(validSrsState({ ...state, project_id: 'other' }, projectId), false)
  assert.equal(validSrsState({ ...state, versions: [{ ...version, requirements: [...version.requirements, ...version.requirements] }] }, projectId), false)
})

test('reads saved SRS using the centralized application API', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.ok(url.pathname.endsWith(`/projects/${projectId}/srs`))
    assert.equal(options.method, 'GET')
    return Response.json(state)
  })
  assert.deepEqual(await getSrs(projectId), state)
})

test('sends exact client action with expected revision and submission ID', async (t) => {
  const input = { submission_id: randomUUID(), expected_revision: 1, reviewer_id: 'Client', version_id: version.version_id, requirement_id: 'R1', decision: 'accepted', comment: '' }
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.ok(url.pathname.endsWith('/srs/feedback'))
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), input)
    return Response.json(state)
  })
  assert.deepEqual(await saveSrsAction(projectId, 'feedback', input), state)
})

test('conflicts are surfaced without automatic retries or fabricated state', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; return Response.json({ detail: 'SRS changed. Refresh.' }, { status: 409 }) })
  await assert.rejects(saveSrsAction(projectId, 'approval', { submission_id: randomUUID(), expected_revision: 1, reviewer_id: 'Client', version_id: version.version_id, confirm: true }), /SRS changed/)
  assert.equal(calls, 1)
})

test('missing reviewer or invalid identity never sends a write', (t) => {
  t.mock.method(globalThis, 'fetch', () => { assert.fail('No network request expected') })
  assert.throws(() => saveSrsAction(projectId, 'draft', { submission_id: randomUUID(), expected_revision: 0, reviewer_id: ' ' }), /reviewer name/)
  assert.throws(() => getSrs('wrong'), /Invalid project/)
})

test('approved output requires acceptance and preserves exact approval identity', () => {
  const feedback = { feedback_id: randomUUID(), requirement_id: 'R1', decision: 'accepted', comment: 'Reviewed', reviewer_id: 'Client', recorded_at: version.created_at, identity_status: 'self_reported' }
  const approval = { reviewer_id: 'Client', approved_at: version.created_at, content_hash: version.content_hash, identity_status: 'self_reported' }
  const approved = { ...version, status: 'approved', feedback: [feedback], approval }
  assert.equal(validSrsState({ ...state, versions: [approved] }, projectId), true)
  assert.equal(validSrsState({ ...state, versions: [{ ...approved, feedback: [{ ...feedback, decision: 'request_changes' }] }] }, projectId), false)
  assert.match(srsText(approved), /Approved by: Client \(self-reported\)/)
  assert.match(srsText(approved), /Status: approved/)
})

test('draft export does not imply client approval or complete SRS generation', () => {
  const output = srsText(version)
  assert.match(output, /Status: draft/)
  assert.match(output, /Client decision: pending/)
  assert.ok(output.includes(version.requirements[0].text))
  assert.ok(!output.includes('Approved by:'))
  assert.match(output, /not a complete standards-compliant SRS/)
})

test('draft permits model labels without claiming a saved human review', () => {
  const automatic = { ...version, generation_method: 'classified-requirements-template-v2', requirements: version.requirements.map(item => ({ ...item, label_review_id: null })) }
  assert.equal(validSrsState({ ...state, versions: [automatic] }, projectId), true)
  assert.match(srsText(automatic), /model prediction \(not label-reviewed\)/)
  assert.equal(automatic.feedback.length, 0)
  assert.equal(automatic.approval, null)
})

test('bulk acceptance sends one explicit confirmed version-bound action', async (t) => {
  const body = { submission_id: randomUUID(), expected_revision: 1, reviewer_id: 'Client', version_id: version.version_id, confirm: true }
  let calls = 0
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls++
    assert.ok(url.pathname.endsWith('/srs/accept-remaining'))
    assert.deepEqual(JSON.parse(options.body), body)
    return Response.json(state)
  })
  assert.deepEqual(await saveSrsAction(projectId, 'accept-remaining', body), state)
  assert.equal(calls, 1)
})


test('legacy backend review gate explains restart instead of requiring unnecessary human reviews', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; return Response.json({ detail: 'Review and save every FR/NFR label before generating an SRS draft.' }, { status: 409 }) })
  await assert.rejects(saveSrsAction(projectId, 'draft', { submission_id: randomUUID(), expected_revision: 0, reviewer_id: 'Analyst' }), (error) => error.code === 'srs-stale-backend' && error.message.includes('Restart') && !error.uncertain)
  assert.equal(calls, 1)
})
