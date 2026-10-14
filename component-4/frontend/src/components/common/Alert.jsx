import React from 'react';
import { AlertCircle, CheckCircle2, Info, AlertTriangle, X } from 'lucide-react';

const iconMap = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: AlertCircle,
};

export default function Alert({
  type = 'info',
  title,
  children,
  onClose,
  className = '',
}) {
  const Icon = iconMap[type] || Info;

  return (
    <div className={`alert alert-${type} ${className}`} role="alert">
      <Icon size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        {title && <div className="alert-title">{title}</div>}
        <div style={{ wordBreak: 'break-word' }}>{children}</div>
      </div>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'inherit',
            cursor: 'pointer',
            padding: '2px',
            opacity: 0.7,
            display: 'flex',
          }}
          aria-label="Dismiss alert"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
