from app.core.config import settings
from app.repositories.base import BaseSubmissionRepository, BaseVerificationRunRepository
from app.repositories.in_memory import (
    InMemorySubmissionRepository,
    InMemoryVerificationRunRepository,
)
from app.repositories.mongo import (
    MongoSubmissionRepository,
    MongoVerificationRunRepository,
    get_mongo_database,
)

# Global singleton repository instances for in-memory storage mode
_in_memory_submission_repo: InMemorySubmissionRepository = InMemorySubmissionRepository()
_in_memory_verification_repo: InMemoryVerificationRunRepository = InMemoryVerificationRunRepository()

_mongo_submission_repo: BaseSubmissionRepository | None = None
_mongo_verification_repo: BaseVerificationRunRepository | None = None


def get_submission_repository() -> BaseSubmissionRepository:
    """
    Factory returning the configured submission repository.
    When STORAGE_BACKEND is 'memory', returns the in-memory repository.
    When STORAGE_BACKEND is 'mongodb', returns the MongoDB repository or raises
    StorageException on connection failure. Never silently falls back.
    """
    global _mongo_submission_repo
    if settings.STORAGE_BACKEND.lower() == "mongodb":
        if _mongo_submission_repo is None:
            db = get_mongo_database()
            _mongo_submission_repo = MongoSubmissionRepository(db)
        return _mongo_submission_repo
    return _in_memory_submission_repo


def get_verification_repository() -> BaseVerificationRunRepository:
    """
    Factory returning the configured verification run repository.
    When STORAGE_BACKEND is 'memory', returns the in-memory repository.
    When STORAGE_BACKEND is 'mongodb', returns the MongoDB repository or raises
    StorageException on connection failure. Never silently falls back.
    """
    global _mongo_verification_repo
    if settings.STORAGE_BACKEND.lower() == "mongodb":
        if _mongo_verification_repo is None:
            db = get_mongo_database()
            _mongo_verification_repo = MongoVerificationRunRepository(db)
        return _mongo_verification_repo
    return _in_memory_verification_repo


__all__ = [
    "BaseSubmissionRepository",
    "BaseVerificationRunRepository",
    "InMemorySubmissionRepository",
    "InMemoryVerificationRunRepository",
    "MongoSubmissionRepository",
    "MongoVerificationRunRepository",
    "get_submission_repository",
    "get_verification_repository",
]
