import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { test } from 'node:test'
import { buildRequirementExport, exportAsText, simplifiedRequirementExport } from '../src/services/requirementExport.js'

const project = { id: '507f1f77bcf86cd799439011', name: 'Grocery store', description: 'Reviewed requirements', discussion_text: 'Users can reset passwords.' }
const extraction = { project_id: project.id, run_id: randomUUID(), source_discussion_hash: 'a'.repeat(64), candidates: [{ requirement_id: randomUUID(), requirement_text: project.discussion_text, review_status: 'unreviewed', evidence: [{ quote: project.discussion_text, start: 0, end: project.discussion_text.length }] }] }
const classification = { project_id: project.id, extraction_run_id: extraction.run_id, classification_id: randomUUID(), model_identifier: 'tfidf-logistic-regression', model_version: 'b'.repeat(64), classified_at: '2026-10-18T00:00:00Z', predictions: [{ requirement_id: extraction.candidates[0].requirement_id, label: 'NFR' }] }
const review = { review_id: randomUUID(), project_id: project.id, extraction_run_id: extraction.run_id, classification_id: classification.classification_id, requirement_id: extraction.candidates[0].requirement_id, model_identifier: classification.model_identifier, model_version: classification.model_version, original_prediction: 'NFR', reviewed_label: 'FR', review_status: 'user_reviewed', reviewer_id: 'Reviewer', reviewed_at: classification.classified_at, note: 'A function.', source_discussion_hash: extraction.source_discussion_hash }

test('export uses saved reviewed label but retains model prediction, IDs and evidence', () => {
  const before = JSON.stringify({ project, extraction, classification, review })
  const data = buildRequirementExport(project, extraction, classification, [review])
  assert.equal(data.requirements[0].label, 'FR')
  assert.equal(data.requirements[0].model_prediction, 'NFR')
  assert.equal(data.requirements[0].label_source, 'user_reviewed')
  assert.equal(data.requirements[0].candidate_review_status, 'unreviewed')
  assert.deepEqual(data.requirements[0].evidence, extraction.candidates[0].evidence)
  assert.equal(data.requirements[0].requirement_id, review.requirement_id)
  assert.equal(JSON.stringify({ project, extraction, classification, review }), before)
})

test('unreviewed predictions remain recorded internally and appear under their predicted group', () => {
  const data = buildRequirementExport(project, extraction, classification)
  assert.equal(data.requirements[0].label, 'NFR')
  assert.equal(data.requirements[0].label_source, 'model_prediction')
  assert.deepEqual(simplifiedRequirementExport(data).non_functional_requirements, [project.discussion_text])
  assert.ok(!exportAsText(data).includes('Model'))
})

test('refuses stale or unrelated reviews instead of applying their labels', () => {
  for (const change of [{ classification_id: randomUUID() }, { extraction_run_id: randomUUID() }, { requirement_id: randomUUID() }, { project_id: 'other' }, { model_version: 'wrong' }, { reviewed_label: 'FN' }, { source_discussion_hash: 'bad' }]) {
    assert.throws(() => buildRequirementExport(project, extraction, classification, [{ ...review, ...change }]), /do not match/)
  }
  assert.throws(() => buildRequirementExport(project, extraction, classification, [review, review]), /do not match/)
})

test('saved audio provenance stays separate while downloads contain only requested fields', () => {
  const audioProject = { ...project, transcription_provenance: { transcription_id: randomUUID(), original_transcript: 'Original ASR.', model: 'azure-speech-fast' } }
  const data = buildRequirementExport(audioProject, extraction, classification, [review])
  const roundTrip = JSON.parse(JSON.stringify(data))
  assert.equal(roundTrip.project.discussion_text, project.discussion_text)
  assert.equal(roundTrip.project.transcription_provenance.original_transcript, 'Original ASR.')
  const text = exportAsText(data)
  assert.ok(text.includes(project.discussion_text))
  assert.ok(!text.includes('Original ASR.'))
  assert.deepEqual(simplifiedRequirementExport(data), { project_title: project.name, project_description: project.description, functional_requirements: [project.discussion_text], non_functional_requirements: [] })
})

test('empty classification exports no fabricated requirements', () => {
  const data = buildRequirementExport(project, { ...extraction, candidates: [] }, { ...classification, predictions: [] })
  assert.deepEqual(data.requirements, [])
  assert.match(exportAsText(data), /Functional requirements \(FR\)\nNone\./)
})


test('minimal exports group saved reviewed labels and preserve text and order', () => {
  const text = 'Results shall appear within one second.'
  const extendedExtraction = { ...extraction, candidates: [...extraction.candidates, { requirement_id: 'second', requirement_text: text }] }
  const extendedClassification = { ...classification, predictions: [...classification.predictions, { requirement_id: 'second', label: 'NFR' }] }
  const data = buildRequirementExport({ ...project, description: null }, extendedExtraction, extendedClassification, [review])
  const summary = simplifiedRequirementExport(data)
  assert.deepEqual(summary, { project_title: project.name, project_description: '', functional_requirements: [project.discussion_text], non_functional_requirements: [text] })
  assert.equal(exportAsText(data), `Project title: Grocery store\nProject description: \n\nFunctional requirements (FR)\n1. Users can reset passwords.\n\nNon-functional requirements (NFR)\n1. ${text}`)
  assert.ok(!JSON.stringify(summary).includes('source_discussion_hash'))
})
