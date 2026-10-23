import React, { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Code2,
  Send,
  RotateCcw,
  PlayCircle,
  CheckCircle2,
  FileCode,
  FileText,
  AlertCircle,
  Copy,
  Check,
  Plus,
  X,
  Sparkles,
  Paperclip,
  FolderArchive,
  ChevronDown,
  ChevronUp,
  Tag,
  Upload,
  Lock,
  Unlock,
  ShieldCheck,
  ShieldAlert,
  Cpu,
  Activity,
  Clock,
  Terminal,
  ExternalLink,
  Layers,
  Bug,
  RefreshCw,
  User,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import Card from '../components/common/Card';
import Button from '../components/common/Button';
import Badge from '../components/common/Badge';
import Alert from '../components/common/Alert';
import { submitCode, uploadSourceFile } from '../api/submissionApi';
import {
  createVerificationRun,
  executeVerificationRun,
  getVerificationRunById,
  getXaiExplanation,
  confirmDelivery,
  getDeliveryConfirmation,
} from '../api/verificationApi';
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
  formatDate,
} from '../utils/formatters';
import {
  getLanguageSample,
  getLanguageFilename,
  getLanguagePlaceholder,
  getLanguageCapability,
  LANGUAGE_SAMPLES,
  LANGUAGE_FILENAMES,
} from '../utils/languageSamples';
import { buildZipArchive } from '../utils/zipBuilder';
import ProjectFileTree from '../components/common/ProjectFileTree';
import CodeViewer from '../components/common/CodeViewer';
import GenerationIndicator from '../components/common/GenerationIndicator';
import { createDemoScenarioFile } from '../utils/demoScenario';

export default function UnifiedSubmissionPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const runIdFromUrl = searchParams.get('run_id')?.trim() || null;

  // Primary Composer State
  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('python');
  const [filename, setFilename] = useState('');
  const [attachedFiles, setAttachedFiles] = useState([]); // Array of File objects
  const [activeProjectFile, setActiveProjectFile] = useState(null);

  // Advanced Options State
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [testCode, setTestCode] = useState('');
  const [requirementTagInput, setRequirementTagInput] = useState('');
  const [requirementIds, setRequirementIds] = useState([]);

  // UI Interactive States
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const [validationDetails, setValidationDetails] = useState(null);
  const [result, setResult] = useState(null);
  const [idCopied, setIdCopied] = useState(false);
  const [runIdCopied, setRunIdCopied] = useState(false);

  // Verification & Post-Delivery State
  const [runningVerification, setRunningVerification] = useState(false);
  const [verifyingStage, setVerifyingStage] = useState('');
  const [verificationRun, setVerificationRun] = useState(null);
  const [loadingSelectedRun, setLoadingSelectedRun] = useState(false);
  const [refreshingRun, setRefreshingRun] = useState(false);
  const [authorizingDelivery, setAuthorizingDelivery] = useState(false);
  const [xaiExplanation, setXaiExplanation] = useState(null);
  const [loadingXai, setLoadingXai] = useState(false);
  const [explanationLevel, setExplanationLevel] = useState('beginner'); // 'beginner' | 'technical'
  const [activeXaiDimension, setActiveXaiDimension] = useState('overview');

  // File input refs
  const sourceFileInputRef = useRef(null);
  const zipFileInputRef = useRef(null);
  const attachmentMenuRef = useRef(null);
  const textareaRef = useRef(null);
  const verificationRequestRef = useRef(false);
  const viewEpochRef = useRef(0);
  const operationEpochRef = useRef(0);
  const internalRouteUpdateRef = useRef(null);

  // The URL is the sole source of truth for a selected historical run. A plain
  // /submissions/new navigation always represents a brand-new composer.
  useLayoutEffect(() => {
    const internalUpdate = internalRouteUpdateRef.current;
    if (
      (internalUpdate === 'verification-start' && !runIdFromUrl) ||
      (internalUpdate && internalUpdate === runIdFromUrl)
    ) {
      internalRouteUpdateRef.current = null;
      return undefined;
    }

    const viewEpoch = ++viewEpochRef.current;
    operationEpochRef.current += 1;
    verificationRequestRef.current = false;

    setVerificationRun(null);
    setXaiExplanation(null);
    setError(null);
    setValidationDetails(null);
    setRunningVerification(false);
    setVerifyingStage('');
    setRefreshingRun(false);
    setAuthorizingDelivery(false);
    setLoadingXai(false);
    setRunIdCopied(false);

    if (!runIdFromUrl) {
      setLoadingSelectedRun(false);
      setCode('');
      setLanguage('python');
      setFilename('');
      setAttachedFiles([]);
      setActiveProjectFile(null);
      setShowAdvanced(false);
      setTestCode('');
      setRequirementTagInput('');
      setRequirementIds([]);
      setAttachmentMenuOpen(false);
      setIsDragOver(false);
      setSubmitting(false);
      setUploadProgress(0);
      setResult(null);
      setIdCopied(false);
      if (sourceFileInputRef.current) sourceFileInputRef.current.value = '';
      if (zipFileInputRef.current) zipFileInputRef.current.value = '';
      return undefined;
    }

    let cancelled = false;
    setLoadingSelectedRun(true);
    (async () => {
      try {
        const run = await getVerificationRunById(runIdFromUrl);
        if (cancelled || viewEpoch !== viewEpochRef.current) return;
        setVerificationRun(run);

        // Check if delivery is confirmed and load XAI
        if (run.status === 'PASSED') {
          const expectsPostDeliveryXai = Boolean(run.delivery_confirmation?.is_delivered);
          if (expectsPostDeliveryXai) setLoadingXai(true);
          try {
            const delivery = await getDeliveryConfirmation(run.id);
            if (delivery && delivery.is_delivered) {
              if (!expectsPostDeliveryXai) setLoadingXai(true);
              const xai = await getXaiExplanation(run.id);
              if (!cancelled && viewEpoch === viewEpochRef.current) setXaiExplanation(xai);
            }
          } catch {
            // delivery not confirmed yet
          } finally {
            if (!cancelled && viewEpoch === viewEpochRef.current) setLoadingXai(false);
          }
        }
      } catch {
        if (!cancelled && viewEpoch === viewEpochRef.current) {
          setError(`Verification run "${runIdFromUrl}" could not be loaded.`);
        }
      } finally {
        if (!cancelled && viewEpoch === viewEpochRef.current) setLoadingSelectedRun(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [location.key, runIdFromUrl]);

  // Close attachment dropdown when clicking outside
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (attachmentMenuRef.current && !attachmentMenuRef.current.contains(e.target)) {
        setAttachmentMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  // Dynamic auto-expansion for ChatGPT-style composer
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      if (code) {
        const targetHeight = Math.min(Math.max(scrollHeight, 84), 380);
        textareaRef.current.style.height = `${targetHeight}px`;
      } else {
        textareaRef.current.style.height = '84px';
      }
    }
  }, [code]);

  const handleCopyId = async (id, isRunId = false) => {
    try {
      await navigator.clipboard.writeText(id);
      if (isRunId) {
        setRunIdCopied(true);
        setTimeout(() => setRunIdCopied(false), 2000);
      } else {
        setIdCopied(true);
        setTimeout(() => setIdCopied(false), 2000);
      }
    } catch {
      // ignore
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
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.selectionStart = textareaRef.current.selectionEnd = start + 2;
        }
      }, 0);
    }
    // Ctrl + Enter or Cmd + Enter to submit & run verification
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleUploadAndRunVerification();
    }
  };

  const loadSampleSnippet = () => {
    const isKnownSample = Object.values(LANGUAGE_SAMPLES).some(
      (s) => s.trim() === code.trim()
    );

    if (code.trim() && !isKnownSample) {
      const confirmReplace = window.confirm(
        `Loading a sample will replace your current editor content. Do you want to proceed?`
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
    const isAutoSampleFilename = Object.values(LANGUAGE_FILENAMES).includes(filename);
    if (!filename || isAutoSampleFilename) {
      setFilename(getLanguageFilename(newLang));
    }
  };

  const validateFile = (file) => {
    if (!file) return null;

    if (!isAllowedExtension(file.name)) {
      throw new Error(
        `Invalid file extension for "${file.name}". Allowed extensions: ${ALLOWED_EXTENSIONS.join(', ')}`
      );
    }

    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      throw new Error(
        `File "${file.name}" exceeds maximum limit (${formatBytes(file.size)}). Maximum permitted upload size is ${MAX_UPLOAD_SIZE_LABEL}.`
      );
    }

    if (file.size === 0) {
      throw new Error(`File "${file.name}" is empty (0 bytes). Please select a file with valid source code.`);
    }

    return file;
  };

  const handleSourceFilesSelected = (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    setError(null);
    try {
      const validFiles = files.map(validateFile).filter(Boolean);
      const nonZipExisting = attachedFiles.filter((f) => !f.name.toLowerCase().endsWith('.zip'));
      setAttachedFiles([...nonZipExisting, ...validFiles]);

      const firstLang = detectLanguageFromFilename(validFiles[0]?.name);
      if (firstLang && firstLang !== 'other') {
        setLanguage(firstLang);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      if (sourceFileInputRef.current) sourceFileInputRef.current.value = '';
      setAttachmentMenuOpen(false);
    }
  };

  const handleZipFileSelected = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    try {
      if (!file.name.toLowerCase().endsWith('.zip')) {
        throw new Error(`Expected a .zip archive, but received "${file.name}".`);
      }
      validateFile(file);
      setAttachedFiles([file]);
      setLanguage('python');
    } catch (err) {
      setError(err.message);
    } finally {
      if (zipFileInputRef.current) zipFileInputRef.current.value = '';
      setAttachmentMenuOpen(false);
    }
  };

  const handleRemoveAttachment = (indexToRemove) => {
    setAttachedFiles((prev) => prev.filter((_, idx) => idx !== indexToRemove));
  };

  const handleClearAttachments = () => {
    setAttachedFiles([]);
    if (sourceFileInputRef.current) sourceFileInputRef.current.value = '';
    if (zipFileInputRef.current) zipFileInputRef.current.value = '';
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
    const droppedFiles = Array.from(e.dataTransfer.files || []);
    if (!droppedFiles.length) return;

    setError(null);
    try {
      const hasZip = droppedFiles.some((f) => f.name.toLowerCase().endsWith('.zip'));
      if (hasZip) {
        const zipFile = droppedFiles.find((f) => f.name.toLowerCase().endsWith('.zip'));
        validateFile(zipFile);
        setAttachedFiles([zipFile]);
        setLanguage('python');
      } else {
        const validFiles = droppedFiles.map(validateFile).filter(Boolean);
        const nonZipExisting = attachedFiles.filter((f) => !f.name.toLowerCase().endsWith('.zip'));
        setAttachedFiles([...nonZipExisting, ...validFiles]);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleReset = () => {
    operationEpochRef.current += 1;
    viewEpochRef.current += 1;
    verificationRequestRef.current = false;
    setCode('');
    setTestCode('');
    setFilename('');
    setRequirementIds([]);
    setRequirementTagInput('');
    setAttachedFiles([]);
    setError(null);
    setValidationDetails(null);
    setResult(null);
    setUploadProgress(0);
    setVerificationRun(null);
    setXaiExplanation(null);
    setRunningVerification(false);
    setVerifyingStage('');
    setRefreshingRun(false);
    setAuthorizingDelivery(false);
    setLoadingXai(false);
    setLoadingSelectedRun(false);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('run_id');
    internalRouteUpdateRef.current = 'verification-start';
    setSearchParams(nextParams, { replace: true });
    if (sourceFileInputRef.current) sourceFileInputRef.current.value = '';
    if (zipFileInputRef.current) zipFileInputRef.current.value = '';
  };

  // Reusable submission perform function
  const performSubmission = async (operationEpoch = operationEpochRef.current) => {
    const hasPastedCode = Boolean(code && code.trim());
    const hasAttachments = attachedFiles.length > 0;

    if (!hasPastedCode && !hasAttachments) {
      throw new Error('Please provide non-empty source code or attach files to submit.');
    }

    setSubmitting(true);
    setUploadProgress(0);

    try {
      let response;

      if (hasPastedCode && !hasAttachments) {
        const payload = {
          code,
          language,
          filename: filename.trim() || getLanguageFilename(language),
          requirement_ids: requirementIds,
          test_code: testCode.trim() || null,
          metadata: {
            submitted_via: 'unified_composer_manual',
            timestamp: new Date().toISOString(),
          },
        };
        response = await submitCode(payload);
      } else if (!hasPastedCode && hasAttachments) {
        if (attachedFiles.length === 1) {
          const singleFile = attachedFiles[0];
          response = await uploadSourceFile({
            file: singleFile,
            language: singleFile.name.toLowerCase().endsWith('.zip') ? undefined : language,
            requirement_ids: requirementIds.join(','),
            onUploadProgress: (progressEvent) => {
              if (progressEvent.total) {
                const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                setUploadProgress(percent);
              }
            },
          });
        } else {
          const fileDescriptors = [];
          for (const f of attachedFiles) {
            const buffer = await f.arrayBuffer();
            fileDescriptors.push({
              name: f.name,
              data: new Uint8Array(buffer),
            });
          }
          const packagedZip = buildZipArchive(fileDescriptors, 'project_submission.zip');
          response = await uploadSourceFile({
            file: packagedZip,
            language: 'python',
            requirement_ids: requirementIds.join(','),
            onUploadProgress: (progressEvent) => {
              if (progressEvent.total) {
                const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                setUploadProgress(percent);
              }
            },
          });
        }
      } else {
        const mainFilename = filename.trim() || getLanguageFilename(language);
        const fileDescriptors = [{ name: mainFilename, data: code }];

        for (const f of attachedFiles) {
          if (f.name !== mainFilename) {
            const buffer = await f.arrayBuffer();
            fileDescriptors.push({
              name: f.name,
              data: new Uint8Array(buffer),
            });
          }
        }

        const combinedZip = buildZipArchive(fileDescriptors, 'project_submission.zip');
        response = await uploadSourceFile({
          file: combinedZip,
          language: 'python',
          requirement_ids: requirementIds.join(','),
          onUploadProgress: (progressEvent) => {
            if (progressEvent.total) {
              const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              setUploadProgress(percent);
            }
          },
        });
      }

      if (operationEpoch !== operationEpochRef.current) return null;
      setResult(response);
      if (response.metadata?.is_multi_file && response.metadata?.entrypoint) {
        setActiveProjectFile(response.metadata.entrypoint);
      }
      setUploadProgress(100);
      return response;
    } finally {
      if (operationEpoch === operationEpochRef.current) setSubmitting(false);
    }
  };

  // Submit Code only (preserves existing behavior)
  const handleSubmit = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    const operationEpoch = ++operationEpochRef.current;
    setError(null);
    setValidationDetails(null);
    setResult(null);

    try {
      await performSubmission(operationEpoch);
    } catch (err) {
      if (operationEpoch !== operationEpochRef.current) return;
      setError(err.message || 'Submission failed. Please check inputs and try again.');
      if (err.details) {
        setValidationDetails(err.details);
      }
    }
  };

  // Execute verification on a known submission ID
  const executeVerificationWorkflow = async (submissionId, operationEpoch) => {
    setVerifyingStage('Configuring verification pipeline (Unit, Integration, Performance)...');
    const run = await createVerificationRun({
      submission_id: submissionId,
      triggered_by: 'submission_workflow',
      test_types: ['unit', 'integration', 'performance'],
      trusted_test_cases: testCode.trim() || undefined,
    });
    if (operationEpoch !== operationEpochRef.current) return;

    setVerifyingStage('Executing tests inside container sandbox...');
    const executed = await executeVerificationRun(run.id, {
      trusted_test_cases: testCode.trim() || undefined,
    });
    if (operationEpoch !== operationEpochRef.current) return;

    setVerifyingStage('Retrieving verification results and telemetry...');
    const fullRun = await getVerificationRunById(executed.id || run.id);
    if (operationEpoch !== operationEpochRef.current) return;
    setVerificationRun(fullRun);

    // If verification passed, check delivery status
    if (fullRun.status === 'PASSED') {
      try {
        const delivery = await getDeliveryConfirmation(fullRun.id);
        if (delivery && delivery.is_delivered) {
          if (operationEpoch === operationEpochRef.current) setLoadingXai(true);
          try {
            const xai = await getXaiExplanation(fullRun.id);
            if (operationEpoch === operationEpochRef.current) setXaiExplanation(xai);
          } finally {
            if (operationEpoch === operationEpochRef.current) setLoadingXai(false);
          }
        } else {
          setXaiExplanation(null);
        }
      } catch {
        setXaiExplanation(null);
      }
    } else {
      setXaiExplanation(null);
    }

    if (operationEpoch !== operationEpochRef.current) return;
    internalRouteUpdateRef.current = fullRun.id;
    setSearchParams({ run_id: fullRun.id }, { replace: true });
  };

  // Single-Click Workflow: Upload + Run Verification
  const handleUploadAndRunVerification = async () => {
    if (verificationRequestRef.current || runningVerification || submitting) return;
    const operationEpoch = ++operationEpochRef.current;
    verificationRequestRef.current = true;
    setRunningVerification(true);
    setError(null);
    setValidationDetails(null);
    setVerificationRun(null);
    setXaiExplanation(null);
    setRefreshingRun(false);
    setAuthorizingDelivery(false);
    setLoadingXai(false);
    setLoadingSelectedRun(false);
    if (runIdFromUrl) {
      internalRouteUpdateRef.current = 'verification-start';
      setSearchParams({}, { replace: true });
    }

    const hasPastedCode = Boolean(code && code.trim());
    const hasAttachments = attachedFiles.length > 0;

    if (!hasPastedCode && !hasAttachments && !result?.id) {
      setError('Please provide non-empty source code or attach files to verify.');
      setRunningVerification(false);
      verificationRequestRef.current = false;
      return;
    }

    try {
      let submissionId = result?.id;
      if (!submissionId) {
        setVerifyingStage('Uploading code submission...');
        const submissionResponse = await performSubmission(operationEpoch);
        if (operationEpoch !== operationEpochRef.current) return;
        if (!submissionResponse?.id) {
          throw new Error('Failed to create code submission.');
        }
        submissionId = submissionResponse.id;
      }

      await executeVerificationWorkflow(submissionId, operationEpoch);
    } catch (err) {
      if (operationEpoch !== operationEpochRef.current) return;
      setError(err.message || 'Verification could not be completed.');
      if (err.details) {
        setValidationDetails(err.details);
      }
    } finally {
      if (operationEpoch === operationEpochRef.current) {
        setRunningVerification(false);
        setVerifyingStage('');
        verificationRequestRef.current = false;
      }
    }
  };

  // Run Verification from existing submission result box
  const handleRunVerification = async () => {
    if (!result?.id || verificationRequestRef.current || runningVerification) return;
    const operationEpoch = ++operationEpochRef.current;
    verificationRequestRef.current = true;
    setRunningVerification(true);
    setError(null);
    setVerificationRun(null);
    setXaiExplanation(null);
    if (runIdFromUrl) {
      internalRouteUpdateRef.current = 'verification-start';
      setSearchParams({}, { replace: true });
    }
    try {
      await executeVerificationWorkflow(result.id, operationEpoch);
    } catch (err) {
      if (operationEpoch !== operationEpochRef.current) return;
      setError(err.message || 'Verification could not be completed.');
    } finally {
      if (operationEpoch === operationEpochRef.current) {
        setRunningVerification(false);
        setVerifyingStage('');
        verificationRequestRef.current = false;
      }
    }
  };

  // Refresh single run status
  const handleRefreshRun = async () => {
    if (!verificationRun?.id || refreshingRun) return;
    const viewEpoch = viewEpochRef.current;
    const runId = verificationRun.id;
    setRefreshingRun(true);
    try {
      const updated = await getVerificationRunById(runId);
      if (viewEpoch !== viewEpochRef.current || runId !== updated.id) return;
      setVerificationRun(updated);
      if (updated.status === 'PASSED') {
        const delivery = await getDeliveryConfirmation(updated.id).catch(() => null);
        if (delivery && delivery.is_delivered) {
          setLoadingXai(true);
          try {
            const xai = await getXaiExplanation(updated.id).catch(() => null);
            if (viewEpoch === viewEpochRef.current) setXaiExplanation(xai);
          } finally {
            if (viewEpoch === viewEpochRef.current) setLoadingXai(false);
          }
        }
      }
    } catch (err) {
      if (viewEpoch !== viewEpochRef.current) return;
      setError(`Failed to refresh run: ${err.message}`);
    } finally {
      if (viewEpoch === viewEpochRef.current) setRefreshingRun(false);
    }
  };

  // Authorize development-only delivery simulation to unlock XAI
  const handleAuthorizeSimulatedDelivery = async () => {
    if (!verificationRun?.id || authorizingDelivery) return;
    const viewEpoch = viewEpochRef.current;
    const runId = verificationRun.id;
    setAuthorizingDelivery(true);
    setError(null);
    try {
      const delivery = await confirmDelivery(runId, {
        is_simulation: true,
        notes: 'Simulated delivery authorization confirmed for supervisor demonstration',
      });
      if (viewEpoch !== viewEpochRef.current) return;
      setVerificationRun((prev) => ({
        ...prev,
        delivery_confirmation: delivery,
      }));

      // Fetch newly unlocked post-delivery human-facing XAI
      setLoadingXai(true);
      const xai = await getXaiExplanation(runId);
      if (viewEpoch !== viewEpochRef.current) return;
      setXaiExplanation(xai);
    } catch (err) {
      if (viewEpoch !== viewEpochRef.current) return;
      setError(`Delivery authorization failed: ${err.message}`);
    } finally {
      if (viewEpoch === viewEpochRef.current) {
        setAuthorizingDelivery(false);
        setLoadingXai(false);
      }
    }
  };

  const lineCount = code ? code.split('\n').length : 0;
  const charCount = code.length;
  const isZipAttached = attachedFiles.some((f) => f.name.toLowerCase().endsWith('.zip'));
  const isMixedInput = Boolean(code && code.trim()) && attachedFiles.length > 0;

  // Extract Category Telemetry
  const agentReports = verificationRun?.execution_telemetry?.agent_reports || {};
  const testResults = verificationRun?.test_results || [];

  const unitReport = agentReports.unit;
  const unitTests = testResults.filter((t) => (t.test_type || '').toLowerCase() === 'unit');
  const unitStatus =
    unitReport?.status ||
    (unitTests.length > 0
      ? unitTests.every((t) => t.status === 'PASSED')
        ? 'PASSED'
        : 'FAILED'
      : verificationRun?.status === 'BLOCKED'
      ? 'BLOCKED'
      : 'NOT_EXECUTED');
  const unitPassedCount =
    unitReport?.passed_tests ?? unitTests.filter((t) => t.status === 'PASSED').length;
  const unitFailedCount =
    unitReport?.failed_tests ?? unitTests.filter((t) => t.status === 'FAILED').length;

  const integReport = agentReports.integration;
  const integTests = testResults.filter(
    (t) => (t.test_type || '').toLowerCase() === 'integration'
  );
  const integStatus =
    integReport?.status ||
    (integTests.length > 0
      ? integTests.every((t) => t.status === 'PASSED')
        ? 'PASSED'
        : 'FAILED'
      : verificationRun?.status === 'BLOCKED'
      ? 'BLOCKED'
      : 'NOT_EXECUTED');
  const integPassedCount =
    integReport?.passed_interactions ??
    integTests.filter((t) => t.status === 'PASSED').length;
  const integFailedCount =
    integReport?.failed_interactions ??
    integTests.filter((t) => t.status === 'FAILED').length;

  const perfReport = agentReports.performance;
  const perfMetrics = perfReport?.metrics;
  const perfStatus = perfReport?.status || (verificationRun?.status === 'BLOCKED' ? 'BLOCKED' : 'NOT_EXECUTED');
  const performanceExecuted = !['NOT_EXECUTED', 'BLOCKED', 'PENDING'].includes(perfStatus)
    && Number(perfMetrics?.sample_size || 0) > 0;

  const isDeliveryConfirmed = Boolean(verificationRun?.delivery_confirmation?.is_delivered);

  return (
    <div className="unified-submission-container animate-fade-in">
      {/* Page Header */}
      <div className="unified-submission-header">
        <h1 className="unified-submission-title">
          <Code2 size={24} className="unified-title-icon" />
          <span>New Submission</span>
        </h1>
        <p className="unified-submission-subtitle">
          Verify source code, multiple files, or complete projects with containerized Unit, Integration, and Performance testing.
        </p>
      </div>

      {/* Hidden File Inputs */}
      <input
        ref={sourceFileInputRef}
        type="file"
        multiple
        accept={ALLOWED_EXTENSIONS.filter((e) => e !== '.zip').join(',')}
        style={{ display: 'none' }}
        onChange={handleSourceFilesSelected}
      />
      <input
        ref={zipFileInputRef}
        type="file"
        accept=".zip"
        style={{ display: 'none' }}
        onChange={handleZipFileSelected}
      />

      {/* Submission Success Banner */}
      {result && (
        <Card
          style={{
            marginBottom: '1.25rem',
            borderColor: 'var(--status-passed-border)',
            backgroundColor: 'rgba(16, 185, 129, 0.04)',
          }}
        >
          <div className="submission-success-layout" style={{ display: 'flex', alignItems: 'flex-start', gap: '0.875rem' }}>
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

            <div className="submission-success-content" style={{ flex: 1, minWidth: '240px' }}>
              <h3 style={{ fontSize: '0.9375rem', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                {result.metadata?.is_multi_file
                  ? 'Multi-File Project Submission Ingested'
                  : 'Source Code Submission Ingested'}
              </h3>
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.625rem' }}>
                {result.metadata?.is_multi_file
                  ? `Extracted project archive with ${result.metadata?.total_project_files || Object.keys(result.metadata?.project_files || {}).length} files ready for containerized verification.`
                  : `Ingested ${result.filename || 'source file'} (${result.code ? result.code.length : 0} bytes) ready for verification pipeline.`}
              </p>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  flexWrap: 'wrap',
                  marginBottom: '0.875rem',
                }}
              >
                <code
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-color)',
                    padding: '0.2rem 0.5rem',
                    borderRadius: 'var(--radius-sm)',
                    fontFamily: 'var(--font-mono)',
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
                  onClick={() => handleCopyId(result.id, false)}
                >
                  {idCopied ? 'Copied' : 'Copy ID'}
                </Button>
                <Badge variant="secondary">{result.language}</Badge>
                {result.metadata?.is_multi_file && (
                  <Badge variant="primary">Multi-File Project</Badge>
                )}
              </div>

              {/* Multi-File Tree View */}
              {result.metadata?.is_multi_file && result.metadata?.project_files && (
                <div style={{ marginBottom: '1rem', width: '100%', minWidth: 0 }}>
                  <div className="submission-success-project-grid">
                    <div className="submission-project-tree-panel">
                      <ProjectFileTree
                        files={result.metadata.project_files}
                        selectedFile={activeProjectFile || result.metadata.entrypoint}
                        onSelectFile={(f) => setActiveProjectFile(f)}
                        entrypoint={result.metadata.entrypoint}
                      />
                    </div>
                    <div className="submission-project-code-panel">
                      {(activeProjectFile || result.metadata.entrypoint) ? (
                        <CodeViewer
                          code={result.metadata.project_files[activeProjectFile || result.metadata.entrypoint] || ''}
                          language="python"
                          filename={activeProjectFile || result.metadata.entrypoint}
                          title={activeProjectFile || result.metadata.entrypoint}
                          maxHeight={null}
                        />
                      ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.8125rem', textAlign: 'center', marginTop: '2rem' }}>
                          Select a project file from the directory tree to inspect contents
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <Button
                  variant="primary"
                  size="sm"
                  icon={PlayCircle}
                  onClick={handleRunVerification}
                  loading={runningVerification}
                  disabled={runningVerification}
                >
                  Run Verification
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleReset}
                  icon={RotateCcw}
                >
                  Submit Another
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/submissions?view=${encodeURIComponent(result.id)}`)}
                >
                  View Submission
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Error Alert */}
      {error && (
        <Alert type="danger" title="System Notice" onClose={() => setError(null)}>
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

      {loadingSelectedRun && (
        <div
          role="status"
          style={{
            padding: '0.85rem 1rem',
            backgroundColor: 'rgba(59, 130, 246, 0.08)',
            border: '1px solid rgba(59, 130, 246, 0.25)',
            borderRadius: 'var(--radius-sm)',
            marginBottom: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            fontSize: '0.8125rem',
          }}
        >
          <Activity size={18} color="var(--primary-400)" className="animate-spin" />
          <span>Loading verification run {runIdFromUrl}...</span>
        </div>
      )}

      {/* Progress Bar for File Uploads */}
      {submitting && uploadProgress > 0 && uploadProgress < 100 && (
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
            <span>Uploading project archive...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div style={{ height: '4px', background: 'var(--bg-tertiary)', borderRadius: '2px', overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${uploadProgress}%`,
                background: 'var(--primary-400)',
                transition: 'width 0.2s ease',
              }}
            />
          </div>
        </div>
      )}

      {/* Execution in progress banner */}
      {runningVerification && (
        <div
          style={{
            padding: '0.85rem 1rem',
            backgroundColor: 'rgba(59, 130, 246, 0.08)',
            border: '1px solid rgba(59, 130, 246, 0.25)',
            borderRadius: 'var(--radius-sm)',
            marginBottom: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            fontSize: '0.8125rem',
            color: 'var(--text-primary)',
          }}
        >
          <Activity size={18} color="var(--primary-400)" className="animate-spin" />
          <div style={{ flex: 1 }}>
            <strong>Verification in Progress:</strong> {verifyingStage || 'Executing Unit, Integration, and Performance tests in container sandbox...'}
          </div>
        </div>
      )}

      {/* MAIN UNIFIED CHATGPT-STYLE COMPOSER */}
      <div
        className={`unified-composer ${isDragOver ? 'drag-active' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {isDragOver && (
          <div className="composer-drag-overlay">
            <Upload size={30} color="var(--primary-400)" />
            <span>Drop source files or project ZIP archive here</span>
          </div>
        )}

        <div className="composer-input-area">
          <textarea
            id="code-textarea"
            ref={textareaRef}
            aria-label="Source Code"
            className="composer-textarea"
            placeholder="Paste your code or attach files to verify..."
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={handleKeyDownInEditor}
            spellCheck="false"
          />
        </div>

        {attachedFiles.length > 0 && (
          <div className="composer-attachments-bar">
            <div className="composer-attachments-label">
              <Paperclip size={13} />
              <span>Attached ({attachedFiles.length}):</span>
            </div>

            <div className="composer-chips-list">
              {attachedFiles.map((file, idx) => {
                const isZip = file.name.toLowerCase().endsWith('.zip');
                return (
                  <div key={idx} className={`attachment-chip ${isZip ? 'is-zip' : ''}`}>
                    {isZip ? (
                      <FolderArchive size={14} color="var(--primary-400)" />
                    ) : (
                      <FileCode size={14} color="var(--text-secondary)" />
                    )}
                    <span className="chip-name" title={file.name}>{file.name}</span>
                    <span className="chip-size">{formatBytes(file.size)}</span>
                    {isZip && <span className="chip-badge">Project ZIP</span>}
                    <button
                      type="button"
                      className="chip-remove-btn"
                      onClick={() => handleRemoveAttachment(idx)}
                      title={`Remove ${file.name}`}
                      aria-label={`Remove ${file.name}`}
                    >
                      <X size={12} />
                    </button>
                  </div>
                );
              })}
            </div>

            <button
              type="button"
              className="composer-clear-files-btn"
              onClick={handleClearAttachments}
            >
              Clear all
            </button>
          </div>
        )}

        {isMixedInput && (
          <div className="mixed-input-callout">
            <div className="mixed-callout-content">
              <Sparkles size={14} color="var(--primary-400)" />
              <span>
                <strong>Mixed Mode:</strong> Pasted code (<code>{filename || getLanguageFilename(language)}</code>) will be packaged as entrypoint with {attachedFiles.length} attached file(s) into a unified project archive.
              </span>
            </div>
            <div className="mixed-callout-actions">
              <button
                type="button"
                onClick={() => setCode('')}
                className="mixed-action-link"
              >
                Clear Pasted Code
              </button>
              <span className="mixed-sep">•</span>
              <button
                type="button"
                onClick={handleClearAttachments}
                className="mixed-action-link"
              >
                Clear Files
              </button>
            </div>
          </div>
        )}

        {/* Bottom Toolbar Controls */}
        <div className="composer-toolbar">
          <div className="composer-toolbar-left" ref={attachmentMenuRef}>
            <div className="attachment-dropdown-wrapper">
              <button
                type="button"
                className={`composer-plus-btn ${attachmentMenuOpen ? 'active' : ''}`}
                onClick={() => setAttachmentMenuOpen((prev) => !prev)}
                title="Add attachments or upload project ZIP"
                aria-label="Add attachments"
              >
                <Plus size={18} />
              </button>

              {attachmentMenuOpen && (
                <div className="attachment-menu-popup" role="menu">
                  <button
                    type="button"
                    className="attachment-menu-item"
                    onClick={() => {
                      sourceFileInputRef.current?.click();
                      setAttachmentMenuOpen(false);
                    }}
                  >
                    <FileCode size={16} className="menu-item-icon" />
                    <div>
                      <div className="menu-item-title">Add Source Files</div>
                      <div className="menu-item-subtitle">.py, .js, .ts, .java, .cpp, .c, etc.</div>
                    </div>
                  </button>
                  <button
                    type="button"
                    className="attachment-menu-item"
                    onClick={() => {
                      zipFileInputRef.current?.click();
                      setAttachmentMenuOpen(false);
                    }}
                  >
                    <FolderArchive size={16} className="menu-item-icon is-zip" />
                    <div>
                      <div className="menu-item-title">Upload Project ZIP</div>
                      <div className="menu-item-subtitle">Complete multi-file Python project</div>
                    </div>
                  </button>
                  <button
                    type="button"
                    className="attachment-menu-item"
                    onClick={() => {
                      const demoFile = createDemoScenarioFile();
                      validateFile(demoFile);
                      setAttachedFiles([demoFile]);
                      setLanguage('python');
                      setAttachmentMenuOpen(false);
                    }}
                  >
                    <Sparkles size={16} className="menu-item-icon" color="var(--primary-400)" />
                    <div>
                      <div className="menu-item-title">Load Demo Project</div>
                      <div className="menu-item-subtitle">friday_defective_three_tests.zip</div>
                    </div>
                  </button>
                </div>
              )}
            </div>

            <div className="language-select-wrapper">
              <select
                id="language-select"
                aria-label="Programming Language"
                className="composer-lang-select"
                value={language}
                onChange={handleLanguageChange}
              >
                {PROGRAMMING_LANGUAGES.map((lang) => (
                  <option key={lang.value} value={lang.value}>
                    {lang.label} ({lang.ext})
                  </option>
                ))}
              </select>
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              icon={Sparkles}
              onClick={loadSampleSnippet}
              title={`Load syntactically valid ${language} example`}
              className="composer-sample-btn"
            >
              Load Sample
            </Button>

            <Button
              type="button"
              id="load-demo-zip-btn"
              variant="outline"
              size="sm"
              icon={FolderArchive}
              onClick={() => {
                const demoFile = createDemoScenarioFile();
                validateFile(demoFile);
                setAttachedFiles([demoFile]);
                setLanguage('python');
              }}
              title="Load Friday demo multi-file project"
              className="composer-demo-zip-btn"
            >
              Load Demo Project
            </Button>
          </div>

          <div className="composer-toolbar-right">
            {code && (
              <span className="composer-metrics">
                {lineCount} {lineCount === 1 ? 'line' : 'lines'} • {charCount} chars
              </span>
            )}

            <Button
              type="button"
              variant="ghost"
              size="sm"
              icon={RotateCcw}
              onClick={handleReset}
              disabled={submitting || runningVerification || (!code && attachedFiles.length === 0 && requirementIds.length === 0)}
              className="composer-clear-btn"
            >
              Clear
            </Button>

            {/* Upload Only Button */}
            <Button
              type="button"
              variant="outline"
              size="sm"
              loading={submitting && !runningVerification}
              icon={Send}
              onClick={handleSubmit}
              disabled={submitting || runningVerification || (!code.trim() && attachedFiles.length === 0)}
              className="composer-submit-btn"
            >
              {isZipAttached || attachedFiles.length > 1 || isMixedInput
                ? 'Upload Project'
                : 'Upload Submission'}
            </Button>

            {/* Primary One-Click Action */}
            <Button
              type="button"
              variant="primary"
              size="sm"
              loading={runningVerification}
              icon={PlayCircle}
              onClick={handleUploadAndRunVerification}
              disabled={submitting || runningVerification || (!code.trim() && attachedFiles.length === 0 && !result?.id)}
              className="composer-run-btn"
              style={{
                backgroundColor: 'var(--status-passed)',
                borderColor: 'var(--status-passed-border)',
                fontWeight: 600,
              }}
            >
              Verify Code
            </Button>
          </div>
        </div>
      </div>

      {/* Tip Bar */}
      <div className="composer-hint-bar">
        <span>Tip: Press <strong>Ctrl+Enter</strong> to run verification directly • Drag and drop files onto composer</span>
        <span>Max file size: {MAX_UPLOAD_SIZE_LABEL}</span>
      </div>

      {/* Advanced Verification Options (Collapsible) */}
      <div className="advanced-options-card">
        <div
          className="advanced-options-header"
          onClick={() => setShowAdvanced((prev) => !prev)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setShowAdvanced((p) => !p)}
        >
          <div className="advanced-options-header-left">
            <Tag size={15} color="var(--primary-400)" />
            <span className="advanced-options-title">
              Advanced Verification Options
            </span>
            <span className="advanced-options-subtitle">
              (Requirement IDs, Trusted Tests, Filename Override)
            </span>
          </div>
          <div>
            {showAdvanced ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
          </div>
        </div>

        {showAdvanced && (
          <div className="advanced-options-body animate-fade-in">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label htmlFor="filename-input" className="form-label">
                  <span>Filename Override (Optional)</span>
                </label>
                <input
                  id="filename-input"
                  type="text"
                  className="form-input"
                  placeholder={`e.g. ${getLanguageFilename(language)}`}
                  value={filename}
                  onChange={(e) => setFilename(e.target.value)}
                  maxLength={255}
                />
              </div>

              <div className="form-group" style={{ marginBottom: 0 }}>
                <label htmlFor="requirements-input" className="form-label">
                  <span>Requirement Identifiers (Optional)</span>
                  <span className="form-hint">Press Enter or comma</span>
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
                        style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', display: 'flex', padding: 0 }}
                      >
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                  <input
                    id="requirements-input"
                    type="text"
                    placeholder={requirementIds.length === 0 ? "e.g. REQ-AUTH-01, REQ-PERF-01" : "Add more..."}
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
                      minWidth: '140px',
                    }}
                  />
                </div>
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="testcode-textarea" className="form-label">
                <span>Trusted Test Suite / Oracle (Optional)</span>
                <span className="form-hint">Authorized pytest test cases to verify this submission</span>
              </label>
              <textarea
                id="testcode-textarea"
                className="form-textarea code-textarea"
                rows={5}
                placeholder={`# Optional: Supply authorized test cases for verification\nfrom solution import calculate_metrics\n\ndef test_metrics():\n    assert calculate_metrics([10, 20, 30])["count"] == 3\n`}
                value={testCode}
                onChange={(e) => setTestCode(e.target.value)}
                spellCheck="false"
                style={{ minHeight: '100px' }}
              />
              <span className="form-hint" style={{ marginTop: '0.35rem', display: 'block' }}>
                Verification Standard: Only explicitly authorized test cases or specifications determine correctness.
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* INLINE VERIFICATION AND POST-DELIVERY CONSOLE (ISSUES 1, 2, 4, 5, 6, 8, 9) */}
      {/* ========================================================================= */}
      {verificationRun && (
        <div style={{ marginTop: '1.5rem' }} className="animate-fade-in">
          <Card
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
                <Activity size={18} color="var(--primary-400)" />
                <span>Verification & Delivery Results</span>
                <Badge
                  variant={
                    verificationRun.status === 'PASSED'
                      ? 'success'
                      : verificationRun.status === 'FAILED'
                      ? 'danger'
                      : verificationRun.status === 'BLOCKED'
                      ? 'warning'
                      : verificationRun.status === 'RUNNING'
                      ? 'info'
                      : 'secondary'
                  }
                  dot
                >
                  {verificationRun.status}
                </Badge>
              </div>
            }
            subtitle={
              <span>
                Run ID: <code style={{ color: 'var(--primary-300)' }}>{verificationRun.id}</code> • Submission: <code style={{ color: 'var(--text-secondary)' }}>{verificationRun.submission_id}</code>
                {verificationRun.execution_telemetry?.duration_ms && (
                  <span> • Duration: {verificationRun.execution_telemetry.duration_ms.toFixed(1)}ms</span>
                )}
              </span>
            }
            action={
              <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                <Button
                  variant="outline"
                  size="sm"
                  icon={runIdCopied ? Check : Copy}
                  onClick={() => handleCopyId(verificationRun.id, true)}
                >
                  {runIdCopied ? 'Copied' : 'Copy Run ID'}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  icon={RefreshCw}
                  loading={refreshingRun}
                  onClick={handleRefreshRun}
                  title="Poll latest run status"
                />
                <Button
                  variant="outline"
                  size="sm"
                  icon={ExternalLink}
                  onClick={() => navigate(`/verifications?run_id=${encodeURIComponent(verificationRun.id)}`)}
                >
                  Advanced Details
                </Button>
              </div>
            }
          >
            {/* OVERALL VERDICT BANNER */}
            <div style={{ marginBottom: '1.25rem' }}>
              {verificationRun.status === 'PASSED' && (
                <Alert type="success" title="Overall Verification Verdict: PASSED">
                  All requested test suites executed inside isolated Docker sandbox and satisfied authorized verification requirements with zero failed assertions.
                </Alert>
              )}

              {verificationRun.status === 'FAILED' && (
                <Alert type="danger" title="Overall Verification Verdict: FAILED">
                  Functional defect or assertion failure detected during sandbox execution. Delivery workflow has been stopped.
                  {verificationRun.error_message && (
                    <div style={{ marginTop: '0.35rem', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                      {verificationRun.error_message}
                    </div>
                  )}
                </Alert>
              )}

              {verificationRun.status === 'BLOCKED' && (
                <Alert type="warning" title="Overall Verification Verdict: BLOCKED">
                  {verificationRun.error_message || 'Verification could not proceed. Required tests were not executed or language is unsupported.'}
                </Alert>
              )}

              {verificationRun.status === 'ERROR' && (
                <Alert type="danger" title="Overall Verification Verdict: INFRASTRUCTURE ERROR">
                  {verificationRun.error_message || 'Container sandbox or execution runner encountered an unexpected infrastructure failure.'}
                </Alert>
              )}
            </div>

            {/* THREE GENUINE TESTING CATEGORIES (ISSUE 9) */}
            <div style={{ marginBottom: '1.25rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem', letterSpacing: '0.05em' }}>
                Verification Categories (Unit • Integration • Performance)
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                  gap: '0.75rem',
                }}
              >
                {/* 1. UNIT TESTING CARD */}
                <div
                  style={{
                    padding: '0.85rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-secondary)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Layers size={16} color="var(--primary-400)" />
                      <strong style={{ fontSize: '0.85rem' }}>Unit Testing</strong>
                    </div>
                    <Badge
                      variant={
                        unitStatus === 'PASSED'
                          ? 'success'
                          : unitStatus === 'FAILED'
                          ? 'danger'
                          : unitStatus === 'BLOCKED'
                          ? 'warning'
                          : 'secondary'
                      }
                      dot
                    >
                      {unitStatus}
                    </Badge>
                  </div>

                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                    {unitStatus === 'NOT_EXECUTED' || unitStatus === 'BLOCKED' ? (
                      <span>No authorized unit test suite executed.</span>
                    ) : (
                      <span>
                        <strong>{unitPassedCount} passed</strong>, {unitFailedCount} failed (total {unitPassedCount + unitFailedCount})
                      </span>
                    )}
                  </div>

                  {unitTests.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', marginTop: '0.35rem' }}>
                      {unitTests.map((t, i) => (
                        <div
                          key={i}
                          style={{
                            fontSize: '0.73rem',
                            fontFamily: 'var(--font-mono)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '0.25rem 0.4rem',
                            borderRadius: '3px',
                            background: t.status === 'PASSED' ? 'rgba(16, 185, 129, 0.06)' : 'rgba(239, 68, 68, 0.08)',
                            border: t.status === 'PASSED' ? '1px solid rgba(16, 185, 129, 0.2)' : '1px solid rgba(239, 68, 68, 0.25)',
                          }}
                        >
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.name}>
                            {t.name}
                          </span>
                          <span style={{ fontWeight: 600, color: t.status === 'PASSED' ? 'var(--status-passed)' : 'var(--status-failed)' }}>
                            {t.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 2. INTEGRATION TESTING CARD */}
                <div
                  style={{
                    padding: '0.85rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-secondary)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Terminal size={16} color="var(--primary-400)" />
                      <strong style={{ fontSize: '0.85rem' }}>Integration Testing</strong>
                    </div>
                    <Badge
                      variant={
                        integStatus === 'PASSED'
                          ? 'success'
                          : integStatus === 'FAILED'
                          ? 'danger'
                          : integStatus === 'BLOCKED'
                          ? 'warning'
                          : 'secondary'
                      }
                      dot
                    >
                      {integStatus}
                    </Badge>
                  </div>

                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                    {integStatus === 'NOT_EXECUTED' || integStatus === 'BLOCKED' ? (
                      <span style={{ color: 'var(--text-muted)' }}>
                        NOT EXECUTED — No multi-module integration test oracle supplied. (Syntax validation alone is not integration testing).
                      </span>
                    ) : (
                      <span>
                        <strong>{integPassedCount} interaction(s) passed</strong>, {integFailedCount} failed
                      </span>
                    )}
                  </div>

                  {integTests.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', marginTop: '0.35rem' }}>
                      {integTests.map((t, i) => (
                        <div
                          key={i}
                          style={{
                            fontSize: '0.73rem',
                            fontFamily: 'var(--font-mono)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '0.25rem 0.4rem',
                            borderRadius: '3px',
                            background: t.status === 'PASSED' ? 'rgba(16, 185, 129, 0.06)' : 'rgba(239, 68, 68, 0.08)',
                            border: t.status === 'PASSED' ? '1px solid rgba(16, 185, 129, 0.2)' : '1px solid rgba(239, 68, 68, 0.25)',
                          }}
                        >
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.name}>
                            {t.name}
                          </span>
                          <span style={{ fontWeight: 600, color: t.status === 'PASSED' ? 'var(--status-passed)' : 'var(--status-failed)' }}>
                            {t.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 3. PERFORMANCE TESTING CARD */}
                <div
                  style={{
                    padding: '0.85rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-secondary)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Clock size={16} color="var(--primary-400)" />
                      <strong style={{ fontSize: '0.85rem' }}>Performance Testing</strong>
                    </div>
                    <Badge
                      variant={
                        perfStatus === 'PASSED'
                          ? 'success'
                          : perfStatus === 'FAILED'
                          ? 'danger'
                          : perfStatus === 'BLOCKED'
                          ? 'warning'
                          : 'secondary'
                      }
                      dot
                    >
                      {perfStatus}
                    </Badge>
                  </div>

                  {perfMetrics ? (
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      <div>Measured Latency (p95): <strong>{performanceExecuted ? `${Number(perfMetrics.latency_p95_ms).toFixed(2)}ms` : 'N/A'}</strong></div>
                      <div>Configured Threshold SLA: <strong>&lt;= {Number(perfMetrics.threshold_latency_ms || 0).toFixed(2)}ms</strong></div>
                      <div style={{ marginTop: '0.2rem' }}>
                        Decision:{' '}
                        <Badge variant={!performanceExecuted ? 'warning' : perfMetrics.is_breached ? 'danger' : 'success'}>
                          {!performanceExecuted ? 'NOT_EVALUATED' : perfMetrics.is_breached ? 'THRESHOLD BREACHED' : 'WITHIN THRESHOLD (PASS)'}
                        </Badge>
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      {perfStatus === 'NOT_EXECUTED' || perfStatus === 'BLOCKED'
                        ? 'No performance benchmark oracle configured.'
                        : 'Completed without latency SLA breach.'}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* TECHNICAL FAILURE EVIDENCE (FOR FAILED RUNS ONLY) */}
            {verificationRun.status === 'FAILED' && (
              <div style={{ marginBottom: '1.25rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem', letterSpacing: '0.05em' }}>
                  Technical Failure Evidence &amp; Defect Classification
                </div>

                {verificationRun.defect_reports && verificationRun.defect_reports.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {verificationRun.defect_reports.map((defect, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: '0.75rem',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid rgba(239, 68, 68, 0.3)',
                          backgroundColor: 'rgba(239, 68, 68, 0.05)',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                          <span style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--text-primary)' }}>
                            <Bug size={14} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle', color: '#ef4444' }} />
                            {defect.title}
                          </span>
                          <Badge variant="danger">{defect.severity || 'HIGH'}</Badge>
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                          Location: <code>{defect.file_path}:{defect.line_number || '?'}</code> • Confidence: {defect.confidence}
                        </div>
                        {defect.description && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', background: 'var(--bg-input)', padding: '0.4rem', borderRadius: '3px' }}>
                            {defect.description}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ padding: '0.75rem', borderRadius: 'var(--radius-sm)', background: 'var(--bg-secondary)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    Failed assertion occurred during test execution. Inspect test logs or run in advanced console for machine repair payload.
                  </div>
                )}
              </div>
            )}

            {/* STRICT POST-DELIVERY XAI SEPARATION */}
            {verificationRun.status === 'PASSED' && (
              /* PASSED STATE: EVALUATE GOVERNANCE AND DELIVERY CONFIRMATION */
              <div style={{ marginTop: '0.5rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem', letterSpacing: '0.05em' }}>
                  Deployment Governance &amp; Post-Delivery XAI Gate
                </div>

                <div
                  style={{
                    padding: '1rem',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-color)',
                    background: 'var(--bg-card)',
                    marginBottom: '1rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <ShieldCheck size={18} color="var(--status-passed)" />
                      <strong style={{ fontSize: '0.85rem' }}>Deployment Readiness Governance:</strong>
                      <Badge variant="success">APPROVED</Badge>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Downstream Delivery Gate:</span>
                      <Badge variant={isDeliveryConfirmed ? 'success' : 'warning'}>
                        {isDeliveryConfirmed ? 'AUTHORIZED' : 'PENDING AUTHORIZATION'}
                      </Badge>
                    </div>
                  </div>

                  {!isDeliveryConfirmed ? (
                    <div
                      style={{
                        padding: '0.75rem',
                        backgroundColor: 'rgba(245, 158, 11, 0.08)',
                        border: '1px solid rgba(245, 158, 11, 0.25)',
                        borderRadius: 'var(--radius-xs)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: '0.75rem',
                      }}
                    >
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', flex: 1, minWidth: '220px' }}>
                        Software verification and governance checks have passed. Authorized delivery confirmation is required
                        to unlock the post-delivery Explainable AI software-understanding package.
                      </div>
                      <Button
                        variant="primary"
                        size="sm"
                        icon={CheckCircle2}
                        onClick={handleAuthorizeSimulatedDelivery}
                        loading={authorizingDelivery}
                      >
                        Authorize Dev Delivery Simulation
                      </Button>
                    </div>
                  ) : (
                    <div
                      style={{
                        padding: '0.75rem',
                        backgroundColor: 'rgba(16, 185, 129, 0.08)',
                        border: '1px solid rgba(16, 185, 129, 0.25)',
                        borderRadius: 'var(--radius-xs)',
                        fontSize: '0.78rem',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                        <Unlock size={14} color="var(--status-passed)" />
                        <strong style={{ color: 'var(--status-passed)' }}>Downstream Delivery Confirmed</strong>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.73rem' }}>
                          ({verificationRun.delivery_confirmation?.delivery_id})
                        </span>
                      </div>
                      <div>
                        Artifact confirmed delivered at {formatDate(verificationRun.delivery_confirmation?.delivered_at)}.
                        Human-facing post-delivery software explanation unlocked below.
                      </div>
                    </div>
                  )}
                </div>

                {/* UNLOCKED POST-DELIVERY XAI CONSOLE (ISSUES 6 & 7) */}
                {isDeliveryConfirmed && (
                  <Card
                    title={
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Sparkles size={18} color="var(--primary-400)" />
                        <span>Post-Delivery Software Understanding Package</span>
                      </div>
                    }
                    subtitle="Human-facing explanation of successfully delivered software across 8 core dimensions"
                    action={
                      <div style={{ display: 'flex', gap: '0.35rem' }}>
                        <Button
                          variant={explanationLevel === 'beginner' ? 'primary' : 'outline'}
                          size="sm"
                          icon={User}
                          onClick={() => setExplanationLevel('beginner')}
                        >
                          Beginner View
                        </Button>
                        <Button
                          variant={explanationLevel === 'technical' ? 'primary' : 'outline'}
                          size="sm"
                          icon={Terminal}
                          onClick={() => setExplanationLevel('technical')}
                        >
                          Technical View
                        </Button>
                      </div>
                    }
                  >
                    {/* Ollama Inference Provenance Attestation */}
                    {xaiExplanation?.inference_provenance && (
                      <div
                        style={{
                          padding: '0.6rem 0.85rem',
                          backgroundColor: xaiExplanation.inference_provenance.genuine_inference
                            ? 'rgba(99, 102, 241, 0.08)'
                            : 'rgba(245, 158, 11, 0.08)',
                          border: xaiExplanation.inference_provenance.genuine_inference
                            ? '1px solid rgba(99, 102, 241, 0.25)'
                            : '1px solid rgba(245, 158, 11, 0.25)',
                          borderRadius: 'var(--radius-xs)',
                          marginBottom: '1rem',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          flexWrap: 'wrap',
                          gap: '0.5rem',
                          fontSize: '0.78rem',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <Cpu size={16} color={xaiExplanation.inference_provenance.genuine_inference ? '#818cf8' : '#f59e0b'} />
                          <span>
                            <strong>AI Inference Engine:</strong>{' '}
                            {xaiExplanation.inference_provenance.genuine_inference ? (
                              <span>
                                Synthesized by local LLM <code style={{ color: '#818cf8', fontWeight: 600 }}>{xaiExplanation.inference_provenance.model || 'qwen2.5-coder:3b'}</code> via Ollama (grounded in verified test evidence)
                              </span>
                            ) : (
                              <span>
                                Grounded Deterministic AST Baseline ({xaiExplanation.inference_provenance.fallback_reason || 'Rule-based code engine'})
                              </span>
                            )}
                          </span>
                        </div>
                        <Badge variant={xaiExplanation.inference_provenance.genuine_inference ? 'primary' : 'warning'}>
                          {xaiExplanation.inference_provenance.genuine_inference ? 'GENUINE LOCAL LLM' : 'DETERMINISTIC BASELINE'}
                        </Badge>
                      </div>
                    )}

                    {loadingXai ? (
                      <GenerationIndicator />
                    ) : xaiExplanation?.post_delivery_explanation ? (
                      (() => {
                        const pdx = xaiExplanation.post_delivery_explanation;
                        const beginner = pdx.beginner_level;

                        if (explanationLevel === 'beginner' && beginner) {
                          return (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.84rem' }}>
                              <div style={{ padding: '0.85rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                <h4 style={{ fontSize: '0.9rem', marginBottom: '0.35rem', color: 'var(--text-primary)' }}>Overview</h4>
                                <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{beginner.overview}</p>
                              </div>

                              <div style={{ padding: '0.85rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                <h4 style={{ fontSize: '0.9rem', marginBottom: '0.35rem', color: 'var(--text-primary)' }}>What It Does</h4>
                                <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{beginner.what_it_does}</p>
                              </div>

                              <div style={{ padding: '0.85rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                <h4 style={{ fontSize: '0.9rem', marginBottom: '0.35rem', color: 'var(--text-primary)' }}>How to Use</h4>
                                <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{beginner.how_to_use}</p>
                              </div>

                              {beginner.realistic_example && (
                                <div style={{ padding: '0.85rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.9rem', marginBottom: '0.35rem', color: 'var(--text-primary)' }}>Example from the Delivered Code</h4>
                                  <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.6, overflowWrap: 'anywhere' }}>{beginner.realistic_example}</p>
                                </div>
                              )}

                              {beginner.test_confidence && (
                                <div style={{ padding: '0.85rem', background: 'rgba(16, 185, 129, 0.06)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.9rem', marginBottom: '0.35rem', color: 'var(--status-passed)' }}>What the Tests Tell Us</h4>
                                  <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{beginner.test_confidence}</p>
                                </div>
                              )}

                              {beginner.key_capabilities && beginner.key_capabilities.length > 0 && (
                                <div style={{ padding: '0.85rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.9rem', marginBottom: '0.35rem', color: 'var(--text-primary)' }}>Key Capabilities</h4>
                                  <ul style={{ margin: 0, paddingLeft: '1.25rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                    {beginner.key_capabilities.map((cap, i) => (
                                      <li key={i}>{cap}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {beginner.safety_and_boundaries && (
                                <div style={{ padding: '0.85rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.9rem', marginBottom: '0.35rem', color: 'var(--text-primary)' }}>Safety &amp; Operational Boundaries</h4>
                                  <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{beginner.safety_and_boundaries}</p>
                                </div>
                              )}
                            </div>
                          );
                        }

                        // Technical Level View across 8 Core Dimensions
                        return (
                          <div>
                            {/* 8 Dimension Navigation Chips */}
                            <div
                              style={{
                                display: 'flex',
                                gap: '0.35rem',
                                flexWrap: 'wrap',
                                marginBottom: '1rem',
                                paddingBottom: '0.75rem',
                                borderBottom: '1px solid var(--border-color)',
                              }}
                            >
                              {[
                                { id: 'overview', label: '1. Purpose & Overview' },
                                { id: 'architecture', label: '2. Architecture & Modules' },
                                { id: 'functions', label: '3. Important Functions' },
                                { id: 'dataflow', label: '4. API & Data Flow' },
                                { id: 'evidence', label: '5. Test Evidence' },
                                { id: 'performance', label: '6. Measured SLA' },
                                { id: 'decisions', label: '7. Design Decisions' },
                                { id: 'limitations', label: '8. Scope & Limits' },
                              ].map((tab) => (
                                <button
                                  key={tab.id}
                                  type="button"
                                  onClick={() => setActiveXaiDimension(tab.id)}
                                  style={{
                                    padding: '0.35rem 0.65rem',
                                    borderRadius: 'var(--radius-sm)',
                                    fontSize: '0.75rem',
                                    fontWeight: activeXaiDimension === tab.id ? 600 : 400,
                                    border: '1px solid',
                                    borderColor: activeXaiDimension === tab.id ? 'var(--primary-400)' : 'var(--border-color)',
                                    background: activeXaiDimension === tab.id ? 'var(--primary-subtle)' : 'var(--bg-secondary)',
                                    color: activeXaiDimension === tab.id ? 'var(--primary-300)' : 'var(--text-secondary)',
                                    cursor: 'pointer',
                                  }}
                                >
                                  {tab.label}
                                </button>
                              ))}
                            </div>

                            {/* Dimension Content Panes */}
                            <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                              {activeXaiDimension === 'overview' && (
                                <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.35rem' }}>Software Purpose &amp; Overview</h4>
                                  <p style={{ margin: 0, whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>{pdx.software_overview}</p>
                                </div>
                              )}

                              {activeXaiDimension === 'architecture' && (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                                  <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                    <h4 style={{ fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.35rem' }}>Component Architecture</h4>
                                    <p style={{ margin: 0, whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>{pdx.architecture_explanation}</p>
                                  </div>

                                  {pdx.module_responsibilities && pdx.module_responsibilities.length > 0 && (
                                    <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                      <h4 style={{ fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Module Responsibilities</h4>
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                                        {pdx.module_responsibilities.map((mod, i) => (
                                          <div key={i} style={{ padding: '0.4rem 0.6rem', background: 'var(--bg-card)', borderRadius: '3px', border: '1px solid var(--border-color)' }}>
                                            <div><strong style={{ color: 'var(--primary-300)' }}>{mod.file_path || mod.module_name}</strong> <span style={{ color: 'var(--text-muted)' }}>({mod.line_count || 0} LOC)</span></div>
                                            <div style={{ marginTop: '0.25rem', overflowWrap: 'anywhere' }}>{mod.primary_responsibility}</div>
                                            {mod.exported_symbols?.length > 0 && <div style={{ marginTop: '0.25rem', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--text-muted)', overflowWrap: 'anywhere' }}>Symbols: {mod.exported_symbols.join(', ')}</div>}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}

                              {activeXaiDimension === 'functions' && (
                                <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Important Functions &amp; Business Logic</h4>
                                  {pdx.important_functions && pdx.important_functions.length > 0 ? (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                      {pdx.important_functions.map((fn, i) => (
                                        <div key={i} style={{ padding: '0.5rem 0.75rem', background: 'var(--bg-card)', borderRadius: '3px', border: '1px solid var(--border-color)' }}>
                                          <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', overflowWrap: 'anywhere' }}>
                                            {fn.signature || fn.function_name}
                                          </div>
                                          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>{fn.file_path}: line {fn.line_number}</div>
                                          <div style={{ fontSize: '0.78rem', marginTop: '0.35rem', whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>{fn.technical_behavior || fn.summary_beginner}</div>
                                          {fn.verified_by_tests?.length > 0 && <div style={{ fontSize: '0.72rem', color: 'var(--status-passed)', marginTop: '0.3rem', overflowWrap: 'anywhere' }}>Related passing tests: {fn.verified_by_tests.join(', ')}</div>}
                                        </div>
                                      ))}
                                    </div>
                                  ) : (
                                    <p style={{ margin: 0 }}>Core functions verified through automated execution.</p>
                                  )}
                                </div>
                              )}

                              {activeXaiDimension === 'dataflow' && (
                                <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.35rem' }}>API Contracts &amp; Data Flow</h4>
                                  <p style={{ margin: 0, whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>{pdx.api_and_data_flow}</p>
                                </div>
                              )}

                              {activeXaiDimension === 'evidence' && (
                                <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Verified Behavior &amp; Test Evidence</h4>
                                  <p style={{ margin: '0 0 0.5rem' }}>These results establish only the scenarios exercised by each recorded test; they do not prove complete correctness.</p>
                                  {pdx.test_evidence?.length > 0 && (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                                      {pdx.test_evidence.map((item, i) => (
                                        <div key={item.test_id || i} style={{ fontSize: '0.75rem', padding: '0.5rem', background: 'var(--bg-card)', borderRadius: '3px', border: '1px solid var(--border-color)' }}>
                                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}><code>{item.test_name}</code><Badge variant="success">{item.test_type} · {item.status}</Badge></div>
                                          <div style={{ marginTop: '0.25rem', color: 'var(--text-muted)' }}>{item.demonstrated_scope}</div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}

                              {activeXaiDimension === 'performance' && (
                                <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.35rem' }}>Measured Performance &amp; SLA Evidence</h4>
                                  {pdx.measured_sla?.available ? (
                                    <div>
                                      <p style={{ margin: '0 0 0.5rem' }}>
                                        Measured p95 runtime is <strong>{Number(pdx.measured_sla.latency_p95_ms).toFixed(2)}ms</strong> against an SLA threshold of <strong>{Number(pdx.measured_sla.threshold_latency_ms).toFixed(2)}ms</strong>.
                                      </p>
                                      <Badge variant={pdx.measured_sla.verdict === 'PASSED' ? 'success' : 'danger'}>{pdx.measured_sla.verdict}</Badge>
                                      <p style={{ margin: '0.5rem 0 0', color: 'var(--text-muted)' }}>{pdx.measured_sla.environment_note}</p>
                                    </div>
                                  ) : (
                                    <p style={{ margin: 0 }}>{pdx.measured_sla?.environment_note || 'No empirical SLA measurement is available.'}</p>
                                  )}
                                </div>
                              )}

                              {activeXaiDimension === 'decisions' && (
                                <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Algorithms &amp; Design Decisions</h4>
                                  {pdx.algorithms_and_design_decisions && pdx.algorithms_and_design_decisions.length > 0 ? (
                                    <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
                                      {pdx.algorithms_and_design_decisions.map((dec, i) => (
                                        <li key={i}>
                                          <strong>{dec.topic || 'Architecture'}:</strong> {dec.decision} — {dec.rationale}
                                        </li>
                                      ))}
                                    </ul>
                                  ) : (
                                    <p style={{ margin: 0 }}>Standard modular Python architecture with decoupled pricing and checkout operations.</p>
                                  )}
                                </div>
                              )}

                              {activeXaiDimension === 'limitations' && (
                                <div style={{ padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)' }}>
                                  <h4 style={{ fontSize: '0.875rem', color: 'var(--text-primary)', marginBottom: '0.35rem' }}>Assumptions &amp; Verification Scope Limits</h4>
                                  <p style={{ margin: 0, whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>{pdx.limitations_and_verification_scope}</p>
                                  {pdx.evidence_manifest && <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-color)', color: 'var(--text-muted)', overflowWrap: 'anywhere' }}>Analyzed files: {pdx.evidence_manifest.analyzed_source_files?.join(', ') || 'none'}. Omitted by bound: {pdx.evidence_manifest.omitted_source_files?.join(', ') || 'none'}.</div>}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })()
                    ) : (
                      <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
                        Post-delivery software understanding package not generated yet.
                      </div>
                    )}
                  </Card>
                )}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
