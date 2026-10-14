import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.core.logging import logger
from app.repositories.base import BaseSubmissionRepository, BaseVerificationRunRepository
from app.schemas.common import VerificationStatus
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.verification import VerificationRunResponse


class InMemorySubmissionRepository(BaseSubmissionRepository):
    """
    TEMPORARY IN-MEMORY STORAGE FOR CODE SUBMISSIONS.

    WARNING:
    All submissions stored in this repository reside strictly in volatile process memory.
    Temporary data is completely LOST upon application shutdown or restart.
    This repository is intended solely for local development and automated testing
    while the shared MongoDB Atlas cluster is unavailable.
    """

    def __init__(self) -> None:
        self._storage: Dict[str, CodeSubmissionResponse] = {}
        self._lock = asyncio.Lock()
        logger.info(
            "Initialized InMemorySubmissionRepository. "
            "NOTE: Temporary in-memory storage active; data will be lost on application restart."
        )

    async def save(self, submission: CodeSubmissionResponse) -> CodeSubmissionResponse:
        async with self._lock:
            self._storage[submission.id] = submission
            return submission

    async def get_by_id(self, submission_id: str) -> Optional[CodeSubmissionResponse]:
        async with self._lock:
            return self._storage.get(submission_id)

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[CodeSubmissionResponse]:
        async with self._lock:
            items = list(self._storage.values())
            # Sort newest first
            items.sort(key=lambda s: s.created_at, reverse=True)
            return items[skip : skip + limit]

    async def count(self) -> int:
        async with self._lock:
            return len(self._storage)

    async def clear(self) -> None:
        """Utility method to reset in-memory state during automated tests."""
        async with self._lock:
            self._storage.clear()


class InMemoryVerificationRunRepository(BaseVerificationRunRepository):
    """
    TEMPORARY IN-MEMORY STORAGE FOR VERIFICATION RUNS.

    WARNING:
    All verification runs and associated records in this repository reside strictly
    in volatile process memory. Temporary data is completely LOST upon application
    shutdown or restart.
    This repository is intended solely for local development and automated testing
    while the shared MongoDB Atlas cluster is unavailable.
    """

    def __init__(self) -> None:
        self._storage: Dict[str, VerificationRunResponse] = {}
        self._lock = asyncio.Lock()
        logger.info(
            "Initialized InMemoryVerificationRunRepository. "
            "NOTE: Temporary in-memory storage active; data will be lost on application restart."
        )

    async def save(self, run: VerificationRunResponse) -> VerificationRunResponse:
        async with self._lock:
            self._storage[run.id] = run
            return run

    async def get_by_id(self, run_id: str) -> Optional[VerificationRunResponse]:
        async with self._lock:
            return self._storage.get(run_id)

    async def get_by_submission_id(self, submission_id: str) -> List[VerificationRunResponse]:
        async with self._lock:
            runs = [r for r in self._storage.values() if r.submission_id == submission_id]
            runs.sort(key=lambda r: r.created_at, reverse=True)
            return runs

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[VerificationRunResponse]:
        async with self._lock:
            items = list(self._storage.values())
            items.sort(key=lambda r: r.created_at, reverse=True)
            return items[skip : skip + limit]

    async def update_status(
        self,
        run_id: str,
        status: VerificationStatus,
        error_message: Optional[str] = None,
    ) -> Optional[VerificationRunResponse]:
        async with self._lock:
            run = self._storage.get(run_id)
            if not run:
                return None
            updated_run = run.model_copy(
                update={
                    "status": status,
                    "error_message": error_message,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._storage[run_id] = updated_run
            return updated_run

    async def count(self) -> int:
        async with self._lock:
            return len(self._storage)

    async def clear(self) -> None:
        """Utility method to reset in-memory state during automated tests."""
        async with self._lock:
            self._storage.clear()
