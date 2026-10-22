import { useEffect, useState } from "react";
import { api } from "../api/endpoints.js";
import { fileTypeOf } from "../lib/behaviourFiles.js";
import { EVIDENCE_FILES, buildTree, describeFile, describeFolder, formatSize, summarize } from "../lib/projectTree.js";
import { useAction } from "../state/useAction.js";
import { Badge, Button, ErrorPanel } from "./ui.jsx";

// GENERATED PROJECT FILE ROW
// Show one generated file with its type, purpose and file size.
function FileRow({ file }) {
  return (
    <li className="proj-file" data-testid="project-file">
      <code>{file.name}</code>
      <Badge tone="neutral">{fileTypeOf(file.name)}</Badge>
      <span className="proj-info">{describeFile(file.path)}</span>
      <span className="proj-size">{formatSize(file.size)}</span>
    </li>
  );
}

// GENERATED PROJECT FOLDER ROW
// Show one expandable folder and recursively display its child folders and files.
function Folder({ node, open }) {
  // Find the simple explanation shown beside this folder name.
  const help = describeFolder(node.path);
  return (
    <details className="proj-folder" open={open} data-testid={`project-folder-${node.path}`}>
      <summary>
        <strong>{node.name}/</strong>
        <span className="proj-info">{help}</span>
        <span className="proj-count">{node.count} file{node.count === 1 ? "" : "s"}</span>
      </summary>
      <div className="proj-children">
        {node.folders.map((folder) => <Folder key={folder.path} node={folder} open={open} />)}
        {node.files.length ? <ul className="proj-files">{node.files.map((file) => <FileRow key={file.path} file={file} />)}</ul> : null}
      </div>
    </details>
  );
}

// GENERATED PROJECT DOWNLOAD AND OPEN-FOLDER PROCESS
// Show the project tree, download its verified zip or open its local folder.
export function ProjectTree({ files, runId }) {
  // Force the folder tree to redraw after expand/collapse changes.
  const [version, setVersion] = useState(0);

  // Track whether all displayed folders should be open or closed.
  const [allOpen, setAllOpen] = useState(true);

  // Store the generated project's local path returned by the backend.
  const [folderPath, setFolderPath] = useState(null);

  // Show brief feedback after the local path is copied.
  const [copied, setCopied] = useState(false);

  // Call the backend endpoint that opens the project in Windows File Explorer.
  const openFolder = useAction(async () => api.hybridOpenFolder(runId));

  // GENERATED PROJECT LOCATION
  // Ask the backend where this run's project folder is stored on this computer.
  useEffect(() => {
    // Ignore a late response after this component has been removed.
    let alive = true;

    // Clear an older run's path before loading the current run location.
    setFolderPath(null);

    // Load the safe backend-resolved project location.
    api.hybridLocation(runId).then((result) => alive && setFolderPath(result.path)).catch(() => {});

    // Stop future state updates when the component is closed or the run changes.
    return () => {
      alive = false;
    };
  }, [runId]);

  // COPY PROJECT PATH
  // Copy the displayed local folder path to the user's clipboard.
  const copyPath = async () => {
    try {
      // Copy the path and show a temporary success message.
      await navigator.clipboard.writeText(folderPath);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Keep the button in its normal state when clipboard access fails.
      setCopied(false);
    }
  };

  // Convert manifest file records into the folder tree shown on the page.
  const tree = buildTree(files);

  // Calculate the displayed file, folder and total-size summary.
  const summary = summarize(files);

  // Expand or collapse every generated-project folder together.
  const toggle = () => {
    setAllOpen(!allOpen);
    setVersion(version + 1);
  };

  return (
    <div data-testid="project-tree">
      <div className="button-row">
          {/* DOWNLOAD GENERATED CODE */}
          {/* Request the hash-verified project zip from the backend archive endpoint. */}
        <a className="btn btn-primary" href={api.hybridArchiveUrl(runId)} download data-testid="project-zip">Download project (.zip)</a>

          {/* Expand or collapse only the displayed folder tree. */}
        <Button variant="ghost" onClick={toggle}>{allOpen ? "Collapse all folders" : "Expand all folders"}</Button>
      </div>

      {/* OPEN GENERATED PROJECT FOLDER */}
      {/* Show the safe local path and folder actions after the backend resolves it. */}
      {folderPath ? (
        <div className="proj-location" data-testid="project-location">
          <span className="muted small">Project folder on this computer</span>
          <code className="proj-path">{folderPath}</code>
          <div className="button-row">
            {/* Ask the backend to open this exact run folder in Windows File Explorer. */}
            <Button variant="secondary" onClick={() => openFolder.run()} loading={openFolder.loading}>Open folder</Button>

            {/* Copy the same resolved folder path without opening another program. */}
            <Button variant="ghost" onClick={copyPath}>{copied ? "Copied" : "Copy path"}</Button>
          </div>
          <ErrorPanel error={openFolder.error} context="Open folder" />
        </div>
      ) : null}

      {/* Explain what the zip contains and that file fingerprints are checked first. */}
      <p className="muted small">
        {summary.files} files in {summary.folders} folders · {formatSize(summary.bytes)}. Every file is checked against its fingerprint before it is zipped.
        Unzip it to get one folder with exactly the structure below, plus the run evidence listed at the bottom.
      </p>

      {/* Display the generated project structure from manifest file records. */}
      <div className="proj-tree" key={`${version}-${allOpen}`}>
        {tree.folders.map((folder) => <Folder key={folder.path} node={folder} open={allOpen} />)}
        {tree.files.length ? <ul className="proj-files">{tree.files.map((file) => <FileRow key={file.path} file={file} />)}</ul> : null}
        {/* Display run evidence separately because it is included in the zip but not app code. */}
        <details className="proj-folder" open={allOpen}>
          <summary>
            <strong>run evidence</strong>
            <span className="proj-info">Also in the zip; not part of the app itself.</span>
            <span className="proj-count">{EVIDENCE_FILES.length} files</span>
          </summary>
          <div className="proj-children">
            <ul className="proj-files">
              {EVIDENCE_FILES.map((file) => (
                <li key={file.path} className="proj-file">
                  <code>{file.path}</code>
                  <Badge tone="neutral">JSON</Badge>
                  <span className="proj-info">{file.info}</span>
                </li>
              ))}
            </ul>
          </div>
        </details>
      </div>
    </div>
  );
}
