import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Code2,
  UploadCloud,
  History,
  PlayCircle,
  AlertOctagon,
  BrainCircuit,
  RefreshCw,
  Cpu,
  Layers,
  ChevronRight,
} from 'lucide-react';

function InteliseBrandIcon({ size = 32 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="sidebar-brand-logo-svg"
      aria-hidden="true"
    >
      <rect width="32" height="32" rx="7" fill="#14161f" />
      <rect x="0.5" y="0.5" width="31" height="31" rx="6.5" stroke="rgba(255, 255, 255, 0.1)" />
      <path
        d="M10 11.5L16 8L22 11.5V18.5L16 22L10 18.5V11.5Z"
        stroke="#F59E0B"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="15" r="2.5" fill="#F59E0B" />
      <path
        d="M16 12.5V8M13.5 16.5L10 18.5M18.5 16.5L22 18.5"
        stroke="rgba(255, 255, 255, 0.35)"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function Sidebar({ isOpen, onClose }) {
  const navSections = [
    {
      section: 'Platform',
      items: [
        { to: '/', label: 'Overview', icon: LayoutDashboard },
      ],
    },
    {
      section: 'Code Submission',
      items: [
        { to: '/submissions/new', label: 'Manual Entry', icon: Code2 },
        { to: '/submissions/upload', label: 'File Upload', icon: UploadCloud },
        { to: '/submissions', label: 'Submissions', icon: History, end: true },
      ],
    },
    {
      section: 'Verification & Feedback',
      items: [
        { to: '/verifications', label: 'Verification Runs', icon: PlayCircle },
        { to: '/defects', label: 'Defect Analysis', icon: AlertOctagon, badge: 'Phase 2' },
        { to: '/xai', label: 'XAI Explanations', icon: BrainCircuit, badge: 'Phase 3' },
        { to: '/feedback', label: 'Feedback Loop', icon: RefreshCw, badge: 'Phase 3' },
      ],
    },
  ];

  return (
    <>
      <div
        className={`sidebar-backdrop ${isOpen ? 'mobile-open' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className={`sidebar ${isOpen ? 'mobile-open' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand-lockup">
            <InteliseBrandIcon size={32} />
            <div className="sidebar-brand-text">
              <div className="sidebar-brand-title-row">
                <span className="sidebar-brand-name">INTELISE</span>
              </div>
              <span className="sidebar-brand-desc">Testing & Feedback Engine</span>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {navSections.map((sec, idx) => (
            <div key={idx} style={{ marginBottom: '0.5rem' }}>
              <div className="nav-section-title">{sec.section}</div>
              {sec.items.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end || false}
                    className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                    onClick={() => {
                      if (window.innerWidth <= 768) {
                        onClose();
                      }
                    }}
                  >
                    <Icon className="nav-item-icon" />
                    <span>{item.label}</span>
                    {item.badge && <span className="nav-item-badge">{item.badge}</span>}
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
