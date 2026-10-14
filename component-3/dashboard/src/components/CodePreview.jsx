import { useEffect, useState } from "react";
import { api } from "../api/endpoints.js";
import { buildPreviewRequest } from "../lib/requests.js";
import { formatBytes } from "../lib/format.js";
import { Badge, ErrorPanel, Hash, Loading, OriginBadge } from "./ui.jsx";

// Read-only, display-only source viewer. Content is rendered as escaped text inside a
// <pre>; it is never evaluated, installed, or executed. The backend re-verifies the
// manifest and every file hash on each preview request, so a tampered workspace is
// rejected instead of displayed.
export function CodePreview({ run, path, title = "Safe code preview" }) {
  const [state, setState] = useState({ loading: false, error: null, preview: null, startedAt: null });
  const runId = run?.manifest?.generation_run_id;

  useEffect(() => {
    if (!run || !path) {
      setState({ loading: false, error: null, preview: null, startedAt: null });
      return undefined;
    }
    let cancelled = false;
    setState({ loading: true, error: null, preview: null, startedAt: Date.now() });
    api
      .codePreview(buildPreviewRequest({ run, relativePath: path }))
      .then((preview) => {
        if (!cancelled) setState({ loading: false, error: null, preview, startedAt: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ loading: false, error, preview: null, startedAt: null });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, path]);

  const { loading, error, preview, startedAt } = state;
  return (
    <div className="code-preview">
      <div className="code-preview-head">
        <strong>{title}</strong>
        <Badge tone="neutral">display only · never executed</Badge>
        {path ? <code className="small">{path}</code> : null}
      </div>
      {!path ? <p className="muted small">Select a file to preview it.</p> : null}
      {loading ? <Loading label="Verifying manifest and reading file" startedAt={startedAt} /> : null}
      <ErrorPanel error={error} context="Code preview" />
      {preview ? (
        <div>
          <div className="code-meta">
            <OriginBadge origin={preview.origin} />
            <Badge tone="neutral">{preview.artifact_type}</Badge>
            <span className="muted small">{formatBytes(preview.size_bytes)}</span>
            <Hash value={preview.sha256} />
            {preview.truncated ? <Badge tone="warn">truncated</Badge> : null}
          </div>
          <pre className="code-block" data-testid="code-block">
            {preview.content}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
