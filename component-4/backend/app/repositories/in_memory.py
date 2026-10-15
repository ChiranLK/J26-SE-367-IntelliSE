import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.logging import logger
from app.repositories.base import (
    BaseRepairRepository,
    BaseSubmissionRepository,
    BaseTestSuiteRepository,
    BaseVerificationRunRepository,
)
from app.schemas.common import VerificationStatus
from app.schemas.repair import RepairAttempt
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


class InMemoryRepairRepository(BaseRepairRepository):
    """In-memory storage for repair attempts and re-verification outcomes."""

    def __init__(self) -> None:
        self._storage: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def save(self, repair: Any) -> Any:
        async with self._lock:
            canonical_id = getattr(repair, "repair_id", None) or getattr(repair, "id", None)
            if canonical_id:
                self._storage[canonical_id] = repair
            alt_id = getattr(repair, "id", None)
            if alt_id and alt_id != canonical_id:
                self._storage[alt_id] = repair
            return repair

    async def get_by_id(self, repair_id: str) -> Optional[Any]:
        async with self._lock:
            if repair_id in self._storage:
                return self._storage[repair_id]
            for item in self._storage.values():
                item_repair_id = getattr(item, "repair_id", None)
                item_id = getattr(item, "id", None)
                if repair_id in (item_repair_id, item_id):
                    return item
            return None

    async def get_by_original_run_id(self, run_id: str) -> List[Any]:
        async with self._lock:
            seen_ids = set()
            items = []
            for r in self._storage.values():
                item_id = getattr(r, "repair_id", None) or getattr(r, "id", None)
                if item_id and item_id not in seen_ids and getattr(r, "original_run_id", None) == run_id:
                    seen_ids.add(item_id)
                    items.append(r)
            items.sort(key=lambda r: getattr(r, "created_at", None) or datetime.min, reverse=True)
            return items

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[Any]:
        async with self._lock:
            seen_ids = set()
            items = []
            for r in self._storage.values():
                item_id = getattr(r, "repair_id", None) or getattr(r, "id", None)
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    items.append(r)
            items.sort(key=lambda r: getattr(r, "created_at", None) or datetime.min, reverse=True)
            return items[skip : skip + limit]

    async def count(self) -> int:
        async with self._lock:
            seen_ids = {getattr(r, "repair_id", None) or getattr(r, "id", None) for r in self._storage.values()}
            return len(seen_ids - {None})

    async def clear(self) -> None:
        """Utility method to reset in-memory state during automated tests."""
        async with self._lock:
            self._storage.clear()


class InMemoryTestSuiteRepository(BaseTestSuiteRepository):
    """In-memory storage for trusted test suites."""

    def __init__(self) -> None:
        self._storage: Dict[str, Any] = {}
        self._run_index: Dict[str, str] = {}  # run_id -> suite_id
        self._lock = asyncio.Lock()

    async def save(self, suite: Any) -> Any:
        async with self._lock:
            suite_id = getattr(suite, "suite_id", None)
            run_id = getattr(suite, "verification_run_id", None)
            if suite_id:
                self._storage[suite_id] = suite
            if run_id and suite_id:
                self._run_index[run_id] = suite_id
            return suite

    async def get_by_id(self, suite_id: str) -> Optional[Any]:
        async with self._lock:
            return self._storage.get(suite_id)

    async def get_by_run_id(self, run_id: str) -> Optional[Any]:
        async with self._lock:
            suite_id = self._run_index.get(run_id)
            if suite_id and suite_id in self._storage:
                return self._storage[suite_id]
            for item in self._storage.values():
                if getattr(item, "verification_run_id", None) == run_id:
                    return item
            return None

    async def count(self) -> int:
        async with self._lock:
            return len(self._storage)

    async def clear(self) -> None:
        async with self._lock:
            self._storage.clear()
            self._run_index.clear()

