// Line-based unified diff (pure, display only). Longest-common-subsequence on lines;
// refuses very large inputs instead of freezing the browser.

const MAX_CELLS = 4_000_000;

const splitLines = (text) => {
  if (text === "" || text == null) return [];
  const lines = String(text).split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  return lines.map((line) => line.replace(/\r$/, ""));
};

export function buildUnifiedDiff(before, after, context = 3) {
  const a = splitLines(before);
  const b = splitLines(after);
  if (a.length * b.length > MAX_CELLS) return { tooLarge: true, hunks: [], added: 0, removed: 0 };

  const table = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }

  const rows = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      rows.push({ type: "ctx", oldNo: i + 1, newNo: j + 1, text: a[i] });
      i += 1;
      j += 1;
    } else if (i < a.length && (j === b.length || table[i + 1][j] >= table[i][j + 1])) {
      // Deletions before additions, as in a conventional unified diff.
      rows.push({ type: "del", oldNo: i + 1, newNo: null, text: a[i] });
      i += 1;
    } else {
      rows.push({ type: "add", oldNo: null, newNo: j + 1, text: b[j] });
      j += 1;
    }
  }

  const added = rows.filter((row) => row.type === "add").length;
  const removed = rows.filter((row) => row.type === "del").length;
  const changedAt = rows.map((row, index) => (row.type === "ctx" ? -1 : index)).filter((index) => index >= 0);
  if (changedAt.length === 0) return { tooLarge: false, hunks: [], added, removed };

  // Merge changed rows (plus context) into hunks.
  const ranges = [];
  for (const index of changedAt) {
    const start = Math.max(0, index - context);
    const end = Math.min(rows.length - 1, index + context);
    const last = ranges[ranges.length - 1];
    if (last && start <= last.end + 1) last.end = Math.max(last.end, end);
    else ranges.push({ start, end });
  }
  const hunks = ranges.map(({ start, end }) => {
    const lines = rows.slice(start, end + 1);
    const oldLines = lines.filter((row) => row.type !== "add");
    const newLines = lines.filter((row) => row.type !== "del");
    const oldStart = oldLines[0]?.oldNo ?? 0;
    const newStart = newLines[0]?.newNo ?? 0;
    return {
      header: `@@ -${oldStart},${oldLines.length} +${newStart},${newLines.length} @@`,
      lines,
    };
  });
  return { tooLarge: false, hunks, added, removed };
}
