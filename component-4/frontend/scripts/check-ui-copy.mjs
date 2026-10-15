#!/usr/bin/env node
/**
 * INTELISE Frontend — Automated Terminology Regression Checker
 *
 * Scans frontend JSX and JavaScript files to verify that user-facing text conforms
 * to INTELISE professional product terminology standards and prevents prohibited
 * development/research jargon from recurring.
 *
 * Exit code:
 *   0 = Clean (no prohibited copy found)
 *   1 = Violations found
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const FRONTEND_ROOT = path.resolve(__dirname, '..');

// Prohibited user-facing terminology rules
export const PROHIBITED_RULES = [
  {
    id: 'PHASE_REFERENCE',
    name: 'Development Phase or Subphase',
    pattern: /\bphase\s*[0-9]+[a-z]?\b/i,
    description: 'Avoid internal phase designations (e.g., Phase 1, Phase 2, Phase 2A, Phase 3). Use functional descriptions instead.',
  },
  {
    id: 'MILESTONE_REFERENCE',
    name: 'Development Milestone',
    pattern: /\bmilestone\s*[0-9]+\b/i,
    description: 'Avoid internal milestone identifiers (e.g., Milestone 1, Milestone 2). Describe actual product capabilities.',
  },
  {
    id: 'INTERNAL_COMPONENT_NUMBER',
    name: 'Internal Component Number (Component 1-4)',
    pattern: /\bcomponent\s*[1-4]\b/i,
    description: 'Avoid internal numbered research components. Use "Repair Integration", "Verification Service", or product features.',
  },
  {
    id: 'COMPONENT_ABBREVIATION',
    name: 'Component Abbreviation (C1-C4)',
    pattern: /\bC[1-4]\b/,
    description: 'Avoid abbreviated component labels like C3 or C4 in user-facing text. Use "Repair Service" or "Repair Integration".',
  },
  {
    id: 'ACADEMIC_RESEARCH_DISCLAIMER',
    name: 'Academic Research Disclaimer',
    pattern: /\b(research\s+(ethics|architecture|methodology|project)|decoupled research|zero fabricated)\b/i,
    description: 'Avoid academic research disclaimers. Present features as standard, verifiable production capabilities.',
  },
  {
    id: 'PROVISIONAL_CONTRACT',
    name: 'Provisional Integration / Contract Notice',
    pattern: /\b(provisional contract|contract under development|bi-directional feedback architecture|diagnostic architecture)\b/i,
    description: 'Avoid provisional development contracts or architecture banners. Use operational messaging like "Automatic repair delivery is currently unavailable".',
  },
  {
    id: 'INTERNAL_PROVIDER_ID',
    name: 'Internal Provider Identifier',
    pattern: /\b(deterministic_evidence_v1|internal provider)\b/i,
    description: 'Avoid exposing internal provider IDs or schema tags to normal users.',
  },
];

// User-facing JSX attributes to inspect
const USER_FACING_ATTR_REGEX = /(?:title|subtitle|label|description|placeholder|aria-label|alt)\s*=\s*(["'])(.*?)\1/g;

/**
 * Strips comments from JavaScript/JSX code.
 */
function stripComments(content) {
  // Replace block comments (except those with ui-copy-ignore) with equal number of newlines to preserve line numbers
  return content.replace(/\/\*[\s\S]*?\*\//g, (match) => {
    if (match.includes('ui-copy-ignore')) {
      return match;
    }
    return '\n'.repeat((match.match(/\n/g) || []).length);
  });
}

/**
 * Extracts candidate user-facing text snippets with their 1-based line numbers.
 */
export function extractUserFacingText(fileContent, filePath = '') {
  const snippets = [];
  const lines = fileContent.split('\n');

  lines.forEach((line, index) => {
    const lineNum = index + 1;
    const trimmed = line.trim();

    // Check for inline ignore directive
    if (trimmed.includes('ui-copy-ignore')) {
      return;
    }

    // Skip single-line comments and import statements
    if (trimmed.startsWith('//') || trimmed.startsWith('import ') || trimmed.startsWith('/*')) {
      return;
    }

    // 1. Extract JSX attributes (title="...", label="...", etc.)
    let attrMatch;
    USER_FACING_ATTR_REGEX.lastIndex = 0;
    while ((attrMatch = USER_FACING_ATTR_REGEX.exec(line)) !== null) {
      snippets.push({
        text: attrMatch[2],
        lineNum,
        source: 'attribute',
        rawLine: line,
      });
    }

    // 2. Extract JSX Text nodes: text between > and <
    const jsxTextMatches = line.matchAll(/>([^<>{}\r\n]+)</g);
    for (const match of jsxTextMatches) {
      const text = match[1].trim();
      if (text.length > 1 && !/^[-•|/\\:;,\s]+$/.test(text)) {
        snippets.push({
          text,
          lineNum,
          source: 'jsx-text',
          rawLine: line,
        });
      }
    }

    // 3. User-facing notifications or UI message strings
    const msgMatches = line.matchAll(/(?:message|reason|text|notes|error)\s*:\s*(["'`])(.*?)\1/g);
    for (const match of msgMatches) {
      const text = match[2].trim();
      if (text.length > 2) {
        snippets.push({
          text,
          lineNum,
          source: 'ui-message',
          rawLine: line,
        });
      }
    }
  });

  return snippets;
}

/**
 * Scans a file and returns all violations.
 */
export function scanFile(filePath, rules = PROHIBITED_RULES) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const cleanContent = stripComments(content);
  const snippets = extractUserFacingText(cleanContent, filePath);
  const violations = [];

  for (const snippet of snippets) {
    for (const rule of rules) {
      if (rule.pattern.test(snippet.text)) {
        violations.push({
          filePath,
          lineNum: snippet.lineNum,
          text: snippet.text,
          matchedRule: rule.name,
          ruleId: rule.id,
          description: rule.description,
          rawLine: snippet.rawLine.trim(),
        });
      }
    }
  }

  return violations;
}

/**
 * Recursively scans directory for target files.
 */
function getFilesToScan(dir, fileList = []) {
  if (!fs.existsSync(dir)) return fileList;
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== 'node_modules' && entry.name !== 'dist' && entry.name !== '__tests__') {
        getFilesToScan(fullPath, fileList);
      }
    } else if (entry.isFile()) {
      if (/\.(jsx|js|html)$/.test(entry.name) && !entry.name.includes('.test.')) {
        fileList.push(fullPath);
      }
    }
  }

  return fileList;
}

/**
 * Main execution routine.
 */
export function runCopyAudit(targetDir = path.join(FRONTEND_ROOT, 'src')) {
  const files = getFilesToScan(targetDir);
  
  // Also include index.html
  const indexHtml = path.join(FRONTEND_ROOT, 'index.html');
  if (fs.existsSync(indexHtml)) {
    files.push(indexHtml);
  }

  let totalViolations = [];

  for (const file of files) {
    const fileViolations = scanFile(file);
    if (fileViolations.length > 0) {
      totalViolations = totalViolations.concat(fileViolations);
    }
  }

  return {
    scannedFilesCount: files.length,
    violations: totalViolations,
  };
}

// CLI entry point
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  let targetPath = path.join(FRONTEND_ROOT, 'src');

  if (args.includes('--fixture') && args[args.indexOf('--fixture') + 1]) {
    const fixturePath = path.resolve(args[args.indexOf('--fixture') + 1]);
    const violations = scanFile(fixturePath);
    console.log(`Scanned fixture: ${fixturePath}`);
    console.log(`Violations found: ${violations.length}`);
    process.exit(violations.length > 0 ? 1 : 0);
  }

  console.log('🔍 Running INTELISE Frontend UI Copy Audit...\n');
  const result = runCopyAudit(targetPath);

  if (result.violations.length === 0) {
    console.log(`✓ UI copy audit passed: All ${result.scannedFilesCount} inspected frontend files adhere to INTELISE professional product standards.`);
    process.exit(0);
  } else {
    console.error(`❌ UI copy audit failed: Found ${result.violations.length} prohibited terminology violation(s) across frontend files:\n`);
    result.violations.forEach((v, i) => {
      const relPath = path.relative(FRONTEND_ROOT, v.filePath);
      console.error(`  ${i + 1}. [${v.ruleId}] ${relPath}:${v.lineNum}`);
      console.error(`     Matched Text: "${v.text}"`);
      console.error(`     Issue: ${v.description}`);
      console.error(`     Line: ${v.rawLine}\n`);
    });
    process.exit(1);
  }
}
