import React from 'react';

export default function StatCard({ title, value, icon: Icon, description, badge, className = '' }) {
  return (
    <div className={`stat-card ${className}`}>
      <div className="stat-card-top">
        <span className="stat-card-title">{title}</span>
        {Icon && (
          <div className="stat-card-icon-wrap">
            <Icon size={14} />
          </div>
        )}
      </div>
      <div className="stat-card-value">{value}</div>
      {(description || badge) && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.25rem', gap: '0.5rem' }}>
          {description && <span className="stat-card-desc">{description}</span>}
          {badge && <div>{badge}</div>}
        </div>
      )}
    </div>
  );
}
