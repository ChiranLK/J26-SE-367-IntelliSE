// Builds the technology-comparison criteria from what the user actually has: the uploaded documents and the
// choices made on the page. Nothing here assumes a particular application or a fixed technology.

// Human-readable names for the four supported technologies.
export const TECH_LABELS = { REACT: "React", ANGULAR: "Angular", NODE_JS: "Node.js", SPRING_BOOT: "Spring Boot" };

// Options shown by the frontend and backend preference controls.
export const FRONTEND_CHOICES = [["", "No preference"], ["REACT", "React"], ["ANGULAR", "Angular"]];
export const BACKEND_CHOICES = [["", "No preference"], ["NODE_JS", "Node.js"], ["SPRING_BOOT", "Spring Boot"]];

// Accept a detected technology only when the document names exactly one option.
const only = (matches) => (matches.length === 1 ? matches[0] : "");

/** Technologies the documents name. A technology counts only when exactly one of its kind is mentioned. */
export function technologiesNamedIn(...texts) {
  const text = texts.filter(Boolean).join(" ");
  const frontend = [];
  if (/\breact(\.?js)?\b/i.test(text)) frontend.push("REACT");
  if (/\bangular(\.?js)?\b/i.test(text)) frontend.push("ANGULAR");
  const backend = [];
  if (/\bnode(\.?js)?\b/i.test(text)) backend.push("NODE_JS");
  if (/\bspring(\s*boot)?\b/i.test(text)) backend.push("SPRING_BOOT");
  return { frontend: only(frontend), backend: only(backend) };
}

// Class-name suffixes used to recognize a layered design.
const LAYER_SUFFIX = /(Service|Repository|Controller|Manager|Dao)$/;

/**
 * Reads the architecture style from the class diagram: two or more different layers (for example a Service and a
 * Repository) mean a layered design; a small diagram without layers is a quick MVP; anything else is a plain REST SPA.
 */
export function deriveArchitecture(classNames) {
  const names = classNames ?? [];
  const layers = [...new Set(names.map((name) => LAYER_SUFFIX.exec(name)?.[1]).filter(Boolean))];
  if (layers.length >= 2) {
    return { style: "ENTERPRISE_LAYERED", label: "Layered (enterprise)", reason: `the diagram has ${layers.join(" and ")} classes` };
  }
  if (names.length > 0 && names.length <= 12) {
    return { style: "RAPID_MVP", label: "Small MVP", reason: `the diagram is small (${names.length} classes) and has no service or repository layers` };
  }
  return { style: "REST_SPA", label: "Web app with REST API", reason: "the diagram does not point to a layered or a minimal design" };
}

/** Technologies that no buildable candidate uses: these have to be excluded when asking what can be built now. */
export function unbuildableTechnologies(report) {
  const buildable = new Set();
  const all = new Set();
  for (const row of report.candidate_calculations) {
    for (const tech of [row.candidate.frontend, row.candidate.backend]) {
      all.add(tech);
      if (row.generator_availability === "IMPLEMENTED") buildable.add(tech);
    }
  }
  return [...all].filter((tech) => !buildable.has(tech));
}

// Neutral team-proficiency defaults used until the researcher changes them.
export const DEFAULT_COMFORT = { react: 5, angular: 5, node_js: 5, spring_boot: 5 };

// Build the documented criteria and evidence sent to backend stack selection.
export function buildStackCriteria({ named, choices, architecture = null, prohibited = [] }) {
  // Record whether evidence came from the documents or default page assumptions.
  const stated = Boolean(named.frontend || named.backend);
  const touched = Boolean(choices.touched);
  const evidence = (reference, confidence, notes) => ({ reference, confidence, uncertainty_notes: notes });
  // Normalize choices, team scores, runtime support and evidence confidence.
  return {
    preferred_frontend: choices.frontend || null,
    preferred_backend: choices.backend || null,
    architecture_style: architecture?.style ?? "REST_SPA",
    prohibited_technologies: prohibited,
    team_proficiency: Object.fromEntries(Object.entries(choices.comfort).map(([key, value]) => [key, Math.max(0, Math.min(10, Number(value))) / 10])),
    available_backend_runtimes: ["NODE", "JVM"],
    supports_static_spa: true,
    evidence: {
      requirements: evidence("UPLOADED-C1-C2-DOCUMENTS", stated ? 1.0 : 0.5, stated ? "Technology named in the documents." : "The documents name no technology."),
      architecture: architecture
        ? evidence("DERIVED-FROM-C2-CLASS-DIAGRAM", 0.7, `Read from the class diagram: ${architecture.reason}.`)
        : evidence("PAGE-ASSUMPTION-WEB-APP-WITH-REST-API", 0.5, "All four options are web apps with a REST API."),
      team: evidence("ENTERED-ON-DESIGN-AND-STACK-PAGE", touched ? 1.0 : 0.5, touched ? "Entered by the user." : "Left at the neutral middle value."),
      deployment: evidence("PAGE-ASSUMPTION-NODE-AND-JAVA-AVAILABLE", 0.5, "Both runtimes are assumed to be available."),
    },
  };
}

// Remove technical evidence suffixes from messages shown to users.
const withoutEvidence = (text) => String(text ?? "").replace(/\s*\(evidence:[^)]*\)/g, "");

// Convert a technology enum value into its display name.
const label = (technology) => TECH_LABELS[technology] ?? technology;

// Build the readable frontend + backend candidate name.
export const stackName = (candidate) => `${label(candidate.frontend)} + ${label(candidate.backend)}`;

/** Plain-language reason a candidate was ruled out. */
export function plainFailures(failures) {
  return (failures ?? []).map(withoutEvidence).map((text) => text.replace(/[.\s]+$/, ""));
}

/** One sentence that says why the best option won. */
export function plainSelectionReason(report) {
  const selected = report.selected_stack;
  const ties = report.candidate_calculations.filter((item) => item.eligible && item.normalized_score === selected.normalized_score).length;
  const name = stackName(selected.candidate);
  if (ties > 1) return `${ties} options scored the same, so ${name} was chosen by the fixed order of the scoring policy.`;
  return `${name} scored highest among the options that fit your choices.`;
}

// ---- Marks out of 10 -------------------------------------------------------------------------------------------
// Final marks = 80% how well the option fits the design + 20% whether the generator for it exists. The 20% is a visible
// policy assumption: only a combination that can really be generated can be chosen (FR-C3-02, "supported" stack).
export const BUILD_WEIGHT = 0.2;

/** Fit with the design, out of 10: the policy criteria weighted by their raw scores, before any evidence discount. */
export const fitMarks = (row) => 10 * row.criterion_scores.reduce((total, item) => total + item.weight * item.raw_score, 0);

/** Can the generator for this combination build it today: 10 or 0. */
export const buildMarks = (row) => (row.generator_availability === "IMPLEMENTED" ? 10 : 0);

// Combine design fit and current generator availability into the displayed mark.
export const finalMarks = (row) => (1 - BUILD_WEIGHT) * fitMarks(row) + BUILD_WEIGHT * buildMarks(row);

// Display marks with one decimal place.
export const formatMarks = (value) => value.toFixed(1);

/** One sentence that says why the selected option has the most marks. */
export function marksReason(report) {
  const selected = report.candidate_calculations.find((row) => row.candidate.candidate_id === report.selected_stack.candidate.candidate_id) ?? report.selected_stack;
  const name = stackName(selected.candidate);
  const built = buildMarks(selected) === 10;
  return `${name} has the most marks: it fits your design (${formatMarks(fitMarks(selected))}/10)${built ? " and it is the combination that can be generated today (10/10)" : ""}.`;
}
