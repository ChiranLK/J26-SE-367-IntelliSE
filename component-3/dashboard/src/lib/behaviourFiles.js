// Groups a behaviour manifest's files by role. Nothing is moved on disk; this only labels them.
export const FILE_GROUPS = [
  { id: "frontend", help: "React + Vite UI (JSX components), built to static files and served by the Node server" },
  { id: "backend", help: "Node.js ES modules: server, runtime and domain logic" },
  { id: "test-seams", help: "Interfaces the independent testers attach to", emptyNote: "This generator path does not produce test seams." },
  { id: "spec", help: "Class and API contract the code was generated from" },
  { id: "docs", help: "Read me" },
];

// Runs generated before the React frontend had no frontend/ and backend/ folders (public/, server.mjs, src/ at the root).
export const isLegacyLayout = (files) => files.some((file) => file.relative_path === "server.mjs");

export function groupOf(relativePath) {
  if (relativePath === "backend/behaviour-spec.json" || relativePath === "behaviour-spec.json") return "spec";
  const [first] = relativePath.split("/");
  if (first === "frontend" || first === "public") return "frontend";
  if (first === "backend" || first === "src" || relativePath === "server.mjs" || relativePath === "runtime.mjs") return "backend";
  return "docs";
}

export function groupFiles(files) {
  return FILE_GROUPS.map((group) => ({
    ...group,
    files: files.filter((file) => groupOf(file.relative_path) === group.id).map((file) => file.relative_path),
  }));
}

const FILE_TYPES = { html: "HTML", css: "CSS", js: "JavaScript", mjs: "JavaScript (ES module)", jsx: "React (JSX)", json: "JSON", md: "Markdown", sql: "SQL", dockerfile: "Docker" };

export function fileTypeOf(relativePath) {
  const extension = relativePath.includes(".") ? relativePath.split(".").pop().toLowerCase() : "";
  return FILE_TYPES[extension] ?? "File";
}

// The generated server is a fixed template (see SERVER_MJS), so its routes are the same for every run.
export const API_ENDPOINTS = [
  { method: "GET", path: "/api/spec", help: "Class and method contract the app was generated from" },
  { method: "GET", path: "/api/state", help: "Current field values of the facade class and the call log" },
  { method: "POST", path: "/api/invoke", help: "Call one public method of the facade class: { method, args }" },
  { method: "POST", path: "/api/reset", help: "Start again with a fresh facade object" },
];

/** Methods that take a list of objects (for example calculate(modules: ModuleResult[])): the behaviour generator cannot build these. */
export function listParameters(designContext) {
  return (designContext?.classes ?? []).flatMap((item) =>
    (item.methods ?? []).flatMap((method) =>
      (method.parameters ?? [])
        .filter((parameter) => String(parameter.type_name ?? "").endsWith("[]"))
        .map((parameter) => `${item.name}.${method.name}(${parameter.name}: ${parameter.type_name})`),
    ),
  );
}
