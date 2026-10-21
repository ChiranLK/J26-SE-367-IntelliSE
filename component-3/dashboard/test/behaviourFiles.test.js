import { describe, expect, it } from "vitest";
import { groupFiles, groupOf, isLegacyLayout } from "../src/lib/behaviourFiles.js";

describe("behaviour file grouping", () => {
  it("puts every file of the React layout under frontend or backend", () => {
    expect(groupOf("frontend/src/App.jsx")).toBe("frontend");
    expect(groupOf("backend/src/domain.mjs")).toBe("backend");
    expect(groupOf("backend/behaviour-spec.json")).toBe("spec");
    expect(groupOf("README.md")).toBe("docs");
  });

  it("still sorts a run from the older layout correctly and flags it", () => {
    const files = ["public/app.js", "server.mjs", "runtime.mjs", "src/domain.mjs", "behaviour-spec.json", "README.md"].map((relative_path) => ({ relative_path }));
    expect(isLegacyLayout(files)).toBe(true);
    const groups = Object.fromEntries(groupFiles(files).map((group) => [group.id, group.files]));
    expect(groups.frontend).toEqual(["public/app.js"]);
    expect(groups.backend).toEqual(["server.mjs", "runtime.mjs", "src/domain.mjs"]);
    expect(groups.spec).toEqual(["behaviour-spec.json"]);
    expect(groups.docs).toEqual(["README.md"]);
    expect(isLegacyLayout([{ relative_path: "backend/server.mjs" }])).toBe(false);
  });
});
