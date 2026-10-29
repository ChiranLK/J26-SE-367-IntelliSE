import { api } from "../api/endpoints.js";
import { API_ENDPOINTS, fileTypeOf, groupFiles } from "../lib/behaviourFiles.js";

// Names of the generated files by role, plus the zip of the verified project folder.
export function GeneratedFiles({ files, workspaceRelativePath }) {
  return (
    <div>
      <div className="button-row">
        <a className="btn btn-primary" href={api.behaviourArchiveUrl(workspaceRelativePath)} download>
          Download project (.zip)
        </a>
      </div>
      <p className="muted small">The zip holds the verified project folder exactly as generated, ready to hand to the testers.</p>
      <div className="grid grid-2">
        {groupFiles(files).map((group) =>
          group.files.length || group.emptyNote ? (
            <div key={group.id} data-testid={`folder-${group.id}`}>
              <strong>{group.id}/</strong> <span className="muted small">{group.help}</span>
              {group.files.length ? (
                <ul className="plain-list">
                  {group.files.map((path) => (
                    <li key={path}><code>{path}</code> <span className="badge badge-neutral">{fileTypeOf(path)}</span></li>
                  ))}
                </ul>
              ) : (
                <p className="muted small">{group.emptyNote}</p>
              )}
            </div>
          ) : null,
        )}
        <div data-testid="folder-api">
          <strong>api/</strong> <span className="muted small">HTTP endpoints of the generated server (implemented in <code>server.mjs</code>, no separate API files)</span>
          <ul className="plain-list">
            {API_ENDPOINTS.map((endpoint) => (
              <li key={`${endpoint.method} ${endpoint.path}`}>
                <span className="badge badge-neutral">{endpoint.method}</span> <code>{endpoint.path}</code>{" "}
                <span className="muted small">{endpoint.help}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
