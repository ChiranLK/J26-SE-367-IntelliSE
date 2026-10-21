import React, { useState } from 'react';
import {
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  AlertCircle,
  CheckCircle,
  ChevronRight,
  ChevronDown,
  Sparkles,
} from 'lucide-react';
import Badge from './Badge';

/**
 * Builds a nested folder tree structure from a flat map of { "path/to/file.py": "content" }
 */
function buildTree(files) {
  const root = { name: '', isDirectory: true, children: {} };

  Object.keys(files || {}).forEach((filePath) => {
    const parts = filePath.replace(/\\/g, '/').split('/');
    let current = root;

    parts.forEach((part, index) => {
      const isLast = index === parts.length - 1;
      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          path: parts.slice(0, index + 1).join('/'),
          isDirectory: !isLast,
          children: {},
        };
      }
      current = current.children[part];
    });
  });

  return root;
}

export default function ProjectFileTree({
  files = {},
  selectedFile = null,
  onSelectFile = () => {},
  defects = [],
  repairedFile = null,
  entrypoint = null,
  maxHeight = null,
  className = '',
}) {
  const [collapsedFolders, setCollapsedFolders] = useState({});

  // Group defects by file path
  const defectCountsByFile = {};
  (defects || []).forEach((d) => {
    const p = (d.file_path || '').replace(/\\/g, '/');
    defectCountsByFile[p] = (defectCountsByFile[p] || 0) + 1;
  });

  const toggleFolder = (folderPath) => {
    setCollapsedFolders((prev) => ({
      ...prev,
      [folderPath]: !prev[folderPath],
    }));
  };

  const renderNode = (node, depth = 0) => {
    if (!node.isDirectory) {
      const isSelected = selectedFile === node.path;
      const defectCount = defectCountsByFile[node.path] || 0;
      const isRepaired = repairedFile === node.path;
      const isEntry = entrypoint === node.path;

      return (
        <div
          key={node.path}
          onClick={() => onSelectFile(node.path)}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.35rem 0.6rem',
            paddingLeft: `${depth * 1.1 + 0.6}rem`,
            fontSize: '0.8125rem',
            cursor: 'pointer',
            borderRadius: 'var(--radius-xs)',
            marginBottom: '1px',
            backgroundColor: isSelected
              ? 'rgba(59, 130, 246, 0.15)'
              : 'transparent',
            color: isSelected
              ? 'var(--primary-300)'
              : defectCount > 0
              ? 'var(--status-failed)'
              : 'var(--text-secondary)',
            fontWeight: isSelected ? 600 : 400,
            transition: 'background-color 0.15s ease',
            minWidth: 0,
            gap: '0.4rem',
          }}
          className="project-file-item"
          title={node.path}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', overflow: 'hidden', minWidth: 0, flex: 1 }}>
            <FileCode size={14} style={{ flexShrink: 0, opacity: isSelected ? 1 : 0.7 }} />
            <span
              style={{
                textOverflow: 'ellipsis',
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                minWidth: 0,
              }}
            >
              {node.name}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', flexShrink: 0 }}>
            {isEntry && (
              <span
                style={{
                  fontSize: '0.65rem',
                  padding: '0.1rem 0.35rem',
                  borderRadius: '3px',
                  backgroundColor: 'rgba(59, 130, 246, 0.2)',
                  color: 'var(--primary-300)',
                }}
                title="Project Entrypoint"
              >
                entry
              </span>
            )}
            {isRepaired && (
              <span
                style={{
                  fontSize: '0.65rem',
                  padding: '0.1rem 0.35rem',
                  borderRadius: '3px',
                  backgroundColor: 'rgba(16, 185, 129, 0.2)',
                  color: 'var(--status-passed)',
                }}
                title="Patched / Repaired File"
              >
                repaired
              </span>
            )}
            {defectCount > 0 && (
              <span
                style={{
                  fontSize: '0.65rem',
                  padding: '0.1rem 0.4rem',
                  borderRadius: '3px',
                  backgroundColor: 'var(--status-failed-bg)',
                  border: '1px solid var(--status-failed-border)',
                  color: 'var(--status-failed)',
                  fontWeight: 600,
                }}
                title={`${defectCount} defect(s) detected in this file`}
              >
                {defectCount} defect{defectCount > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      );
    }

    // Directory Node
    const isCollapsed = Boolean(collapsedFolders[node.path]);
    const childrenKeys = Object.keys(node.children).sort((a, b) => {
      const aIsDir = node.children[a].isDirectory;
      const bIsDir = node.children[b].isDirectory;
      if (aIsDir === bIsDir) return a.localeCompare(b);
      return aIsDir ? -1 : 1;
    });

    return (
      <div key={node.path || 'root'} style={{ marginBottom: '1px' }}>
        {node.path && (
          <div
            onClick={() => toggleFolder(node.path)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.35rem 0.6rem',
              paddingLeft: `${depth * 1.1 + 0.5}rem`,
              fontSize: '0.8125rem',
              cursor: 'pointer',
              color: 'var(--text-muted)',
              borderRadius: 'var(--radius-xs)',
              userSelect: 'none',
              minWidth: 0,
            }}
            title={node.path}
          >
            <span style={{ display: 'inline-flex', flexShrink: 0 }}>
              {isCollapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
            </span>
            <span style={{ display: 'inline-flex', flexShrink: 0 }}>
              {isCollapsed ? (
                <Folder size={14} color="var(--primary-400)" />
              ) : (
                <FolderOpen size={14} color="var(--primary-400)" />
              )}
            </span>
            <span
              style={{
                fontWeight: 500,
                color: 'var(--text-primary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                minWidth: 0,
              }}
            >
              {node.name}
            </span>
          </div>
        )}
        {!isCollapsed && (
          <div>
            {childrenKeys.map((key) => renderNode(node.children[key], node.path ? depth + 1 : depth))}
          </div>
        )}
      </div>
    );
  };

  const treeRoot = buildTree(files);
  const totalFiles = Object.keys(files || {}).length;

  return (
    <div
      className={`project-file-tree-container ${className}`}
      style={{
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-sm)',
        backgroundColor: 'var(--bg-card)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        minWidth: 0,
        width: '100%',
      }}
    >
      <div
        className="project-file-tree-header"
        style={{
          padding: '0.55rem 0.75rem',
          borderBottom: '1px solid var(--border-color)',
          backgroundColor: 'var(--bg-card-header)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
          gap: '0.5rem',
        }}
      >
        <span
          style={{
            fontSize: '0.8125rem',
            fontWeight: 600,
            color: 'var(--text-primary)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          Project Tree ({totalFiles} {totalFiles === 1 ? 'file' : 'files'})
        </span>
        {Object.keys(defectCountsByFile).length > 0 && (
          <Badge variant="danger" style={{ fontSize: '0.7rem', flexShrink: 0 }}>
            {Object.values(defectCountsByFile).reduce((a, b) => a + b, 0)} defects
          </Badge>
        )}
      </div>

      <div
        className="project-file-tree-body"
        style={{
          padding: '0.5rem 0.35rem',
          overflowY: 'auto',
          overflowX: 'hidden',
          flex: 1,
          minHeight: 0,
          ...(maxHeight ? { maxHeight } : {}),
        }}
      >
        {totalFiles === 0 ? (
          <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
            No files available.
          </div>
        ) : (
          renderNode(treeRoot)
        )}
      </div>
    </div>
  );
}
