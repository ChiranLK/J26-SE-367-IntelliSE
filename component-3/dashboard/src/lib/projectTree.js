// Turns the generated project's file list into a folder tree with plain-language descriptions.
// Everything shown comes from the run manifest's file records; the descriptions only explain them.

export const FOLDER_INFO = {
  frontend: "The website people use: a React app.",
  "frontend/src": "The app's code.",
  "frontend/src/components": "Screens and widgets: the form, the result, the history list.",
  "frontend/src/api": "Talks to the backend API.",
  "frontend/src/policy": "The grade table shown to the user.",
  "frontend/src/validation": "Checks the form before anything is sent.",
  backend: "The server: calculates the GPA and saves the history (Node.js).",
  "backend/src": "The server's code.",
  "backend/src/routes": "Which web address goes to which handler.",
  "backend/src/controllers": "Reads the request and sends back the answer.",
  "backend/src/services": "The GPA calculation itself.",
  "backend/src/repositories": "Saving and reading the history (in memory or in PostgreSQL).",
  "backend/src/validation": "Rejects wrong input (bad grade, too many credits, ...).",
  "backend/src/policy": "The grade points of the grading policy.",
  "backend/src/db": "Database connection and set-up.",
  "backend/test": "Automated smoke checks of the server.",
  database: "The database structure (PostgreSQL).",
  "database/migrations": "Step-by-step set-up scripts for the database.",
  openapi: "The API written down in a standard format.",
  "test-seams": "Hooks for the independent testers (C4).",
  deployment: "Docker files to run the whole app on a computer.",
};

export const FILE_INFO = {
  "README.md": "Overview of the project and how to run it.",
  "frontend/index.html": "The page that loads the React app.",
  "frontend/package.json": "The frontend's packages and build command.",
  "frontend/vite.config.js": "Build tool settings.",
  "frontend/src/main.jsx": "Starts the React app.",
  "frontend/src/App.jsx": "The page layout: heading, form, result and history.",
  "frontend/src/styles.css": "Colours, spacing and layout.",
  "frontend/src/api/gpaApi.js": "Calls the backend: calculate, list and (if present) clear history.",
  "frontend/src/components/GpaCalculatorForm.jsx": "The module table with Add module and Calculate GPA.",
  "frontend/src/components/ModuleRow.jsx": "One row: module code, credits, grade, counts toward GPA.",
  "frontend/src/components/GpaResult.jsx": "Shows the calculated GPA.",
  "frontend/src/components/HistoryList.jsx": "Lists previous calculations.",
  "frontend/src/components/PolicyDisclosure.jsx": "Text that tells which grading policy is used.",
  "frontend/src/policy/gradingPolicy.js": "Grades and grade points for the drop-down.",
  "frontend/src/validation/moduleValidation.js": "Form checks: required fields, credit range, repeated modules.",
  "backend/package.json": "The server's packages and test command.",
  "backend/src/server.js": "Starts the server.",
  "backend/src/app.js": "Connects routes, controller, service and repository together.",
  "backend/src/errors.js": "Clear error messages and error codes.",
  "backend/src/routes/gpaRoutes.js": "The API addresses (calculate, history, policy).",
  "backend/src/controllers/gpaController.js": "Turns web requests into service calls.",
  "backend/src/services/gpaCalculationService.js": "Computes the credit-weighted GPA with half-up rounding.",
  "backend/src/validation/gpaRequestValidator.js": "Checks every module before calculating.",
  "backend/src/policy/gradingPolicy.js": "The grade table (grade → points).",
  "backend/src/repositories/gpaCalculationRepository.js": "The rules any history storage must follow.",
  "backend/src/repositories/inMemoryGpaCalculationRepository.js": "History kept in memory (used by tests).",
  "backend/src/repositories/postgresGpaCalculationRepository.js": "History saved in PostgreSQL.",
  "backend/src/db/pool.js": "Opens the connection to PostgreSQL.",
  "backend/src/db/migrate.js": "Creates the tables when the server starts.",
  "backend/test/gpa.smoke.test.js": "Checks the calculation with a known example (3.42).",
  "backend/test/composed-app.smoke.test.js": "Checks the whole server over HTTP.",
  "database/migrations/001_create_gpa_calculations.sql": "Creates the calculation and module tables.",
  "openapi/openapi.json": "The API contract: addresses, inputs and outputs.",
  "test-seams/c4-test-seams.json": "List of the hooks the independent testers can use.",
  "test-seams/README.md": "How the testers use those hooks.",
  "deployment/backend.Dockerfile": "Builds the backend as a Docker image.",
  "deployment/frontend.Dockerfile": "Builds the frontend as a Docker image.",
  "deployment/static-server.mjs": "Serves the built frontend.",
  "deployment/preview-plan.json": "How the preview containers are started.",
};

// Files the zip also holds although they are not part of the app itself.
export const EVIDENCE_FILES = [
  { path: "generation-manifest.json", info: "Fingerprint of every file, what generated it and the run's digests." },
  { path: "traceability/trace-graph.json", info: "The links from each requirement to its design, code, API, database and test hooks." },
];

const TOP_ORDER = ["frontend", "backend", "database", "openapi", "test-seams", "deployment"];

export function buildTree(files) {
  const root = { name: "", path: "", folders: new Map(), files: [] };
  for (const file of files) {
    const parts = file.path.split("/");
    let node = root;
    parts.slice(0, -1).forEach((part, index) => {
      const path = parts.slice(0, index + 1).join("/");
      if (!node.folders.has(part)) node.folders.set(part, { name: part, path, folders: new Map(), files: [] });
      node = node.folders.get(part);
    });
    node.files.push({ name: parts.at(-1), path: file.path, size: file.size_bytes ?? 0 });
  }
  const finish = (node) => {
    node.folders = [...node.folders.values()].sort((a, b) => a.name.localeCompare(b.name));
    node.files.sort((a, b) => a.name.localeCompare(b.name));
    node.folders.forEach(finish);
    node.count = node.files.length + node.folders.reduce((sum, folder) => sum + folder.count, 0);
    return node;
  };
  finish(root);
  root.folders.sort((a, b) => {
    const rank = (name) => (TOP_ORDER.includes(name) ? TOP_ORDER.indexOf(name) : TOP_ORDER.length);
    return rank(a.name) - rank(b.name) || a.name.localeCompare(b.name);
  });
  return root;
}

export const describeFolder = (path) => FOLDER_INFO[path] ?? "";
export const describeFile = (path) => FILE_INFO[path] ?? "";

export function formatSize(bytes) {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

export function summarize(files) {
  const tree = buildTree(files);
  return { files: files.length, folders: tree.folders.length, bytes: files.reduce((sum, file) => sum + (file.size_bytes ?? 0), 0) };
}
