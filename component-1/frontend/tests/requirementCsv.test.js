import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { parseRequirementCsv, readRequirementFile } from '../src/services/requirementCsv.js'

test('downloadable sample contains 12 illustrative rows with balanced expected labels', async () => {
  const source = await readFile(new URL('../public/samples/fr-nfr-test.csv', import.meta.url), 'utf8')
  const rows = parseRequirementCsv(source)
  assert.equal(rows.length, 12)
  assert.equal(rows.filter((row) => row.expected === 'FR').length, 6)
  assert.equal(rows.filter((row) => row.expected === 'NFR').length, 6)
  assert.match(rows[4].requirement, /reports, including totals,/)
})

test('CSV preserves commas, escaped quotes, multiline Unicode text, BOM and CRLF', () => {
  assert.deepEqual(parseRequirementCsv('\uFEFFid,requirement,expected_label\r\nA,"  Users say ""hello"", 👋\r\non login.  ", fr\r\n'), [{
    id: 'A', requirement: '  Users say "hello", 👋\r\non login.  ', expected: 'FR',
  }])
})

test('expected labels and IDs are optional; wording is not normalized', () => {
  assert.deepEqual(parseRequirementCsv('requirement\n  Keep this text.  \n'), [{ id: 'R01', requirement: '  Keep this text.  ', expected: null }])
})

test('malformed/unfinished quoting, missing headers and unknown columns are rejected', () => {
  for (const source of ['text\nHello', 'requirement,requirement\na,b', 'requirement,other\na,b', 'requirement\n"unfinished', 'requirement\n"closed"extra', 'requirement\nbad"quote']) {
    assert.throws(() => parseRequirementCsv(source))
  }
})

test('blank requirements, invalid labels, duplicate IDs and field-count errors are rejected', () => {
  for (const source of ['requirement\n', 'id,requirement,expected_label\nA, ,FR', 'requirement,expected_label\nHello,unknown', 'id,requirement\nA,One\nA,Two', 'requirement\nToo,many']) {
    assert.throws(() => parseRequirementCsv(source))
  }
})

test('row and requirement length bounds are enforced before inference', () => {
  assert.throws(() => parseRequirementCsv(`requirement\n${'Row\n'.repeat(51)}`), /50 requirements/)
  assert.throws(() => parseRequirementCsv(`requirement\n${'x'.repeat(5001)}`), /5,000/)
})

test('file reader enforces extension, byte size and UTF-8 encoding', async () => {
  for (const file of [new File(['requirement\nHello'], 'input.txt'), new File([], 'empty.csv'), new File(['x'.repeat(100001)], 'large.csv'), new File([new Uint8Array([0xff])], 'invalid.csv')]) {
    await assert.rejects(readRequirementFile(file))
  }
  assert.equal((await readRequirementFile(new File(['requirement\nHello'], 'valid.csv')))[0].requirement, 'Hello')
})
