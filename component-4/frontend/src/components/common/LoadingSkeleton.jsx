import React from 'react';

export function SkeletonLine({ width = '100%', height = '16px', className = '' }) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ width, height, marginBottom: '0.5rem' }}
    />
  );
}

export function SkeletonCard({ height = '140px', className = '' }) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ width: '100%', height, borderRadius: 'var(--radius-lg)' }}
    />
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', width: '100%' }}>
      <SkeletonLine height="32px" width="100%" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ display: 'flex', gap: '1rem', width: '100%' }}>
          {Array.from({ length: cols }).map((_, j) => (
            <SkeletonLine
              key={j}
              height="24px"
              width={j === 0 ? '40%' : `${60 / (cols - 1)}%`}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export default function LoadingSkeleton({ type = 'table', ...props }) {
  if (type === 'card') return <SkeletonCard {...props} />;
  if (type === 'line') return <SkeletonLine {...props} />;
  return <SkeletonTable {...props} />;
}
