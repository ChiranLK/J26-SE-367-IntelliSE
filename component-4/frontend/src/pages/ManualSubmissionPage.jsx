import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Code2,
  Send,
  RotateCcw,
  PlayCircle,
  CheckCircle2,
  FileCode,
  Tag,
  AlertCircle,
  Copy,
  Check,
  Plus,
  X,
  Sparkles,
} from 'lucide-react';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';
import { submitCode } from '../api/submissionApi';
import { PROGRAMMING_LANGUAGES } from '../utils/constants';
import {
  getLanguageSample,
  getLanguageFilename,
  getLanguagePlaceholder,
  getLanguageCapability,
  LANGUAGE_SAMPLES,
  LANGUAGE_FILENAMES,
} from '../utils/languageSamples';

export default function ManualSubmissionPage() {
  const navigate = useNavigate();

  // Form state
  const [language, setLanguage] = useState('python');
  const [code, setCode] = useState('');
  const [testCode, setTestCode] = useState('');
  const [filename, setFilename] = useState('');
  const [requirementTagInput, setRequirementTagInput] = useState('');
  const [requirementIds, setRequirementIds] = useState([]);
  
  // UI states
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [validationDetails, setValidationDetails] = useState(null);
  const [result, setResult] = useState(null);
  const [idCopied, setIdCopied] = useState(false);

  const handleCopyId = async (id) => {
    try {
      await navigator.clipboard.writeText(id);
      setIdCopied(true);
      setTimeout(() => setIdCopied(false), 2000);
    } catch {
      setIdCopied(false);
    }
  };

  const handleAddTag = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const trimmed = requirementTagInput.trim().replace(/^,+|,+$/g, '');
      if (trimmed && !requirementIds.includes(trimmed)) {
        setRequirementIds((prev) => [...prev, trimmed]);
        setRequirementTagInput('');
      }
    }
  };

  const handleRemoveTag = (tagToRemove) => {
    setRequirementIds((prev) => prev.filter((t) => t !== tagToRemove));
  };

  const handleKeyDownInEditor = (e) => {
    // Tab key inserts 2 spaces
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = e.target.selectionStart;
      const end = e.target.selectionEnd;
      const newCode = code.substring(0, start) + '  ' + code.substring(end);
      setCode(newCode);
      // Move cursor
      setTimeout(() => {
        e.target.selectionStart = e.target.selectionEnd = start + 2;
      }, 0);
    }
    // Ctrl + Enter or Cmd + Enter to submit
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const loadSampleSnippet = () => {
    // Overwrite protection: check if editor contains custom code before replacing
    const isKnownSample = Object.values(LANGUAGE_SAMPLES).some(
      (s) => s.trim() === code.trim()
    );
    if (code.trim() && !isKnownSample) {
      const selectedLangObj = PROGRAMMING_LANGUAGES.find((l) => l.value === language);
      const confirmReplace = window.confirm(
        `Replace current editor contents with the ${selectedLangObj?.label || language} sample snippet?`
      );
      if (!confirmReplace) {
        return;
      }
    }

    const sample = getLanguageSample(language);
    setCode(sample);
    setFilename(getLanguageFilename(language));
    if (requirementIds.length === 0) {
      setRequirementIds(['REQ-TEST-01', 'REQ-PERF-01']);
    }
    setError(null);
  };

  const handleLanguageChange = (e) => {
    const newLang = e.target.value;
    setLanguage(newLang);
    // Overwrite protection: changing dropdown alone MUST NOT overwrite user-written code!
    // If the filename is empty or was set to an auto sample filename, update it to match the new language
    const isAutoSampleFilename = Object.values(LANGUAGE_FILENAMES).includes(filename);
    if (!filename || isAutoSampleFilename) {
      setFilename(getLanguageFilename(newLang));
    }
  };

  const handleReset = () => {
    setCode('');
    setTestCode('');
    setFilename('');
    setRequirementIds([]);
    setRequirementTagInput('');
    setError(null);
    setValidationDetails(null);
    setResult(null);
  };

  const handleSubmit = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    setError(null);
    setValidationDetails(null);
    setResult(null);

    // Client-side non-empty code check
    if (!code.trim()) {
      setError('Please provide non-empty source code to submit.');
      return;
    }

    setSubmitting(true);

    try {
      const payload = {
        code,
        language,
        filename: filename.trim() || null,
        requirement_ids: requirementIds,
        test_code: testCode.trim() || null,
        metadata: {
          submitted_via: 'web_frontend_manual',
          timestamp: new Date().toISOString(),
        },
      };

      const response = await submitCode(payload);
      setResult(response);
    } catch (err) {
      setError(err.message || 'Submission failed. Please check inputs.');
      if (err.details) {
        setValidationDetails(err.details);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const lineCount = code ? code.split('\n').length : 0;
  const charCount = code.length;

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">
          <Code2 size={22} color="var(--primary-400)" />
          <span>Manual Code Submission</span>
        </h1>
        <p className="page-description">
          Submit source code for automated test execution, verification, and defect analysis.
        </p>
      </div>

      {/* Post-Submission Confirmation Banner */}
      {result && (
        <Card
          style={{
            marginBottom: '1.25rem',
            borderColor: 'var(--status-passed-border)',
            backgroundColor: 'rgba(16, 185, 129, 0.04)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: '0.875rem' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: 'var(--status-passed-bg)',
                  border: '1px solid var(--status-passed-border)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--status-passed)',
                  flexShrink: 0,
                  marginTop: '2px',
                }}
              >
                <CheckCircle2 size={18} />
              </div>
              <div>
                <h3 style={{ fontSize: '0.9375rem', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                  Artifact Ingested Successfully
                </h3>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.625rem' }}>
                  Source code stored securely with identifier assigned:
                </p>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  <code
                    className="text-mono"
                    style={{
                      padding: '0.25rem 0.6rem',
                      background: 'var(--bg-input)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 'var(--radius-xs)',
                      color: 'var(--primary-300)',
                      fontSize: '0.8125rem',
                      fontWeight: 500,
                    }}
                  >
                    {result.id}
                  </code>
                  <Button
                    variant="outline"
                    size="sm"
                    icon={idCopied ? Check : Copy}
                    onClick={() => handleCopyId(result.id)}
                  >
                    {idCopied ? 'Copied' : 'Copy'}
                  </Button>
                  <Badge variant="secondary">{result.language}</Badge>
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <Button
                    variant="primary"
                    size="sm"
                    icon={PlayCircle}
                    onClick={() => navigate(`/verifications?create_for=${encodeURIComponent(result.id)}`)}
                  >
                    Initiate Verification Pipeline
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleReset}
                    icon={RotateCcw}
                  >
                    Submit Another Snippet
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Error Alert */}
      {error && (
        <Alert type="danger" title="Validation / Ingestion Error" onClose={() => setError(null)}>
          {error}
          {validationDetails && Array.isArray(validationDetails) && (
            <ul style={{ marginTop: '0.4rem', paddingLeft: '1.25rem', fontSize: '0.78rem' }}>
              {validationDetails.map((item, idx) => (
                <li key={idx}>
                  {item.loc ? `${item.loc.join(' -> ')}: ` : ''}{item.msg}
                </li>
              ))}
            </ul>
          )}
        </Alert>
      )}

      {/* Developer Workbench Workspace */}
      <Card title="Workspace Editor" subtitle="Specify programming language, metadata, and source text">
        <form onSubmit={handleSubmit} noValidate>
          
          {/* Metadata Controls Bar */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
            
            {/* Language Selection */}
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="language-select" className="form-label">
                <span>Programming Language *</span>
              </label>
              <select
                id="language-select"
                className="form-select"
                value={language}
                onChange={handleLanguageChange}
                required
              >
                {PROGRAMMING_LANGUAGES.map((lang) => (
                  <option key={lang.value} value={lang.value}>
                    {lang.label} ({lang.ext})
                  </option>
                ))}
              </select>
              <div style={{ marginTop: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                <Badge variant={getLanguageCapability(language).badgeVariant} style={{ fontSize: '0.6875rem' }}>
                  {getLanguageCapability(language).label}
                </Badge>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  {getLanguageCapability(language).description}
                </span>
              </div>
            </div>

            {/* Optional Filename */}
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="filename-input" className="form-label">
                <span>Filename (Optional)</span>
              </label>
              <input
                id="filename-input"
                type="text"
                className="form-input"
                placeholder="e.g. math_utils.py, auth_handler.js"
                value={filename}
                onChange={(e) => setFilename(e.target.value)}
                maxLength={255}
              />
            </div>
          </div>

          {/* Interactive Requirement Tag Input */}
          <div className="form-group">
            <label htmlFor="requirements-input" className="form-label">
              <span>Requirement Identifiers (Optional)</span>
              <span className="form-hint">Type ID and press Enter or comma</span>
            </label>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.35rem',
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.4rem 0.6rem',
                minHeight: '38px',
              }}
            >
              {requirementIds.map((req) => (
                <span
                  key={req}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                    fontSize: '0.75rem',
                    fontFamily: 'var(--font-mono)',
                    backgroundColor: 'var(--primary-subtle)',
                    color: 'var(--primary-300)',
                    border: '1px solid var(--primary-border)',
                    padding: '1px 6px',
                    borderRadius: '3px',
                  }}
                >
                  <span>{req}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveTag(req)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'inherit',
                      cursor: 'pointer',
                      display: 'flex',
                      padding: 0,
                    }}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
              <input
                id="requirements-input"
                type="text"
                placeholder={requirementIds.length === 0 ? "e.g. REQ-AUTH-01, REQ-PERF-01 (press Enter)" : "Add more..."}
                value={requirementTagInput}
                onChange={(e) => setRequirementTagInput(e.target.value)}
                onKeyDown={handleAddTag}
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: 'var(--text-primary)',
                  fontSize: '0.8125rem',
                  outline: 'none',
                  flex: 1,
                  minWidth: '160px',
                }}
              />
            </div>
          </div>

          {/* Code Editor Header & Textarea */}
          <div className="form-group">
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '0.35rem',
              }}
            >
              <label htmlFor="code-textarea" className="form-label" style={{ marginBottom: 0 }}>
                <span>Source Code *</span>
              </label>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.75rem' }}>
                <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {lineCount} lines • {charCount} chars
                </span>
                <button
                  type="button"
                  onClick={loadSampleSnippet}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--primary-300)',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                    fontSize: '0.75rem',
                  }}
                >
                  <Sparkles size={12} />
                  <span>Load Sample</span>
                </button>
              </div>
            </div>

            <textarea
              id="code-textarea"
              className="form-textarea code-textarea"
              rows={16}
              placeholder={getLanguagePlaceholder(language)}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={handleKeyDownInEditor}
              required
              spellCheck="false"
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              <span>Press <kbd style={{ padding: '1px 4px', background: 'var(--bg-tertiary)', borderRadius: '3px' }}>Tab</kbd> for indentation • <kbd style={{ padding: '1px 4px', background: 'var(--bg-tertiary)', borderRadius: '3px' }}>Ctrl + Enter</kbd> to submit</span>
              <span>Code is securely stored for verification; never executed in browser.</span>
            </div>
          </div>

          {/* Optional Test Suite / Oracle Editor */}
          <div className="form-group" style={{ marginTop: '1rem' }}>
            <label htmlFor="testcode-textarea" className="form-label">
              <span>Trusted Test Suite / Oracle (Optional)</span>
              <span className="form-hint">Authorized pytest test cases to verify this submission</span>
            </label>
            <textarea
              id="testcode-textarea"
              className="form-textarea code-textarea"
              rows={6}
              placeholder={`# Optional: Supply authorized test cases for verification\nfrom solution import calculate_metrics\n\ndef test_metrics():\n    assert calculate_metrics([10, 20, 30])["count"] == 3\n`}
              value={testCode}
              onChange={(e) => setTestCode(e.target.value)}
              spellCheck="false"
              style={{ minHeight: '110px' }}
            />
            <span className="form-hint">
              Verification Standard: Only explicitly authorized test cases or specifications determine correctness.
            </span>
          </div>

          {/* Workbench Footer Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1.25rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem' }}>
            <Button
              type="button"
              variant="outline"
              onClick={handleReset}
              disabled={submitting || (!code && !filename && requirementIds.length === 0)}
              icon={RotateCcw}
            >
              Clear
            </Button>
            <Button
              type="submit"
              variant="primary"
              loading={submitting}
              icon={Send}
            >
              Submit Code
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
