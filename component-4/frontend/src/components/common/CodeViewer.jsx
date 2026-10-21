import React, { useState } from 'react';
import { Copy, Check, FileCode, WrapText } from 'lucide-react';
import Badge from './Badge';

export default function CodeViewer({
  code = '',
  language = 'text',
  filename = null,
  maxHeight = '420px',
  showLineNumbers = true,
  className = '',
  allowWrapToggle = true,
}) {
  const [copied, setCopied] = useState(false);
  const [wrapLines, setWrapLines] = useState(false);

  const handleCopy = async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
      } else {
        throw new Error('Clipboard API unavailable');
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for complete code copying across all contexts
      try {
        const textArea = document.createElement('textarea');
        textArea.value = code;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        textArea.style.top = '0';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        setCopied(false);
      }
    }
  };

  const lines = (code || '').split('\n');

  return (
    <div className={`code-viewer-container ${className}`}>
      <div className="code-viewer-header">
        <div className="code-viewer-header-left">
          <FileCode size={14} className="code-viewer-file-icon" />
          <span className="code-viewer-filename" title={filename || 'Source Code'}>
            {filename || 'Source Code'}
          </span>
          <Badge variant="primary" className="code-viewer-badge">
            {language}
          </Badge>
          <span className="code-viewer-lines-count">
            ({lines.length} {lines.length === 1 ? 'line' : 'lines'})
          </span>
        </div>
        <div className="code-viewer-header-actions">
          {allowWrapToggle && (
            <button
              type="button"
              onClick={() => setWrapLines((prev) => !prev)}
              className={`btn btn-outline btn-xs code-viewer-action-btn ${wrapLines ? 'active' : ''}`}
              title={wrapLines ? 'Disable line wrap (scroll horizontally)' : 'Enable line wrap'}
              aria-label={wrapLines ? 'Disable line wrap' : 'Enable line wrap'}
              style={{ padding: '0.2rem 0.5rem', fontSize: '0.72rem' }}
            >
              <WrapText size={12} />
              <span>{wrapLines ? 'Unwrap' : 'Wrap'}</span>
            </button>
          )}
          <button
            type="button"
            onClick={handleCopy}
            className="btn btn-outline btn-sm code-viewer-action-btn code-viewer-copy-btn"
            style={{ padding: '0.2rem 0.6rem', fontSize: '0.75rem', gap: '0.35rem' }}
            title="Copy code to clipboard"
            aria-label="Copy code to clipboard"
          >
            {copied ? <Check size={12} color="var(--status-passed)" /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      </div>
      <div
        className={`code-viewer-body ${wrapLines ? 'wrap-lines' : 'nowrap-lines'}`}
        style={maxHeight ? { maxHeight } : undefined}
      >
        {showLineNumbers ? (
          <table className="code-viewer-table">
            <tbody>
              {lines.map((line, idx) => (
                <tr key={idx} className="code-viewer-row">
                  <td className="code-viewer-lineno">
                    {idx + 1}
                  </td>
                  <td className="code-viewer-codecell">
                    <code>{line || '\n'}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <pre className="code-viewer-pre"><code>{code}</code></pre>
        )}
      </div>
    </div>
  );
}
