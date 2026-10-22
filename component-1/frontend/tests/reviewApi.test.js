import assert from 'node:assert/strict'
import { createHash, randomUUID } from 'node:crypto'
import { test } from 'node:test'
import { getLabelReviews, saveLabelReview } from '../src/services/reviewApi.js'

const projectId = '507f1f77bcf86cd799439011'
const extraction = { project_id: projectId, run_id: randomUUID(), source_discussion_hash: 'a'.repeat(64), candidates: [{ requirement_id: 'req-one', requirement_text: 'Users can reset passwords.' }] }
const classification = { classification_id: randomUUID(), project_id: projectId, extraction_run_id: extraction.run_id,
  model_identifier: 'tfidf-logistic-regression', model_version: 'b'.repeat(64), classified_at: '2026-10-18T00:00:00Z', predictions: [{ requirement_id: 'req-one', label: 'NFR' }] }
const input = { submission_id: randomUUID(), reviewed_label: 'FR', reviewer_id: 'Reviewer', note: '<b>Plain text note</b>' }
const saved = { review_id: randomUUID(), ...input, project_id: projectId, extraction_run_id: extraction.run_id,
  classification_id: classification.classification_id, requirement_id: 'req-one', original_prediction: 'NFR',
  model_identifier: classification.model_identifier, model_version: classification.model_version,
  source_discussion_hash: extraction.source_discussion_hash, requirement_text_hash: createHash('sha256').update(extraction.candidates[0].requirement_text).digest('hex'),
  reviewed_at: '2026-10-18T01:00:00Z', review_status: 'user_reviewed', reviewer_identity_status: 'self_reported' }
const page = { project_id: projectId, extraction_run_id: extraction.run_id, classification_id: classification.classification_id, reviews: [saved] }

test('save sends reviewed label only and verifies source, prediction and run identities', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.ok(url.pathname.endsWith(`/classifications/${classification.classification_id}/requirements/req-one/reviews`))
    assert.equal(options.method, 'POST')
    assert.deepEqual(JSON.parse(options.body), input)
    return Response.json(saved, { status: 201 })
  })
  assert.deepEqual(await saveLabelReview(projectId, extraction, classification, 'req-one', input), saved)
  assert.equal(classification.predictions[0].label, 'NFR')
})

test('reopen retrieves existing reviews; empty reviews are valid', async (t) => {
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    assert.equal(options.method, 'GET')
    return Response.json(page)
  })
  assert.deepEqual(await getLabelReviews(projectId, extraction, classification), page)
  t.mock.method(globalThis, 'fetch', async () => Response.json({ ...page, reviews: [] }))
  assert.deepEqual((await getLabelReviews(projectId, extraction, classification)).reviews, [])
})

test('rejects mismatched identity, hashes, prediction, labels and duplicate reviews', async (t) => {
  for (const change of [{ classification_id: randomUUID() }, { requirement_id: 'other' }, { requirement_text_hash: 'f'.repeat(64) }, { model_version: 'x' }, { original_prediction: 'FR' }, { reviewed_label: 'FN' }, { review_status: 'approved' }]) {
    t.mock.method(globalThis, 'fetch', async () => Response.json({ ...page, reviews: [{ ...saved, ...change }] }))
    await assert.rejects(getLabelReviews(projectId, extraction, classification), { code: 'invalid-response' })
  }
  t.mock.method(globalThis, 'fetch', async () => Response.json({ ...page, reviews: [saved, saved] }))
  await assert.rejects(getLabelReviews(projectId, extraction, classification), { code: 'invalid-response' })
})

test('invalid input makes no request; unavailable backend never generates reviews', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; return Response.json({ detail: 'Not Found' }, { status: 404 }) })
  assert.throws(() => saveLabelReview(projectId, extraction, classification, 'req-one', { ...input, reviewed_label: 'FN' }), { code: 'review-input' })
  assert.equal(calls, 0)
  await assert.rejects(getLabelReviews(projectId, extraction, classification), { status: 404 })
})

test('uncertain save preserves the explicit submission ID and makes no automatic retry', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; throw new TypeError('offline') })
  await assert.rejects(saveLabelReview(projectId, extraction, classification, 'req-one', input), { uncertain: true })
  assert.equal(calls, 1)
})
