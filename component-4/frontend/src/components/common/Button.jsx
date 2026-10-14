import React from 'react';
import { Loader2 } from 'lucide-react';

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  icon: Icon,
  iconRight: IconRight,
  iconOnly = false,
  type = 'button',
  className = '',
  ...props
}) {
  const sizeClass = size === 'sm' ? 'btn-sm' : size === 'lg' ? 'btn-lg' : 'btn-md';
  const iconOnlyClass = iconOnly ? 'btn-icon-only' : '';
  const iconSize = size === 'sm' ? 14 : size === 'lg' ? 18 : 15;

  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`btn btn-${variant} ${sizeClass} ${iconOnlyClass} ${className}`.trim()}
      {...props}
    >
      {loading ? (
        <Loader2
          className="btn-spinner"
          size={iconSize}
          aria-hidden="true"
        />
      ) : (
        Icon && <Icon className="btn-icon btn-icon-left" size={iconSize} aria-hidden="true" />
      )}
      {children && <span className="btn-label">{children}</span>}
      {!loading && IconRight && (
        <IconRight className="btn-icon btn-icon-right" size={iconSize} aria-hidden="true" />
      )}
    </button>
  );
}
