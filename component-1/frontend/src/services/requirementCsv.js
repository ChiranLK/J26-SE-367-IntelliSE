export const MAX_CSV_BYTES = 100000
export const MAX_CSV_ROWS = 50

// Small strict CSV reader supporting BOM, CRLF, quoted commas/newlines and "".
// Preserve requirement wording; trim only header/ID/expected-label metadata.
export function parseRequirementCsv(source) {
  const input = source.replace(/^\uFEFF/, '')
  const records = []
  let row = [], field = '', quoted = false, closed = false
  function cell() { row.push(field); field = ''; closed = false }
  function record() {
    cell()
    if (row.some((value) => value.trim())) records.push(row)
    row = []
    if (records.length > MAX_CSV_ROWS + 1) throw new Error('Use no more than 50 requirements per file.')
  }
  for (let i = 0; i < input.length; i++) {
    const char = input[i]
    if (quoted) {
      if (char === '"' && input[i + 1] === '"') { field += '"'; i++ }
      else if (char === '"') { quoted = false; closed = true }
      else field += char
    } else if (char === ',') cell()
    else if (char === '\n' || char === '\r') {
      if (char === '\r' && input[i + 1] === '\n') i++
      record()
    } else if (char === '"') {
      if (field || closed) throw new Error('Invalid CSV quoting. Use the downloadable sample format.')
      quoted = true
    } else {
      if (closed) throw new Error('Unexpected text after a quoted CSV field.')
      field += char
    }
  }
  if (quoted) throw new Error('The CSV contains an unfinished quoted field.')
  if (field || row.length || closed) record()
  const headers = records.shift()?.map((value) => value.trim().toLowerCase()) ?? []
  if (!headers.includes('requirement') || new Set(headers).size !== headers.length
    || headers.some((key) => !['id', 'requirement', 'expected_label'].includes(key))) {
    throw new Error('Use a requirement column, with optional id and expected_label columns.')
  }
  if (!records.length) throw new Error('The CSV contains no requirements.')
  const identifiers = new Set()
  return records.map((values, index) => {
    const number = index + 1
    if (values.length !== headers.length) throw new Error(`Requirement ${number} has the wrong number of CSV fields.`)
    const data = Object.fromEntries(headers.map((key, column) => [key, values[column]]))
    if (!data.requirement.trim() || Array.from(data.requirement).length > 5000) throw new Error(`Requirement ${number} must contain 1–5,000 characters.`)
    const id = data.id?.trim() || `R${String(number).padStart(2, '0')}`
    if (id.length > 80 || identifiers.has(id)) throw new Error(`Requirement ${number} needs a unique ID of at most 80 characters.`)
    identifiers.add(id)
    const expected = data.expected_label?.trim().toUpperCase() || null
    if (expected && !['FR', 'NFR'].includes(expected)) throw new Error(`Requirement ${number}: expected_label must be FR, NFR or empty.`)
    return { id, requirement: data.requirement, expected }
  })
}

export async function readRequirementFile(file) {
  if (!file || !/\.csv$/i.test(file.name)) throw new Error('Choose a .csv file, such as the downloadable sample.')
  if (file.size < 1 || file.size > MAX_CSV_BYTES) throw new Error('Choose a nonempty CSV no larger than 100 KB.')
  let source
  try { source = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()) }
  catch { throw new Error('Save the CSV as UTF-8 and try again.') }
  return parseRequirementCsv(source)
}
