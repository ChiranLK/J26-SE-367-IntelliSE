from enum import Enum


class ProgrammingLanguage(str, Enum):
    """Supported programming languages for code submission and verification."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CPP = "cpp"
    C = "c"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    OTHER = "other"


class VerificationStatus(str, Enum):
    """Lifecycle statuses for a verification run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class TestType(str, Enum):
    """Types of verification tests executed in later phases."""

    __test__ = False

    UNIT = "unit"
    INTEGRATION = "integration"
    PERFORMANCE = "performance"


class TestResultStatus(str, Enum):
    """Execution status for individual test cases."""

    __test__ = False

    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    TIMEOUT = "TIMEOUT"


class DefectSeverity(str, Enum):
    """Severity classification for detected defects."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SubmissionSource(str, Enum):
    """Origin of a submitted codebase."""

    MANUAL_ENTRY = "manual_entry"
    FILE_UPLOAD = "file_upload"
    COMPONENT_3_API = "component_3_api"


class DefectCategory(str, Enum):
    """Proposal-aligned defect category taxonomy (Table 4 & SO2)."""

    FUNCTIONAL_BUG = "functional_bug"
    SECURITY_VULNERABILITY = "security_vulnerability"
    PERFORMANCE_BOTTLENECK = "performance_bottleneck"
    REGRESSION = "regression"
    UNKNOWN = "unknown"


class ConvergenceRiskLevel(str, Enum):
    """Architectural risk levels for module convergence (SO5)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DeploymentReadinessStatus(str, Enum):
    """Deployment readiness gate outcome (FR11, NFR01)."""

    READY = "READY"
    BLOCKED = "BLOCKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"

