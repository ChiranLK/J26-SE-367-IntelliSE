import { describe, expect, it } from "vitest";
import { buildTree, describeFile, describeFolder, summarize } from "../src/lib/projectTree.js";

const FILES = [
  "README.md", "backend/package.json", "backend/src/app.js", "backend/src/services/gpaCalculationService.js",
  "database/migrations/001_create_gpa_calculations.sql", "frontend/src/App.jsx", "frontend/src/components/ModuleRow.jsx",
  "deployment/backend.Dockerfile", "openapi/openapi.json", "test-seams/c4-test-seams.json",
].map((path, index) => ({ path, size_bytes: 100 + index }));

describe("project tree", () => {
  it("nests the files by folder, in reading order, with counts", () => {
    const tree = buildTree(FILES);
    expect(tree.folders.map((folder) => folder.name)).toEqual(["frontend", "backend", "database", "openapi", "test-seams", "deployment"]);
    const frontend = tree.folders[0];
    expect(frontend.count).toBe(2);
    expect(frontend.folders[0].name).toBe("src");
    expect(frontend.folders[0].folders[0].name).toBe("components");
    expect(tree.files.map((file) => file.name)).toEqual(["README.md"]);
  });

  it("explains known folders and files in plain words and leaves unknown ones blank", () => {
    expect(describeFolder("backend/src/services")).toMatch(/GPA calculation/);
    expect(describeFile("database/migrations/001_create_gpa_calculations.sql")).toMatch(/tables/);
    expect(describeFile("something/else.txt")).toBe("");
  });

  it("summarises files, top-level folders and size", () => {
    expect(summarize(FILES)).toEqual({ files: 10, folders: 6, bytes: FILES.reduce((sum, file) => sum + file.size_bytes, 0) });
  });
});
