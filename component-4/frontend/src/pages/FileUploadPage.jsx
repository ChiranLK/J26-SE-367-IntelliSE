import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UploadCloud,
  FileCode,
  CheckCircle2,
  AlertTriangle,
  PlayCircle,
  RotateCcw,
  Upload,
  X,
  Copy,
  Check,
  File,
  Sparkles,
} from 'lucide-react';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';
import { uploadSourceFile } from '../api/submissionApi';
import {
  ALLOWED_EXTENSIONS,
  MAX_UPLOAD_SIZE_BYTES,
  MAX_UPLOAD_SIZE_LABEL,
  PROGRAMMING_LANGUAGES,
} from '../utils/constants';
import {
  formatBytes,
  detectLanguageFromFilename,
  isAllowedExtension,
} from '../utils/formatters';
import ProjectFileTree from '../components/common/ProjectFileTree';
import CodeViewer from '../components/common/CodeViewer';

export default function FileUploadPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  // File state
  const [selectedFile, setSelectedFile] = useState(null);
  const [detectedLang, setDetectedLang] = useState(null);
  const [overrideLanguage, setOverrideLanguage] = useState('');
  const [requirementIds, setRequirementIds] = useState('');
  const [activeProjectFile, setActiveProjectFile] = useState(null);

  // UI state
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
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

  const validateAndSetFile = (file) => {
    setError(null);
    setResult(null);

    if (!file) return;

    if (!isAllowedExtension(file.name)) {
      setError(
        `Invalid file extension for "${file.name}". Allowed extensions: ${ALLOWED_EXTENSIONS.join(', ')}`
      );
      setSelectedFile(null);
      setDetectedLang(null);
      return;
    }

    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setError(
        `File exceeds maximum limit (${formatBytes(file.size)}). Maximum permitted upload size is ${MAX_UPLOAD_SIZE_LABEL}.`
      );
      setSelectedFile(null);
      setDetectedLang(null);
      return;
    }

    if (file.size === 0) {
      setError('Selected file is empty (0 bytes). Please select a file with valid source code.');
      setSelectedFile(null);
      setDetectedLang(null);
      return;
    }

    setSelectedFile(file);
    const lang = detectLanguageFromFilename(file.name);
    setDetectedLang(lang);
    if (lang) {
      setOverrideLanguage(lang);
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    validateAndSetFile(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    validateAndSetFile(file);
  };

  const handleClear = () => {
    setSelectedFile(null);
    setDetectedLang(null);
    setOverrideLanguage('');
    setRequirementIds('');
    setError(null);
    setResult(null);
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedFile) {
      setError('Please select a valid source code file to upload.');
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setError(null);
    setResult(null);

    try {
      const response = await uploadSourceFile({
        file: selectedFile,
        language: overrideLanguage || undefined,
        requirement_ids: requirementIds.trim() || undefined,
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percent);
          }
        },
      });

      setResult(response);
      if (response.metadata?.is_multi_file && response.metadata?.entrypoint) {
        setActiveProjectFile(response.metadata.entrypoint);
      }
      setUploadProgress(100);
    } catch (err) {
      setError(err.message || 'File upload failed. Please verify the file and backend status.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">
          <UploadCloud size={22} color="var(--primary-400)" />
          <span>Source File & Project Upload</span>
        </h1>
        <p className="page-description">
          Upload individual Python source files or complete Python project ZIP archives for autonomous verification.
        </p>
      </div>

      {/* Success Notification Box */}
      {result && (
        <Card
          style={{
            marginBottom: '1.25rem',
            borderColor: 'var(--status-passed-border)',
            backgroundColor: 'rgba(16, 185, 129, 0.04)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.875rem' }}>
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
            <div style={{ flex: 1, minWidth: '240px' }}>
              <h3 style={{ fontSize: '0.9375rem', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                {result.metadata?.is_multi_file ? 'Multi-File Python Project Upload Complete' : 'Source File Upload Complete'}
              </h3>
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.625rem' }}>
                {result.metadata?.is_multi_file ? (
                  <>
                    Project archive <strong style={{ color: 'var(--text-primary)' }}>{result.filename}</strong> safely unpacked in memory ({result.metadata.file_count} files, {result.metadata.python_file_count} Python modules). Discovered {result.metadata.test_files?.length || 0} test files.
                  </>
                ) : (
                  <>
                    File <strong style={{ color: 'var(--text-primary)' }}>{result.filename}</strong> has been ingested and classified under <Badge variant="primary">{result.language}</Badge>.
                  </>
                )}
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
              </div>

              {/* Multi-file Project Tree & Source Preview */}
              {result.metadata?.is_multi_file && result.metadata?.project_files && (
                <div style={{ margin: '1rem 0', display: 'grid', gridTemplateColumns: 'minmax(220px, 260px) minmax(0, 1fr)', gap: '0.75rem', minWidth: 0 }}>
                  <div style={{ minWidth: 0, minHeight: 0 }}>
                    <ProjectFileTree
                      files={result.metadata.project_files}
                      selectedFile={activeProjectFile || result.metadata.entrypoint}
                      onSelectFile={(path) => setActiveProjectFile(path)}
                      entrypoint={result.metadata.entrypoint}
                    />
                  </div>
                  <div style={{ minWidth: 0, minHeight: 0 }}>
                    <CodeViewer
                      code={result.metadata.project_files[activeProjectFile || result.metadata.entrypoint] || result.code}
                      language="python"
                      filename={activeProjectFile || result.metadata.entrypoint}
                      maxHeight="280px"
                    />
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <Button
                  variant="primary"
                  size="sm"
                  icon={PlayCircle}
                  onClick={() => navigate(`/verifications?create_for=${encodeURIComponent(result.id)}`)}
                >
                  Initiate Verification Run
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleClear}
                  icon={RotateCcw}
                >
                  Upload Another File
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Error Alert */}
      {error && (
        <Alert type="danger" title="File Validation Alert" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Upload Zone & Configuration */}
      <Card title="Upload Source File" subtitle="Select a local source file or drop it into the target zone">
        <form onSubmit={handleSubmit}>
          
          {/* Minimalist Dropzone */}
          <div
            className={`dropzone ${isDragOver ? 'dragover' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                fileInputRef.current?.click();
              }
            }}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              style={{ display: 'none' }}
              accept={ALLOWED_EXTENSIONS.join(',')}
            />
            <UploadCloud className="dropzone-icon" />
            <div className="dropzone-title">
              {selectedFile ? 'Replace selected file' : 'Click to select or drag and drop code file'}
            </div>
            <div className="dropzone-desc">
              Maximum file size: {MAX_UPLOAD_SIZE_LABEL}. Files are stored securely and never executed in browser.
            </div>
          </div>

          {/* Selected File Card */}
          {selectedFile && (
            <div
              style={{
                marginTop: '1rem',
                padding: '0.75rem 1rem',
                backgroundColor: 'var(--bg-tertiary)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-color)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '0.5rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                <FileCode size={20} color="var(--primary-400)" />
                <div>
                  <div style={{ fontWeight: 500, color: 'var(--text-primary)', fontSize: '0.875rem' }}>
                    {selectedFile.name}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {formatBytes(selectedFile.size)} • {selectedFile.type || 'text/plain'}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {detectedLang && (
                  <Badge variant="primary">
                    Auto-detected: {detectedLang}
                  </Badge>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  iconOnly
                  icon={X}
                  onClick={handleClear}
                  title="Remove selected file"
                />
              </div>
            </div>
          )}

          {/* Upload Progress Bar */}
          {uploading && (
            <div style={{ marginTop: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '0.3rem' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Uploading payload to backend...</span>
                <span style={{ fontWeight: 600, color: 'var(--primary-400)', fontFamily: 'var(--font-mono)' }}>{uploadProgress}%</span>
              </div>
              <div style={{ width: '100%', height: '4px', background: 'var(--bg-tertiary)', borderRadius: '2px', overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${uploadProgress}%`,
                    height: '100%',
                    backgroundColor: 'var(--primary-400)',
                    transition: 'width 0.15s ease',
                  }}
                />
              </div>
            </div>
          )}

          {/* Configuration Inputs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginTop: '1.25rem' }}>
            
            {/* Language Override */}
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="override-language" className="form-label">
                <span>Programming Language Override</span>
              </label>
              <select
                id="override-language"
                className="form-select"
                value={overrideLanguage}
                onChange={(e) => setOverrideLanguage(e.target.value)}
              >
                <option value="">Auto-detect from extension</option>
                {PROGRAMMING_LANGUAGES.map((lang) => (
                  <option key={lang.value} value={lang.value}>
                    {lang.label} ({lang.ext})
                  </option>
                ))}
              </select>
            </div>

            {/* Requirement Identifiers */}
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="upload-requirements" className="form-label">
                <span>Requirement Identifiers (Optional)</span>
              </label>
              <input
                id="upload-requirements"
                type="text"
                className="form-input"
                placeholder="e.g. REQ-AUTH-01, REQ-PERF-01"
                value={requirementIds}
                onChange={(e) => setRequirementIds(e.target.value)}
              />
            </div>
          </div>

          {/* Supported Extensions Pills */}
          <div style={{ marginTop: '1.25rem', paddingTop: '0.875rem', borderTop: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.4rem', fontWeight: 500 }}>
              Allowed file extensions:
            </span>
            <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
              {ALLOWED_EXTENSIONS.map((ext) => {
                const isSelected = selectedFile && selectedFile.name.endsWith(ext);
                return (
                  <span
                    key={ext}
                    style={{
                      fontSize: '0.6875rem',
                      fontFamily: 'var(--font-mono)',
                      padding: '2px 6px',
                      borderRadius: 'var(--radius-xs)',
                      backgroundColor: isSelected ? 'var(--primary-subtle)' : 'var(--bg-input)',
                      color: isSelected ? 'var(--primary-300)' : 'var(--text-secondary)',
                      border: isSelected ? '1px solid var(--primary-border)' : '1px solid var(--border-color)',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {ext}
                  </span>
                );
              })}
            </div>
          </div>

          {/* Footer Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
            <Button
              type="button"
              variant="outline"
              onClick={handleClear}
              disabled={uploading || !selectedFile}
              icon={RotateCcw}
            >
              Reset
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={!selectedFile || uploading}
              loading={uploading}
              icon={Upload}
            >
              Upload File
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
