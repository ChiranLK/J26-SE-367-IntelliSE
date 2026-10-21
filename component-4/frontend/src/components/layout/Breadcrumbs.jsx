import React from 'react';
import { useLocation, Link } from 'react-router-dom';
import { Home } from 'lucide-react';

const routeNames = {
  '': 'Overview',
  'submissions': 'Submissions',
  'new': 'New Submission',
  'upload': 'New Submission',
  'verifications': 'Verification Runs',
  'defects': 'Defect Analysis',
  'xai': 'Software Explanations',
  'feedback': 'Feedback History',
};

export default function Breadcrumbs() {
  const location = useLocation();
  const pathnames = location.pathname.split('/').filter((x) => x);

  if (pathnames.length === 0) {
    return (
      <div className="breadcrumbs">
        <span className="breadcrumbs-current" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <span>Overview</span>
        </span>
      </div>
    );
  }

  return (
    <nav aria-label="Breadcrumb" className="breadcrumbs">
      <Link to="/" style={{ color: 'var(--text-muted)' }}>
        Overview
      </Link>
      {pathnames.map((value, index) => {
        const to = `/${pathnames.slice(0, index + 1).join('/')}`;
        const isLast = index === pathnames.length - 1;
        const name = routeNames[value] || value;

        return (
          <React.Fragment key={to}>
            <span className="breadcrumbs-separator" style={{ opacity: 0.4 }}>/</span>
            {isLast ? (
              <span className="breadcrumbs-current">{name}</span>
            ) : (
              <Link to={to}>{name}</Link>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}
