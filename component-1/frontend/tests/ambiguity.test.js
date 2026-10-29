import assert from 'node:assert/strict'
import { test } from 'node:test'
import { analyseAmbiguity, AMBIGUITY_RULE_VERSION } from '../src/services/ambiguity.js'
import { buildRequirementExport, exportAsText } from '../src/services/requirementExport.js'

test('flags wording with exact phrases and useful clarification questions', () => {
  const result = analyseAmbiguity('The calculator should respond quickly and be user-friendly.')
  assert.equal(result.rule_version, AMBIGUITY_RULE_VERSION)
  assert.equal(result.method, 'rules')
  assert.equal(result.status, 'potential_unclear_points')
  assert.deepEqual(result.issues.map((item) => item.phrase), ['should', 'quickly', 'user-friendly'])
  assert.ok(result.issues.every((item) => item.clarification_question.endsWith('?')))
})

test('offsets refer to Unicode characters in exact candidate text, including repeats', () => {
  const text = '👋 Reports load Quickly, and quickly again.'
  const result = analyseAmbiguity(text)
  assert.equal(result.issues.length, 2)
  for (const item of result.issues) assert.equal(Array.from(text).slice(item.start, item.end).join(''), item.phrase)
  assert.equal(text, '👋 Reports load Quickly, and quickly again.')
})

test('permissions, negation, numeric limits and clear calculator statements remain untouched', () => {
  for (const text of ['Only administrators may delete accounts.', 'Guests must not delete reports.', 'Results shall appear within two seconds.', 'Users shall be able to add two numbers.']) {
    assert.deepEqual(analyseAmbiguity(text).issues, [])
    assert.equal(analyseAmbiguity(text).status, 'no_rule_matches')
  }
  // No rule match is not a proof of clarity: unresolved references are outside v1 scope.
  assert.equal(analyseAmbiguity('It shall do that.').status, 'no_rule_matches')
})

test('open-ended lists and vague quantities/conditions are review hints', () => {
  const result = analyseAmbiguity('Support many users as needed, etc. and/or other accounts.')
  assert.deepEqual(result.issues.map((item) => item.rule_id), ['vague-quantity', 'unspecified-condition', 'open-ended-list', 'logical-choice'])
})

test('internal analysis retains rule hints while simple downloads retain only requirements', () => {
  const text = 'Results should appear quickly.'
  const project = { id: '507f1f77bcf86cd799439011', name: 'Example', discussion_text: text }
  const extraction = { project_id: project.id, run_id: 'run', source_discussion_hash: 'hash', candidates: [{ requirement_id: 'R1', requirement_text: text, evidence: [{ quote: text, start: 0, end: text.length }], review_status: 'unreviewed' }] }
  const classification = { project_id: project.id, extraction_run_id: 'run', classification_id: 'class', model_identifier: 'tfidf-logistic-regression', model_version: 'version', classified_at: '2026-10-19T00:00:00Z', predictions: [{ requirement_id: 'R1', label: 'NFR' }] }
  const data = buildRequirementExport(project, extraction, classification)
  assert.equal(data.requirements[0].text, text)
  assert.equal(data.requirements[0].model_prediction, 'NFR')
  assert.equal(data.requirements[0].ambiguity_analysis.issues.length, 2)
  assert.ok(exportAsText(data).includes(text))
  assert.ok(!exportAsText(data).includes('Clarify:'))
})

test('full-discussion hints survive a partial extraction without inventing candidates', () => {
  const source = [
    'The calculator shall display results quickly.',
    'The calculator shall have a user-friendly interface.',
    'Calculation results shall appear within one second.',
  ].join('\n')
  const project = { id: '507f1f77bcf86cd799439011', name: 'Partial extraction', discussion_text: source }
  const quote = source.split('\n')[2]
  const extraction = { project_id: project.id, run_id: 'run', source_discussion_hash: 'hash', candidates: [{ requirement_id: 'R1', requirement_text: quote, evidence: [{ quote, start: source.indexOf(quote), end: source.length }], review_status: 'unreviewed' }] }
  const classification = { project_id: project.id, extraction_run_id: 'run', classification_id: 'class', model_identifier: 'tfidf-logistic-regression', model_version: 'version', classified_at: '2026-10-19T00:00:00Z', predictions: [{ requirement_id: 'R1', label: 'NFR' }] }
  const data = buildRequirementExport(project, extraction, classification)
  assert.equal(data.requirements.length, 1, 'source hints must not become fabricated requirements')
  assert.equal(data.requirements[0].text, quote)
  assert.equal(data.requirements[0].ambiguity_analysis.issues.length, 0)
  assert.equal(data.source_ambiguity_analysis.offset_scope, 'discussion_text')
  assert.deepEqual(data.source_ambiguity_analysis.issues.map(item => item.phrase), ['quickly', 'user-friendly'])
  for (const issue of data.source_ambiguity_analysis.issues) assert.equal(Array.from(source).slice(issue.start, issue.end).join(''), issue.phrase)
  const text = exportAsText(data)
  assert.ok(text.includes(quote))
  assert.ok(!text.includes('quickly') && !text.includes('user-friendly'))
})

test('full-discussion scan works without extraction and does not treat all conversation as requirements', () => {
  const text = '👋 We should meet on Friday. Results shall appear quickly.'
  const result = analyseAmbiguity(text, { scope: 'discussion_text' })
  assert.equal(result.offset_scope, 'discussion_text')
  assert.deepEqual(result.issues.map(item => item.phrase), ['should', 'quickly'])
  assert.ok(!('requirements' in result), 'wording flags do not establish software relevance')
  for (const issue of result.issues) assert.equal(Array.from(text).slice(issue.start, issue.end).join(''), issue.phrase)
})

test('Unicode offsets remain correct in long discussions', () => {
  const text = '👋 '.repeat(5000) + 'Results shall appear quickly.'
  const result = analyseAmbiguity(text, { scope: 'discussion_text' })
  assert.equal(result.issues.length, 1)
  assert.equal(Array.from(text).slice(result.issues[0].start, result.issues[0].end).join(''), 'quickly')
  assert.throws(() => analyseAmbiguity(text, { scope: 'unknown' }), TypeError)
})
