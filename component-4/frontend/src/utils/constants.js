/**
 * Application-wide constants matching backend schemas and configurations.
 */

export const PROGRAMMING_LANGUAGES = [
  { value: 'python', label: 'Python', ext: '.py' },
  { value: 'javascript', label: 'JavaScript', ext: '.js' },
  { value: 'typescript', label: 'TypeScript', ext: '.ts' },
  { value: 'java', label: 'Java', ext: '.java' },
  { value: 'cpp', label: 'C++', ext: '.cpp' },
  { value: 'c', label: 'C', ext: '.c' },
  { value: 'csharp', label: 'C#', ext: '.cs' },
  { value: 'go', label: 'Go', ext: '.go' },
  { value: 'rust', label: 'Rust', ext: '.rs' },
  { value: 'other', label: 'Other', ext: '.txt' },
];

export const ALLOWED_EXTENSIONS = [
  '.py', '.js', '.ts', '.jsx', '.tsx', '.java',
  '.cpp', '.c', '.h', '.hpp', '.cs', '.go',
  '.rs', '.html', '.css', '.json', '.txt', '.md',
];

export const MAX_UPLOAD_SIZE_BYTES = 2 * 1024 * 1024; // 2MB
export const MAX_UPLOAD_SIZE_LABEL = '2 MB';

export const VERIFICATION_STATUSES = {
  PENDING: { label: 'Pending', variant: 'warning', description: 'Queued for Phase 2 execution' },
  RUNNING: { label: 'Running', variant: 'info', description: 'Currently executing tests' },
  PASSED: { label: 'Passed', variant: 'success', description: 'All test suites passed' },
  FAILED: { label: 'Failed', variant: 'danger', description: 'Defects detected during testing' },
  ERROR: { label: 'Error', variant: 'danger', description: 'Execution failed due to system error' },
};

export const TEST_TYPES = [
  { id: 'unit', label: 'Unit Testing', description: 'Verifies individual functions and modules in isolation' },
  { id: 'integration', label: 'Integration Testing', description: 'Validates interactions between components and services' },
  { id: 'performance', label: 'Performance Testing', description: 'Measures latency, throughput, and resource limits' },
];

export const SUBMISSION_SOURCES = {
  manual_entry: { label: 'Manual Entry', variant: 'primary' },
  file_upload: { label: 'File Upload', variant: 'secondary' },
  component_3_api: { label: 'Component 3 API', variant: 'accent' },
};
