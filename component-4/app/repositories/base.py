from abc import ABC, abstractmethod
from typing import List, Optional
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
