import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

/**
 * ExpandableDiagnostic
 *
 * Renders diagnostic messages, tracebacks, and assertion details with an accessible
 * toggle interaction. Long or multiline messages are rendered as a concise single-line
 * preview with a 'View Details' button; when expanded, the complete raw diagnostic is
 * shown in a scrollable, pre-formatted view that preserves whitespace and breaks unbroken strings safely.
 *
 * Short messages (<= maxLength and single-line) are displayed directly with no toggle control.
 */
export default function ExpandableDiagnostic({
  text,
  maxLength = 80,
  emptyFallback = 'None',
  variant = 'default',
  className = '',
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!text || typeof text !== 'string' || text.trim().length === 0) {
    return (
      <span className={`diagnostic-empty ${className}`.trim()} style={{ color: 'var(--text-muted)' }}>
        {emptyFallback}
      </span>
    );
  }

  const isMultiline = text.includes('\n');
  const isLong = text.length > maxLength || isMultiline;

  // Short, single-line text without overflow: render directly with no expansion controls
  if (!isLong) {
    return (
      <span
        className={`diagnostic-short diagnostic-${variant} ${className}`.trim()}
        style={{
          color: variant === 'danger' ? 'var(--status-failed)' : 'var(--text-secondary)',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.75rem',
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
        }}
      >
        {text}
      </span>
    );
  }

  // Generate concise preview: first non-empty line up to maxLength
  const lines = text.split('\n');
  const firstNonEmptyLine = lines.find((l) => l.trim().length > 0) || text;
  const previewText =
    firstNonEmptyLine.length > maxLength
      ? `${firstNonEmptyLine.slice(0, maxLength).trimEnd()}…`
      : isMultiline
      ? `${firstNonEmptyLine}…`
      : `${text.slice(0, maxLength).trimEnd()}…`;

  return (
    <div className={`expandable-diagnostic ${isExpanded ? 'expanded' : 'collapsed'} ${className}`.trim()}>
      {!isExpanded ? (
        <div className="diagnostic-preview-row">
          <span
            className={`diagnostic-preview diagnostic-${variant}`}
            title={text}
            style={{
              color: variant === 'danger' ? 'var(--status-failed)' : 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
              wordBreak: 'break-word',
              overflowWrap: 'anywhere',
            }}
          >
            {previewText}
          </span>
          <button
            type="button"
            className="btn-diagnostic-toggle"
            onClick={() => setIsExpanded(true)}
            aria-expanded={false}
            aria-label="View Details: expand complete diagnostic message"
          >
            <span>View Details</span>
            <ChevronDown size={12} aria-hidden="true" />
          </button>
        </div>
      ) : (
        <div className="diagnostic-expanded-container">
          <pre
            className={`diagnostic-full diagnostic-${variant}`}
            tabIndex={0}
            role="region"
            aria-label="Full diagnostic message"
            style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              overflowWrap: 'anywhere',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
              lineHeight: 1.45,
              padding: '0.5rem 0.625rem',
              borderRadius: 'var(--radius-xs)',
              backgroundColor: 'var(--bg-input)',
              border: '1px solid var(--border-color)',
              color: variant === 'danger' ? 'var(--status-failed)' : 'var(--text-secondary)',
              maxHeight: '220px',
              overflowY: 'auto',
              overflowX: 'auto',
              margin: '0.25rem 0 0.35rem 0',
            }}
          >
            {text}
          </pre>
          <button
            type="button"
            className="btn-diagnostic-toggle"
            onClick={() => setIsExpanded(false)}
            aria-expanded={true}
            aria-label="Hide Details: collapse diagnostic message"
          >
            <span>Hide Details</span>
            <ChevronUp size={12} aria-hidden="true" />
          </button>
        </div>
      )}
    </div>
  );
}
