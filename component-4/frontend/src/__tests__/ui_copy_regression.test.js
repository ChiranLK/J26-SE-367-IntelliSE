import { describe, it, expect } from 'vitest';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { scanFile, extractUserFacingText, runCopyAudit, PROHIBITED_RULES } from '../../scripts/check-ui-copy.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const FRONTEND_ROOT = path.resolve(__dirname, '../..');

describe('Automated UI Terminology Regression Checker', () => {
  it('passes the actual production codebase with zero prohibited copy violations', () => {
    const result = runCopyAudit(path.join(FRONTEND_ROOT, 'src'));
    expect(result.scannedFilesCount).toBeGreaterThan(20);
    expect(result.violations).toHaveLength(0);
  });

  it('does NOT falsely flag legitimate internal identifiers, API contracts, or React components', () => {
    const legitimateInternalSnippet = `
      import React from 'react';
      import { getComponent3Status } from '../api/verificationApi';
      
      export function LegitimateComponent({ componentProps }) {
        const component_3_job_id = 'c3-job-123';
        const isComponent3Ready = false;
        // Comments mentioning Phase 2 or Component 3 for developer reference should be ignored
        /* Block comments mentioning Milestone 1 should also be ignored */
        return (
          <div className="component-container">
            <span className="text-muted">Integration testing validates interactions between components</span>
            <span className="text-mono">{component_3_job_id}</span>
          </div>
        );
      }
    `;

    const tempFile = path.join(__dirname, 'temp_legitimate_fixture.jsx');
    fs.writeFileSync(tempFile, legitimateInternalSnippet, 'utf-8');

    try {
      const violations = scanFile(tempFile);
      expect(violations).toHaveLength(0);
    } finally {
      if (fs.existsSync(tempFile)) fs.unlinkSync(tempFile);
    }
  });

  it('accurately detects prohibited Phase, Milestone, Component-number, and Research copy', () => {
    const prohibitedSnippet = `
      import React from 'react';

      export function BadComponent() {
        return (
          <div>
            <h1>Phase 2 Queue</h1>
            <span title="Component 3 Integration">Milestone 1 Deliverable</span>
            <p>In strict compliance with research ethics, no fabricated defects are shown.</p>
            <button aria-label="Dispatch to C3">Submit</button>
            <div data-notice="provisional contract under development" />
          </div>
        );
      }
    `;

    const tempBadFile = path.join(__dirname, 'temp_prohibited_fixture.jsx');
    fs.writeFileSync(tempBadFile, prohibitedSnippet, 'utf-8');

    try {
      const violations = scanFile(tempBadFile);
      const ruleIds = violations.map((v) => v.ruleId);

      expect(ruleIds).toContain('PHASE_REFERENCE');
      expect(ruleIds).toContain('INTERNAL_COMPONENT_NUMBER');
      expect(ruleIds).toContain('MILESTONE_REFERENCE');
      expect(ruleIds).toContain('ACADEMIC_RESEARCH_DISCLAIMER');
      expect(ruleIds).toContain('COMPONENT_ABBREVIATION');

      // Check that line numbers are reported correctly
      const phaseViolation = violations.find((v) => v.ruleId === 'PHASE_REFERENCE');
      expect(phaseViolation.lineNum).toBe(7);
      expect(phaseViolation.text).toBe('Phase 2 Queue');
    } finally {
      if (fs.existsSync(tempBadFile)) fs.unlinkSync(tempBadFile);
    }
  });

  it('supports narrowly justified inline exemptions via ui-copy-ignore', () => {
    const exemptedSnippet = `
      export function JustifiedNotice() {
        return (
          <div>
            <span>Phase 2 Historical Document</span> {/* ui-copy-ignore: Historical archive document */}
          </div>
        );
      }
    `;

    const tempExemptFile = path.join(__dirname, 'temp_exempt_fixture.jsx');
    fs.writeFileSync(tempExemptFile, exemptedSnippet, 'utf-8');

    try {
      const violations = scanFile(tempExemptFile);
      expect(violations).toHaveLength(0);
    } finally {
      if (fs.existsSync(tempExemptFile)) fs.unlinkSync(tempExemptFile);
    }
  });
});
