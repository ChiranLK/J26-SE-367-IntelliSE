import React, { useState, useEffect } from 'react';
import { Menu, Sun, Moon, Database } from 'lucide-react';
import Breadcrumbs from './Breadcrumbs';
import Button from '../common/Button';
import { checkBackendHealth } from '../../api/healthApi';

export default function Navbar({ onToggleSidebar }) {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('intelise_theme') || 'dark';
  });
  const [healthStatus, setHealthStatus] = useState({
    status: 'checking',
    latencyMs: null,
    storageBackend: null,
    isEphemeral: false,
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('intelise_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  useEffect(() => {
    let isMounted = true;

    async function pingHealth() {
      try {
        const data = await checkBackendHealth();
        if (isMounted) {
          setHealthStatus({
            status: data.status === 'ok' ? 'online' : 'offline',
            latencyMs: data.latencyMs,
            storageBackend: data.storage_backend,
            isEphemeral: data.is_ephemeral_storage,
          });
        }
      } catch {
        if (isMounted) {
          setHealthStatus({
            status: 'offline',
            latencyMs: null,
            storageBackend: null,
            isEphemeral: false,
          });
        }
      }
    }

    pingHealth();
    const interval = setInterval(pingHealth, 15000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="top-navbar">
      <div className="navbar-left">
        <button
          type="button"
          className="navbar-toggle-btn"
          onClick={onToggleSidebar}
          aria-label="Toggle navigation menu"
        >
          <Menu size={16} />
        </button>
        <Breadcrumbs />
      </div>

      <div className="navbar-right">
        {/* Connection status pill */}
        <div
          className="status-pill api-status-pill"
          title={`Backend status: ${healthStatus.status}. Storage engine: ${healthStatus.storageBackend || 'unknown'}`}
        >
          <span className={`status-dot ${healthStatus.status}`} />
          <span className="api-status-text" style={{ fontSize: '0.75rem' }}>
            {healthStatus.status === 'online' ? (
              <>
                <span style={{ fontWeight: 500 }}>API Online</span>
                {healthStatus.latencyMs !== null && (
                  <span className="api-status-latency" style={{ color: 'var(--text-muted)', marginLeft: '4px', fontFamily: 'var(--font-mono)' }}>
                    {healthStatus.latencyMs}ms
                  </span>
                )}
              </>
            ) : healthStatus.status === 'checking' ? (
              'Checking API...'
            ) : (
              'API Offline'
            )}
          </span>
        </div>

        {/* Ephemeral storage badge indicator */}
        {healthStatus.storageBackend && (
          <div
            className="status-pill storage-status-pill"
            style={{
              borderColor: healthStatus.isEphemeral ? 'var(--status-pending-border)' : 'var(--border-color)',
              color: healthStatus.isEphemeral ? 'var(--status-pending)' : 'var(--text-secondary)',
              backgroundColor: healthStatus.isEphemeral ? 'var(--status-pending-bg)' : 'var(--bg-card)',
              fontSize: '0.6875rem',
            }}
            title={
              healthStatus.isEphemeral
                ? 'Ephemeral Storage Active: Data resides in memory and will be lost on server restart.'
                : 'Persistent Storage Active'
            }
          >
            <Database size={11} />
            <span style={{ fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {healthStatus.storageBackend}
            </span>
          </div>
        )}

        {/* Theme toggle */}
        <Button
          variant="outline"
          size="sm"
          iconOnly
          icon={theme === 'dark' ? Sun : Moon}
          onClick={toggleTheme}
          title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} mode`}
          aria-label="Toggle theme"
        />
      </div>
    </header>
  );
}
