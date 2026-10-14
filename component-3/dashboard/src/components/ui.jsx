import { useEffect, useState } from "react";
import { shortHash } from "../lib/format.js";

const STATUS_TONE = {
  // generic gate / run statuses
  SATISFIED: "ok",
  PASS: "ok",
  SELECTED: "ok",
  RESOLVED: "ok",
  VERIFIED: "ok",
  ACTIVE: "ok",
  PROVISIONAL: "warn",
  PENDING: "warn",
  PATCHED_PENDING_INDEPENDENT_RETEST: "warn",
  REVIEW_REQUIRED: "warn",
  PARTIAL: "warn",
  UNRESOLVED: "warn",
  NOT_RUN: "neutral",
  NOT_REQUIRED: "neutral",
  NOT_INTEGRATED: "bad-soft",
  NOT_IMPLEMENTED: "bad-soft",
  BLOCKED: "bad",
  FAILED: "bad",
  FAIL: "bad",
  RETIRED: "neutral",
  // provenance
  TEMPLATE: "info",
  LOCAL_LLM: "llm",
  SIMULATED: "sim",
  MOCK: "sim",
  MOCKED_TEST_DOUBLE: "sim",
  REAL_LOCAL_OLLAMA: "llm",
};

export function Badge({ tone = "neutral", children, title }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function StatusBadge({ status, label }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  return <Badge tone={tone}>{label ?? String(status).replaceAll("_", " ")}</Badge>;
}

export function SimulatedBadge({ children = "SIMULATED" }) {
  return (
    <Badge tone="sim" title="Not real upstream or Component 4 evidence">
      {children}
    </Badge>
  );
}

export function PageHeader({ title, subtitle, badges }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle ? <p className="muted">{subtitle}</p> : null}
      </div>
      {badges ? <div className="badge-row">{badges}</div> : null}
    </header>
  );
}

export function Card({ title, subtitle, actions, children, tone }) {
  return (
    <section className={`card${tone ? ` card-${tone}` : ""}`}>
      {title || actions ? (
        <div className="card-head">
          <div>
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <p className="muted small">{subtitle}</p> : null}
          </div>
          {actions ? <div className="card-actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Callout({ tone = "info", title, children }) {
  return (
    <div className={`callout callout-${tone}`} role={tone === "bad" ? "alert" : "note"}>
      {title ? <strong>{title}</strong> : null}
      <div>{children}</div>
    </div>
  );
}

export function SimBanner({ children }) {
  return (
    <div className="sim-banner" role="note">
      <SimulatedBadge />
      <span>{children}</span>
    </div>
  );
}

export function Stat({ label, value, hint, tone }) {
  return (
    <div className={`stat${tone ? ` stat-${tone}` : ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </div>
  );
}

export function KeyValues({ items }) {
  return (
    <dl className="kv">
      {items
        .filter((item) => item && item.value !== undefined && item.value !== null && item.value !== "")
        .map((item) => (
          <div key={item.label} className="kv-row">
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
    </dl>
  );
}

export function Hash({ value, length = 14 }) {
  if (!value) return null;
  return (
    <code className="hash" title={value}>
      {shortHash(value, length)}
    </code>
  );
}

export function Table({ columns, rows, rowKey, empty = "No rows.", onRowClick, selectedKey, dense }) {
  if (!rows || rows.length === 0) return <p className="muted small">{empty}</p>;
  return (
    <div className="table-wrap">
      <table className={`table${dense ? " table-dense" : ""}`}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} style={column.width ? { width: column.width } : undefined}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const key = rowKey ? rowKey(row, index) : index;
            const clickable = typeof onRowClick === "function";
            return (
              <tr
                key={key}
                className={`${clickable ? "clickable" : ""}${selectedKey === key ? " selected" : ""}`}
                onClick={clickable ? () => onRowClick(row) : undefined}
              >
                {columns.map((column) => (
                  <td key={column.key} className={column.className}>
                    {column.render ? column.render(row) : row[column.key]}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Button({ children, onClick, loading, disabled, variant = "primary", title, type = "button" }) {
  return (
    <button
      type={type}
      className={`btn btn-${variant}`}
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      aria-busy={loading ? "true" : undefined}
    >
      {loading ? <span className="spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export function Elapsed({ startedAt }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, []);
  return <span>{((now - startedAt) / 1000).toFixed(1)} s</span>;
}

export function Loading({ label, startedAt, note }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner spinner-dark" aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        {startedAt ? (
          <span className="muted">
            {" "}
            · waiting for the backend, <Elapsed startedAt={startedAt} />
          </span>
        ) : null}
        {note ? <div className="muted small">{note}</div> : null}
      </div>
    </div>
  );
}

const KIND_TITLE = {
  network: "Backend unreachable",
  timeout: "Backend timed out",
  http: "Request rejected by the backend",
  "invalid-response": "Unreadable backend response",
  aborted: "Request cancelled",
};

// Shows exactly what the API said. Review-required style conflicts (HTTP 409) are
// amber because they are expected gate decisions, not crashes.
export function ErrorPanel({ error, context }) {
  if (!error) return null;
  const gate = error.kind === "http" && (error.status === 409 || error.status === 422);
  const errors = Array.isArray(error.errors) ? error.errors : [];
  const unavailableThroughProxy = error.kind === "http" && error.status >= 500 && errors.length === 0;
  return (
    <div className={`callout ${gate ? "callout-warn" : "callout-bad"}`} role="alert" data-testid="error-panel">
      <strong>
        {context ? `${context}: ` : ""}
        {unavailableThroughProxy
          ? "Backend or local proxy unavailable"
          : KIND_TITLE[error.kind] ?? "Request failed"}
        {error.status ? ` (HTTP ${error.status})` : ""}
      </strong>
      {errors.length ? (
        <ul className="error-list">
          {errors.map((item, index) => (
            <li key={`${item.code}-${index}`}>
              <code>{item.code}</code>
              {item.field ? <span className="muted"> at {item.field}</span> : null}
              <div>{item.message}</div>
            </li>
          ))}
        </ul>
      ) : (
        <div>{error.message}</div>
      )}
      {error.path ? <div className="muted small">Endpoint: {error.path}</div> : null}
    </div>
  );
}

export function JsonView({ value, summary = "Raw JSON" }) {
  return (
    <details className="json-view">
      <summary>{summary}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

export function ModeBadge({ mode }) {
  return mode === "MOCK" ? (
    <Badge tone="sim" title="Deterministic test-double model. Pipeline check only.">
      MOCK model
    </Badge>
  ) : (
    <Badge tone="llm" title="Output came from the configured local Ollama model.">
      REAL local Ollama
    </Badge>
  );
}

export function OriginBadge({ origin }) {
  return origin === "LOCAL_LLM" ? <Badge tone="llm">LOCAL_LLM</Badge> : <Badge tone="info">TEMPLATE</Badge>;
}
