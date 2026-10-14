import React, { useState } from 'react';
import { Copy, Check, FileCode } from 'lucide-react';
import Badge from './Badge';

export default function CodeViewer({
  code = '',
  language = 'text',
  filename = null,
  maxHeight = '420px',
  showLineNumbers = true,
  className = '',
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      setCopied(false);
    }
  };

  const lines = (code || '').split('\n');

  return (
    <div className={`code-viewer-container ${className}`}>
      <div className="code-viewer-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <FileCode size={14} />
          <span>{filename || 'Source Code'}</span>
          <Badge variant="primary" style={{ textTransform: 'lowercase', fontSize: '0.7rem' }}>
            {language}
          </Badge>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            ({lines.length} {lines.length === 1 ? 'line' : 'lines'})
          </span>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="btn btn-outline btn-sm"
          style={{ padding: '0.2rem 0.6rem', fontSize: '0.75rem', gap: '0.35rem' }}
          title="Copy code to clipboard"
        >
          {copied ? <Check size={12} color="var(--status-passed)" /> : <Copy size={12} />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <div className="code-viewer-body" style={{ maxHeight, overflowY: 'auto' }}>
        {showLineNumbers ? (
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <tbody>
              {lines.map((line, idx) => (
                <tr key={idx} style={{ lineHeight: '1.6' }}>
                  <td
                    style={{
                      width: '40px',
                      userSelect: 'none',
                      color: 'var(--text-muted)',
                      textAlign: 'right',
                      paddingRight: '1rem',
                      verticalAlign: 'top',
                      fontSize: '0.75rem',
                      opacity: 0.6,
                    }}
                  >
                    {idx + 1}
                  </td>
                  <td style={{ verticalAlign: 'top', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    <code>{line}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <pre><code>{code}</code></pre>
        )}
      </div>
    </div>
  );
}
