import React from 'react';

export default function Card({ title, subtitle, action, children, className = '', ...props }) {
  return (
    <div className={`card ${className}`} {...props}>
      {(title || action) && (
        <div className="card-header">
          <div>
            {title && <h3 className="card-title">{title}</h3>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {action && <div className="card-action">{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
