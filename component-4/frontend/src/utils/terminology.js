/**
 * INTELISE Frontend — Centralized Product Terminology
 * Standardized user-facing labels, titles, descriptions, and statuses.
 * Avoid hardcoded duplicates across components and prevent terminology regressions.
 */

export const TERMINOLOGY = {
  // Brand & Application
  APP_NAME: 'INTELISE',
  APP_FULL_NAME: 'INTELISE — Code Verification & Repair Feedback Platform',
  APP_TAGLINE: 'Intelligent Testing & Feedback Engine',
  APP_DESCRIPTION: 'Automated code verification, defect analysis, and repair feedback platform',

  // Core Capabilities & Navigation
  CODE_VERIFICATION: 'Code Verification',
  VERIFICATION_RUNS: 'Verification Runs',
  DEFECT_ANALYSIS: 'Defect Analysis',
  TEST_EXPLANATIONS: 'Test Explanations',
  TECHNICAL_FEEDBACK: 'Technical Feedback',
  REPAIR_FEEDBACK: 'Repair Feedback',
  REPAIR_INTEGRATION: 'Repair Integration',
  FEEDBACK_HISTORY: 'Feedback History',
  SUBMISSIONS: 'Submissions',
  MANUAL_ENTRY: 'Manual Entry',
  FILE_UPLOAD: 'File Upload',

  // Actions & Buttons
  ACTIONS: {
    APPROVE_FOR_REPAIR: 'Approve for Repair',
    SEND_FOR_REPAIR: 'Send for Repair',
    SEND_FOR_REPAIR_UNAVAILABLE: 'Send for Repair (Unavailable)',
    TEST_FAIL_CLOSED: 'Test Fail-Closed',
    VERIFY_CODE: 'Verify Code',
    NEW_SUBMISSION: 'New Submission',
    REFRESH: 'Refresh',
    INSPECT_RUN: 'Inspect Run',
    VIEW_DETAILS: 'View Details',
    COPY_ID: 'Copy ID',
  },

  // Operational & Integration Status Messages
  STATUS: {
    PENDING_VERIFICATION: 'Pending Verification',
    AWAITING_EXECUTION: 'Awaiting test execution',
    VERIFIED_PASSING: 'Verified Passing',
    DEFECTS_DETECTED: 'Defects Detected',
    REPAIR_DELIVERY_UNAVAILABLE: 'Automatic repair delivery is currently unavailable',
    REPAIR_DELIVERY_SAFE_DISABLED: 'Outbound delivery is safely disabled until a verified repair service is connected.',
    REPAIR_INTEGRATION_STATUS: 'Repair Integration Status',
    REPAIR_DELIVERY_STATUS: 'Repair Service Delivery',
    DELIVERY_UNAVAILABLE: 'Delivery Unavailable',
    REPAIR_JOB: 'Repair Job',
    CORRELATION_ID: 'Correlation ID',
    ATTEMPT_ID: 'Attempt ID',
    FAILED_ASSERTIONS: 'Failed Assertions',
    AFFECTED_FILES: 'Affected Files',
    APPROVAL_STATUS: 'Approval Status',
    DELIVERY_STATUS: 'Delivery Status',
  },

  // Workflow Steps
  WORKFLOW: {
    TITLE: 'Repair Feedback Workflow',
    SUBTITLE: 'Structured feedback and re-verification cycle with automated repair services',
    STEP_1_TITLE: 'Step 1 — Defect Communication & Authorization',
    STEP_1_DESC: 'When verification fails, structured defect reports and a technical feedback payload are generated. A human reviewer explicitly authorizes dispatch.',
    STEP_2_TITLE: 'Step 2 — Automated Code Repair',
    STEP_2_DESC: 'The repair service accepts the technical feedback package, creates an internal repair job, and generates a refined code implementation addressing failed assertions.',
    STEP_3_TITLE: 'Step 3 — Ingestion & Re-Verification',
    STEP_3_DESC: 'The corrected implementation is submitted for verification, triggering a fresh verification run to confirm all test suites pass.',
  },

  // Explanations & Guidelines
  STANDARDS: {
    TEST_SPEC_RULE: 'Verification Standard: Only explicitly authorized test specifications determine correctness.',
    CODE_SAFE_NOTICE: 'Code is securely stored for verification; never executed in browser.',
    EXPLANATION_TARGET: 'Target: Reviewer / Software Engineer',
    EXPLANATION_SUBTITLE: 'Recommended next step based on verification analysis',
  },
};

export default TERMINOLOGY;
