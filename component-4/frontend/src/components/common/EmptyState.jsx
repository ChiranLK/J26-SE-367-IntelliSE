import React from 'react';
import { Inbox } from 'lucide-react';

export default function EmptyState({
  icon: Icon = Inbox,
  title = 'No records found',
  description = 'There is currently no data stored in the backend.',
  action,
  className = '',
}) {
  return (
    <div className={`empty-state ${className}`}>
      <Icon className="empty-state-icon" />
      <h4 className="empty-state-title">{title}</h4>
      <p className="empty-state-desc">{description}</p>
      {action && <div style={{ marginTop: '0.75rem' }}>{action}</div>}
    </div>
  );
}
