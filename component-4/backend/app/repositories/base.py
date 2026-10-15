from abc import ABC, abstractmethod
from typing import Any, List, Optional
from app.schemas.common import VerificationStatus
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.verification import VerificationRunResponse


class BaseSubmissionRepository(ABC):
    """Abstract interface for code submission persistence."""

    @abstractmethod
    async def save(self, submission: CodeSubmissionResponse) -> CodeSubmissionResponse:
        """Persists a new or updated code submission."""
        pass

    @abstractmethod
    async def get_by_id(self, submission_id: str) -> Optional[CodeSubmissionResponse]:
        """Retrieves a submission by its unique identifier."""
        pass

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 100) -> List[CodeSubmissionResponse]:
        """Lists submissions with pagination support."""
        pass

    @abstractmethod
    async def count(self) -> int:
        """Returns the total number of stored submissions."""
        pass


class BaseVerificationRunRepository(ABC):
    """Abstract interface for verification run persistence."""

    @abstractmethod
    async def save(self, run: VerificationRunResponse) -> VerificationRunResponse:
        """Persists a new or updated verification run."""
        pass

    @abstractmethod
    async def get_by_id(self, run_id: str) -> Optional[VerificationRunResponse]:
        """Retrieves a verification run by its unique identifier."""
        pass

    @abstractmethod
    async def get_by_submission_id(self, submission_id: str) -> List[VerificationRunResponse]:
        """Retrieves all verification runs associated with a given submission."""
        pass

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 100) -> List[VerificationRunResponse]:
        """Lists verification runs with pagination support."""
        pass

    @abstractmethod
    async def update_status(
        self,
        run_id: str,
        status: VerificationStatus,
        error_message: Optional[str] = None,
    ) -> Optional[VerificationRunResponse]:
        """Updates the status and optional error message of a verification run."""
        pass

    @abstractmethod
    async def count(self) -> int:
        """Returns the total number of stored verification runs."""
        pass


class BaseRepairRepository(ABC):
    """Abstract interface for repair attempt and re-verification persistence."""

    @abstractmethod
    async def save(self, repair: Any) -> Any:
        """Persists a new or updated repair attempt."""
        pass

    @abstractmethod
    async def get_by_id(self, repair_id: str) -> Optional[Any]:
        """Retrieves a repair attempt by unique repair ID."""
        pass

    @abstractmethod
    async def get_by_original_run_id(self, run_id: str) -> List[Any]:
        """Retrieves all repair attempts associated with an original verification run."""
        pass

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 100) -> List[Any]:
        """Lists repair attempts with pagination support."""
        pass

    @abstractmethod
    async def count(self) -> int:
        """Returns the total number of stored repair attempts."""
        pass


class BaseTestSuiteRepository(ABC):
    """Abstract interface for trusted test suite persistence."""

    @abstractmethod
    async def save(self, suite: Any) -> Any:
        """Persists a new or updated trusted test suite."""
        pass

    @abstractmethod
    async def get_by_id(self, suite_id: str) -> Optional[Any]:
        """Retrieves a trusted test suite by unique suite ID."""
        pass

    @abstractmethod
    async def get_by_run_id(self, run_id: str) -> Optional[Any]:
        """Retrieves a trusted test suite associated with a verification run ID."""
        pass

    @abstractmethod
    async def count(self) -> int:
        """Returns the total number of stored test suites."""
        pass

