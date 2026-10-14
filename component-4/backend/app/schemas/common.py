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
