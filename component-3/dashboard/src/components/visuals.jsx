import { useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints.js";
import { buildPreviewRequest } from "../lib/requests.js";
import { buildUnifiedDiff } from "../lib/diff.js";
import { formatDuration } from "../lib/format.js";
import { Badge, Callout, ErrorPanel, Elapsed, Skeleton } from "./ui.jsx";

// Evidence colour code used by every chip in the dashboard:
//   real = green · simulated = amber · mock = purple · not integrated = red/grey
export const EVIDENCE = {
  real: { tone: "real", label: "REAL" },
  simulated: { tone: "sim", label: "SIMULATED" },
  mock: { tone: "mock", label: "MOCKED_TEST_DOUBLE" },
  none: { tone: "bad-soft", label: "NOT INTEGRATED" },
};

export function EvidenceChip({ kind, children }) {
  const spec = EVIDENCE[kind] ?? EVIDENCE.none;
  return (
    <Badge tone={spec.tone} title={`Evidence class: ${spec.label}`}>
      {children ?? spec.label}
    </Badge>
  );
}

// ---------------------------------------------------------------- file grid

const splitPath = (path) => {
  const index = path.lastIndexOf("/");
  return index < 0 ? { dir: "", name: path } : { dir: path.slice(0, index), name: path.slice(index + 1) };
};

export function FileGrid({ files }) {
  return (
    <div className="file-grid" data-testid="file-grid">
      {files.map((file) => {
        const { dir, name } = splitPath(file.path);
        return (
          <div
            key={file.path}
            className={`file-tile file-tile-${file.state}`}
            data-testid="file-tile"
            data-state={file.state}
            title={file.path}
          >
            <div className="file-tile-name">{name}</div>
            {dir ? <div className="file-tile-dir">{dir}</div> : null}
            {file.state === "patched" ? <span className="file-badge file-badge-patched">patched</span> : null}
            {file.state === "identical" ? <span className="file-badge file-badge-identical">✓ byte-identical</span> : null}
            {file.state === "violation" ? <span className="file-badge file-badge-violation">changed outside scope</span> : null}
            {file.state === "untouched" ? <span className="file-badge file-badge-untouched">no patch applied</span> : null}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- diff panel

export function DiffView({ before, after, path }) {
  const diff = useMemo(() => buildUnifiedDiff(before, after), [before, after]);
  if (diff.tooLarge) return <Callout tone="warn" title="Diff too large to render">The two files are too large for the in-browser diff.</Callout>;
  if (diff.hunks.length === 0) return <p className="muted small">No line differences between the two versions of <code>{path}</code>.</p>;
  return (
    <div className="diff" data-testid="diff-view">
      <div className="diff-head">
        <code>{path}</code>
        <span className="diff-stat-add">+{diff.added}</span>
        <span className="diff-stat-del">−{diff.removed}</span>
      </div>
      <div className="diff-body" role="table" aria-label={`Unified diff of ${path}`}>
        {diff.hunks.map((hunk) => (
          <div key={hunk.header}>
            <div className="diff-hunk">{hunk.header}</div>
            {hunk.lines.map((line, index) => (
              <div key={`${hunk.header}-${index}`} className={`diff-line diff-${line.type}`} data-testid={`diff-${line.type}`}>
                <span className="diff-no">{line.oldNo ?? ""}</span>
                <span className="diff-no">{line.newNo ?? ""}</span>
                <span className="diff-sign">{line.type === "add" ? "+" : line.type === "del" ? "-" : " "}</span>
                <span className="diff-text">{line.text}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// Reads the before/after source of each patched file through the existing read-only
// endpoints (workspace-run verifies the manifests, code-preview returns the text).
// Nothing is executed. The regeneration response itself carries hashes, not content.
export function PatchDiffPanel({ result }) {
  const versioning = result.artifact_versioning;
  const patches = result.patches ?? [];
  const [path, setPath] = useState(patches[0]?.relative_path ?? null);
  const [state, setState] = useState({ loading: false, error: null, before: null, after: null });
  const key = `${versioning?.source_workspace_relative_path}|${versioning?.new_workspace_relative_path}|${path}`;

  useEffect(() => {
    if (!versioning || !path) return undefined;
    let cancelled = false;
    setState({ loading: true, error: null, before: null, after: null });
    (async () => {
      const [beforeRun, afterRun] = await Promise.all([
        api.workspaceRun(versioning.source_workspace_relative_path),
        api.workspaceRun(versioning.new_workspace_relative_path),
      ]);
      const [before, after] = await Promise.all([
        api.codePreview(buildPreviewRequest({ run: beforeRun, relativePath: path })),
        api.codePreview(buildPreviewRequest({ run: afterRun, relativePath: path })),
      ]);
      if (!cancelled) setState({ loading: false, error: null, before, after });
    })().catch((error) => {
      if (!cancelled) setState({ loading: false, error, before: null, after: null });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (!versioning || patches.length === 0) return null;
  return (
    <div className="diff-panel">
      <div className="diff-panel-head">
        <strong>Patch diff</strong>
        <Badge tone="neutral">read-only · never executed</Badge>
        {patches.length > 1 ? (
          <div className="chip-row">
            {patches.map((patch) => (
              <button key={patch.relative_path} type="button" className={`chip chip-button${path === patch.relative_path ? " chip-active" : ""}`} onClick={() => setPath(patch.relative_path)}>
                {patch.relative_path}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {state.loading ? <Skeleton lines={5} /> : null}
      <ErrorPanel error={state.error} context="Patch diff" />
      {state.before && state.after ? (
        <>
          {state.before.truncated || state.after.truncated ? (
            <Callout tone="warn" title="Preview truncated">The backend truncated the file preview; the diff below only covers the returned text.</Callout>
          ) : null}
          <DiffView before={state.before.content} after={state.after.content} path={path} />
        </>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- run progress

export function RunningBoard({ label, startedAt, note }) {
  return (
    <div className="running-board" role="status" aria-live="polite" data-testid="running-board">
      <div className="running-head">
        <span className="spinner spinner-dark" aria-hidden="true" />
        <div>
          <strong>{label}</strong>
          <span className="muted"> · waiting for the backend</span>
          {note ? <div className="muted small">{note}</div> : null}
        </div>
        <div className="running-timer" aria-label="Elapsed time">
          <Elapsed startedAt={startedAt} />
        </div>
      </div>
      <div className="file-grid file-grid-skeleton" aria-hidden="true">
        {Array.from({ length: 8 }, (_, index) => (
          <div key={index} className="file-tile skeleton" />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- chain visual

const ICON_PATHS = {
  req: "M6 4h9l3 3v13H6z M9 10h6 M9 14h6",
  uml: "M4 6h6v5H4z M14 13h6v5h-6z M10 8.5h4v7",
  code: "M9 8l-5 4 5 4 M15 8l5 4-5 4",
  api: "M4 12h6 M14 12h6 M10 8l4 4-4 4",
  db: "M5 7c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3z M5 7v10c0 1.7 3.1 3 7 3s7-1.3 7-3V7 M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3",
  test: "M9 4h6 M10 4v6l-5 9h14l-5-9V4",
};

function Icon({ name }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

const CHAIN_STAGES = [
  { key: "requirement", label: "Requirement", icon: "req", type: "REQUIREMENT" },
  { key: "design", label: "UML / design", icon: "uml", type: "UML_ELEMENT" },
  { key: "code", label: "Code", icon: "code", type: "CODE_MODULE" },
  { key: "api", label: "API", icon: "api", type: "API_OPERATION" },
  { key: "database", label: "Database", icon: "db", type: "DATABASE_ARTIFACT" },
  { key: "tests", label: "Test hook", icon: "test", type: "TEST_HOOK" },
];

export function ChainVisual({ chain, impactIds, onSelect, needsAttention }) {
  const groups = CHAIN_STAGES.map((stage) => ({
    ...stage,
    items: stage.key === "requirement" ? [{ node: chain.requirement, link: null }] : chain[stage.key],
  }));
  return (
    <div className="chain" data-testid="chain-visual">
      {groups.map((group, index) => (
        <div key={group.key} className="chain-segment">
          <div className={`chain-stage chain-${group.key}`} data-testid="chain-stage" data-stage={group.key}>
            <div className="chain-icon"><Icon name={group.icon} /></div>
            <div className="chain-label">{group.label}</div>
            <div className="chain-nodes">
              {group.items.length === 0 ? <span className="muted small">none</span> : null}
              {group.items.map(({ node, link }) => {
                const impacted = impactIds?.has(node.node_id);
                const attention = link && needsAttention(link);
                return (
                  <button
                    key={node.node_id}
                    type="button"
                    className={`chain-node${impacted ? " chain-node-impacted" : ""}${attention ? " chain-node-warn" : ""}`}
                    data-testid="chain-node"
                    data-node-type={node.node_type}
                    data-impacted={impacted ? "true" : "false"}
                    title={`${node.node_type} · ${node.node_id}${link ? ` · ${link.relation_type} · ${link.resolution_status}` : ""}`}
                    onClick={() => link && onSelect({ node, link })}
                  >
                    {attention ? "⚠ " : ""}
                    {node.label}
                  </button>
                );
              })}
            </div>
          </div>
          {index < groups.length - 1 ? (
            <svg className="chain-arrow" viewBox="0 0 40 12" aria-hidden="true">
              <path d="M0 6h34 M28 1l6 5-6 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) : null}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- coverage ring

export function CoverageRing({ value, total, label }) {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const ratio = total === 0 ? 0 : value / total;
  return (
    <div className="ring" data-testid="coverage-ring">
      <svg viewBox="0 0 100 100" width="132" height="132" role="img" aria-label={`${value} of ${total} ${label}`}>
        <circle cx="50" cy="50" r={radius} fill="none" stroke="var(--line)" strokeWidth="9" />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke={ratio === 1 ? "var(--ok)" : "var(--warn)"}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${circumference * ratio} ${circumference}`}
          transform="rotate(-90 50 50)"
        />
      </svg>
      <div className="ring-text">
        <strong>{value}/{total}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- timeline

const STATUS_LABEL = { DONE: "DONE", NOT_RUN: "NOT RUN", REFUSED: "REFUSED", PENDING: "PENDING" };

export function PipelineTimeline({ stages }) {
  return (
    <ol className="timeline" data-testid="pipeline-timeline">
      {stages.map((stage) => (
        <li key={stage.id} className={`timeline-item timeline-${stage.status.toLowerCase()}`} data-testid="timeline-stage" data-status={stage.status}>
          <span className="timeline-dot" aria-hidden="true" />
          <div className="timeline-body">
            <strong>{stage.label}</strong>
            <div className="timeline-meta">
              <span className={`timeline-status timeline-status-${stage.status.toLowerCase()}`}>{STATUS_LABEL[stage.status]}</span>
              <EvidenceChip kind={stage.evidence.kind}>{stage.evidence.label}</EvidenceChip>
              {typeof stage.durationMs === "number" ? <span className="muted small">{formatDuration(stage.durationMs)}</span> : null}
            </div>
            {stage.detail ? <div className="muted small">{stage.detail}</div> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
