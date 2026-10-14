import { describe, it, expect } from 'vitest';
import {
  formatDate,
  formatRelativeTime,
  formatBytes,
  truncateId,
  detectLanguageFromFilename,
  isAllowedExtension,
} from '../utils/formatters';

describe('formatters utility', () => {
  it('formats bytes properly into human-readable strings', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(2 * 1024 * 1024)).toBe('2 MB');
    expect(formatBytes(500)).toBe('500 B');
  });

  it('truncates IDs appropriately', () => {
    expect(truncateId('sub-1234567890abcdef', 8)).toBe('sub-1234...');
    expect(truncateId('sub-123', 10)).toBe('sub-123');
    expect(truncateId('')).toBe('');
  });

  it('detects programming languages from filenames', () => {
    expect(detectLanguageFromFilename('main.py')).toBe('python');
    expect(detectLanguageFromFilename('app.js')).toBe('javascript');
    expect(detectLanguageFromFilename('Component.tsx')).toBe('typescript');
    expect(detectLanguageFromFilename('Server.java')).toBe('java');
    expect(detectLanguageFromFilename('algorithm.cpp')).toBe('cpp');
    expect(detectLanguageFromFilename('unknown.xyz')).toBe(null);
    expect(detectLanguageFromFilename('')).toBe(null);
  });

  it('validates allowed extensions matching backend configuration', () => {
    expect(isAllowedExtension('test.py')).toBe(true);
    expect(isAllowedExtension('test.js')).toBe(true);
    expect(isAllowedExtension('test.ts')).toBe(true);
    expect(isAllowedExtension('test.java')).toBe(true);
    expect(isAllowedExtension('test.exe')).toBe(false);
    expect(isAllowedExtension('test.sh')).toBe(false);
    expect(isAllowedExtension('test.bin')).toBe(false);
  });

  it('formats dates without crashing on invalid or missing input', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate(undefined)).toBe('—');
    expect(formatDate('2026-10-14T08:00:00Z')).toContain('2026');
  });

  it('formats relative times gracefully', () => {
    expect(formatRelativeTime(null)).toBe('—');
    const now = new Date().toISOString();
    expect(formatRelativeTime(now)).toBe('just now');
  });
});
