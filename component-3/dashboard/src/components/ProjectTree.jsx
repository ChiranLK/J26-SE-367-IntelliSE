import { useEffect, useState } from "react";
import { api } from "../api/endpoints.js";
import { fileTypeOf } from "../lib/behaviourFiles.js";
import { EVIDENCE_FILES, buildTree, describeFile, describeFolder, formatSize, summarize } from "../lib/projectTree.js";
import { useAction } from "../state/useAction.js";
import { Badge, Button, ErrorPanel } from "./ui.jsx";

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

function Folder({ node, open }) {
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

// The generated project as a folder tree, plus the zip of exactly these files.
export function ProjectTree({ files, runId }) {
  const [version, setVersion] = useState(0);
  const [allOpen, setAllOpen] = useState(true);
  const [folderPath, setFolderPath] = useState(null);
  const [copied, setCopied] = useState(false);
  const openFolder = useAction(async () => api.hybridOpenFolder(runId));

  // Where the project folder is on this computer, in case the download does not work.
  useEffect(() => {
    let alive = true;
    setFolderPath(null);
    api.hybridLocation(runId).then((result) => alive && setFolderPath(result.path)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [runId]);

  const copyPath = async () => {
    try {
      await navigator.clipboard.writeText(folderPath);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };
  const tree = buildTree(files);
  const summary = summarize(files);
  const toggle = () => {
    setAllOpen(!allOpen);
    setVersion(version + 1);
  };

  return (
    <div data-testid="project-tree">
      <div className="button-row">
        <a className="btn btn-primary" href={api.hybridArchiveUrl(runId)} download data-testid="project-zip">Download project (.zip)</a>
        <Button variant="ghost" onClick={toggle}>{allOpen ? "Collapse all folders" : "Expand all folders"}</Button>
      </div>
      {folderPath ? (
        <div className="proj-location" data-testid="project-location">
          <span className="muted small">Project folder on this computer</span>
          <code className="proj-path">{folderPath}</code>
          <div className="button-row">
            <Button variant="secondary" onClick={() => openFolder.run()} loading={openFolder.loading}>Open folder</Button>
            <Button variant="ghost" onClick={copyPath}>{copied ? "Copied" : "Copy path"}</Button>
          </div>
          <ErrorPanel error={openFolder.error} context="Open folder" />
        </div>
      ) : null}
      <p className="muted small">
        {summary.files} files in {summary.folders} folders · {formatSize(summary.bytes)}. Every file is checked against its fingerprint before it is zipped.
        Unzip it to get one folder with exactly the structure below, plus the run evidence listed at the bottom.
      </p>
      <div className="proj-tree" key={`${version}-${allOpen}`}>
        {tree.folders.map((folder) => <Folder key={folder.path} node={folder} open={allOpen} />)}
        {tree.files.length ? <ul className="proj-files">{tree.files.map((file) => <FileRow key={file.path} file={file} />)}</ul> : null}
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
