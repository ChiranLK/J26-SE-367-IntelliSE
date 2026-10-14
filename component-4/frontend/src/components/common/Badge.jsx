import React from 'react';

export default function Badge({ children, variant = 'secondary', dot = false, className = '', ...props }) {
  return (
    <span className={`badge badge-${variant} ${className}`} {...props}>
      {dot && (
        <span
          style={{
            width: '5px',
            height: '5px',
            borderRadius: '50%',
            backgroundColor: 'currentColor',
            display: 'inline-block',
            flexShrink: 0,
            opacity: 0.9,
          }}
        />
      )}
      <span>{children}</span>
    </span>
  );
}
