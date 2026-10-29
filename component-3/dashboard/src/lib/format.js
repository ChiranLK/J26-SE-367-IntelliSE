export const shortHash = (value, length = 12) =>
  typeof value === "string" && value.length > length ? `${value.slice(0, length)}…` : value ?? "";

export function formatBytes(bytes) {
  if (typeof bytes !== "number") return "";
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export function formatDuration(ms) {
  if (typeof ms !== "number") return "";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function formatTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleTimeString();
}

// Server timestamps are UTC; show them in Sri Lanka time (UTC+05:30), e.g. "2026-10-22 02:27:24 (UTC+05:30)".
export function formatSriLankaTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const shifted = new Date(date.getTime() + (5 * 60 + 30) * 60000);
  return `${shifted.toISOString().slice(0, 19).replace("T", " ")} (UTC+05:30)`;
}

export const sum = (items) => items.reduce((total, value) => total + value, 0);
