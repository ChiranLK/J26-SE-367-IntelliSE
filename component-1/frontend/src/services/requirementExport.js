import { analyseAmbiguity } from './ambiguity.js'
import { classificationLabels } from './projectApi.js'

export function buildRequirementExport(project, extraction, classification, reviews = []) {
  const labels = classificationLabels(classification, extraction, project.id)
  if (extraction.project_id !== project.id || !Array.isArray(reviews)) throw new Error('Export records do not belong to the same project.')
  const byId = new Map()
  for (const review of reviews) {
    const candidate = extraction.candidates.find((item) => item.requirement_id === review.requirement_id)
    if (!candidate || byId.has(review.requirement_id) || review.project_id !== project.id
      || review.extraction_run_id !== extraction.run_id || review.classification_id !== classification.classification_id
      || review.model_identifier !== classification.model_identifier || review.model_version !== classification.model_version
      || review.original_prediction !== labels.get(review.requirement_id) || !['FR', 'NFR'].includes(review.reviewed_label)
      || review.review_status !== 'user_reviewed' || review.source_discussion_hash !== extraction.source_discussion_hash) {
      throw new Error('Saved reviews do not match this export. Refresh saved results.')
    }
    byId.set(review.requirement_id, review)
  }
  return {
    schema_version: 'c1-requirements-export-v1',
    project: { id: project.id, name: project.name, description: project.description, discussion_text: project.discussion_text,
      transcription_provenance: project.transcription_provenance ?? null },
    source_ambiguity_analysis: analyseAmbiguity(project.discussion_text, { scope: 'discussion_text' }),
    extraction: { run_id: extraction.run_id, created_at: extraction.created_at, source_discussion_hash: extraction.source_discussion_hash,
      model_identifier: extraction.model_identifier, provider: extraction.provider ?? null, prompt_version: extraction.prompt_version },
    classification: { classification_id: classification.classification_id, model_identifier: classification.model_identifier,
      model_version: classification.model_version, classified_at: classification.classified_at },
    requirements: extraction.candidates.map((candidate, index) => {
      const review = byId.get(candidate.requirement_id) ?? null
      return { display_id: `R${String(index + 1).padStart(2, '0')}`, requirement_id: candidate.requirement_id,
        text: candidate.requirement_text, label: review?.reviewed_label ?? labels.get(candidate.requirement_id),
        label_source: review ? 'user_reviewed' : 'model_prediction', model_prediction: labels.get(candidate.requirement_id),
        candidate_review_status: candidate.review_status, evidence: candidate.evidence, label_review: review, ambiguity_analysis: analyseAmbiguity(candidate.requirement_text) }
    }),
    limitations: 'Saved human labels are self-reported reviews. Model predictions may be wrong. English ambiguity rules can miss unclear requirements or flag clear wording; they do not establish semantic clarity. Extraction completeness and relevance require evaluation. No client approval or independent verification is implied.',
  }
}

// Only this presentation projection is downloaded. Full saved records remain in the application.
export function simplifiedRequirementExport(data) {
  return {
    project_title: data.project.name,
    project_description: data.project.description ?? '',
    functional_requirements: data.requirements.filter((item) => item.label === 'FR').map((item) => item.text),
    non_functional_requirements: data.requirements.filter((item) => item.label === 'NFR').map((item) => item.text),
  }
}

export function exportAsText(data) {
  const summary = simplifiedRequirementExport(data)
  const group = (heading, items) => [heading, ...(items.length ? items.map((text, index) => `${index + 1}. ${text}`) : ['None.'])]
  return [
    `Project title: ${summary.project_title}`,
    `Project description: ${summary.project_description}`, '',
    ...group('Functional requirements (FR)', summary.functional_requirements), '',
    ...group('Non-functional requirements (NFR)', summary.non_functional_requirements),
  ].join('\n')
}

export function requirementExportFilename(projectTitle, format) {
  if (!['json', 'txt'].includes(format)) throw new Error('Choose JSON or text.')
  const rawTitle = (typeof projectTitle === 'string' ? projectTitle : '').normalize('NFC')
  const title = Array.from(rawTitle, (character) => character.codePointAt(0) < 32 || character.codePointAt(0) === 127 ? '-' : character).join('')
    .replace(/[<>:"/\\|?*]/g, '-')
    .replace(/\s+/gu, ' ').replace(/^[. ]+|[. ]+$/g, '') || 'Project'
  const safeTitle = /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(title) ? `Project ${title}` : title
  // Keep Unicode titles while staying within common filename byte limits.
  let basename = ''
  const encoder = new TextEncoder()
  for (const character of safeTitle) {
    if (encoder.encode(basename + character).length > 200) break
    basename += character
  }
  return `${basename.replace(/[. ]+$/g, '') || 'Project'}.${format}`
}

export function downloadRequirementExport(data, format) {
  if (!['json', 'txt'].includes(format)) throw new Error('Choose JSON or text.')
  const content = format === 'json' ? JSON.stringify(simplifiedRequirementExport(data), null, 2) : exportAsText(data)
  const blob = new Blob([content], { type: format === 'json' ? 'application/json;charset=utf-8' : 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = requirementExportFilename(data.project.name, format)
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
