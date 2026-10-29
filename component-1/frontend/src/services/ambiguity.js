// Transparent review hints, independent of FR/NFR prediction and source evidence.
export const AMBIGUITY_RULE_VERSION = 'c1-ambiguity-rules-v1'
const rules = [
  { id: 'vague-speed', pattern: '\\b(?:quickly|fast|rapidly|promptly)\\b', reason: 'The response-time wording may need a measurable limit.', question: 'What is the maximum acceptable response time, and under what workload?' },
  { id: 'subjective-usability', pattern: '\\b(?:user[- ]friendly|easy to use|intuitive)\\b', reason: 'Different users may interpret this quality differently.', question: 'Which user task, user group and measurable success criterion define acceptable usability?' },
  { id: 'vague-quantity', pattern: '\\b(?:many|few|several|some|minimal|sufficient|adequate)\\b', reason: 'The quantity or threshold may be unspecified.', question: 'What exact count, range, percentage or limit is required?' },
  { id: 'unspecified-condition', pattern: '\\b(?:appropriate|as needed|as required|where possible|if possible|normally|usually|generally)\\b', reason: 'The applicable condition or decision rule may be missing.', question: 'Under which precise conditions does this apply, and who decides?' },
  { id: 'open-ended-list', pattern: '\\betc\\.|\\band so on\\b', reason: 'The list does not define its full scope.', question: 'What is the complete list of supported items or actions?' },
  { id: 'uncertain-obligation', pattern: '\\b(?:should|could|might)\\b', reason: 'The required obligation or priority may need confirmation.', question: 'Is this mandatory, optional or a future preference?' },
  { id: 'logical-choice', pattern: '\\band/or\\b', reason: 'The allowed combination may be interpreted in different ways.', question: 'Are both options required, either option sufficient, or must exactly one be chosen?' },
]

export function analyseAmbiguity(text, { scope = 'requirement_text' } = {}) {
  if (typeof text !== 'string') throw new TypeError('Requirement text must be a string.')
  if (!['requirement_text', 'discussion_text'].includes(scope)) throw new TypeError('Unknown ambiguity offset scope.')
  // Compute Unicode offsets once, including for long saved discussions.
  const offsets = new Uint32Array(text.length + 1)
  let utf16 = 0
  let characters = 0
  for (const character of text) {
    for (let index = 0; index < character.length; index++) offsets[utf16++] = characters
    characters++
  }
  offsets[text.length] = characters
  const issues = []
  for (const rule of rules) {
    for (const match of text.matchAll(new RegExp(rule.pattern, 'gi'))) {
      const start = offsets[match.index]
      issues.push({ rule_id: rule.id, phrase: match[0], start, end: offsets[match.index + match[0].length],
        reason: rule.reason, clarification_question: rule.question })
    }
  }
  issues.sort((a, b) => a.start - b.start || a.rule_id.localeCompare(b.rule_id))
  return { rule_version: AMBIGUITY_RULE_VERSION, method: 'rules', language: 'en', offset_scope: scope,
    status: issues.length ? 'potential_unclear_points' : 'no_rule_matches', issues }
}
