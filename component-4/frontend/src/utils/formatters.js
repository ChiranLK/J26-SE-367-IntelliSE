/**
 * Formatting utilities for dates, bytes, and strings.
 */
import { ALLOWED_EXTENSIONS, PROGRAMMING_LANGUAGES } from './constants';

export function formatDate(dateString) {
  if (!dateString) return '—';
  try {
    const d = new Date(dateString);
    if (isNaN(d.getTime())) return dateString;
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(d);
  } catch {
    return dateString;
  }
}

export function formatRelativeTime(dateString) {
  if (!dateString) return '—';
  try {
    const d = new Date(dateString);
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - d.getTime()) / 1000);
    if (diffSec < 5) return 'just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return dateString;
  }
}

export function formatBytes(bytes, decimals = 1) {
  if (bytes === 0) return '0 B';
  if (!bytes || isNaN(bytes)) return '—';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export function truncateId(id, len = 12) {
  if (!id) return '';
  if (id.length <= len) return id;
  return `${id.slice(0, len)}...`;
}

export function detectLanguageFromFilename(filename) {
  if (!filename) return null;
  const extMatch = filename.match(/\.[0-9a-z]+$/i);
  if (!extMatch) return null;
  const ext = extMatch[0].toLowerCase();
  
  const extToLang = {
    '.py': 'python',
    '.zip': 'python',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.java': 'java',
    '.cpp': 'cpp',
    '.hpp': 'cpp',
    '.c': 'c',
    '.h': 'c',
    '.cs': 'csharp',
    '.go': 'go',
    '.rs': 'rust',
  };
  return extToLang[ext] || null;
}

export function isAllowedExtension(filename) {
  if (!filename) return false;
  const extMatch = filename.match(/\.[0-9a-z]+$/i);
  if (!extMatch) return false;
  const ext = extMatch[0].toLowerCase();
  return ALLOWED_EXTENSIONS.includes(ext);
}
