from app.core.config import settings
from app.repositories.base import (
    BaseRepairRepository,
    BaseSubmissionRepository,
    BaseTestSuiteRepository,
    BaseVerificationRunRepository,
)
from app.repositories.in_memory import (
    InMemoryRepairRepository,
    InMemorySubmissionRepository,
    InMemoryTestSuiteRepository,
    InMemoryVerificationRunRepository,
)
from app.repositories.mongo import (
    MongoRepairRepository,
    MongoSubmissionRepository,
    MongoTestSuiteRepository,
    MongoVerificationRunRepository,
    get_mongo_database,
)

# Global singleton repository instances for in-memory storage mode
_in_memory_submission_repo: InMemorySubmissionRepository = InMemorySubmissionRepository()
_in_memory_verification_repo: InMemoryVerificationRunRepository = InMemoryVerificationRunRepository()
_in_memory_repair_repo: InMemoryRepairRepository = InMemoryRepairRepository()
_in_memory_test_suite_repo: InMemoryTestSuiteRepository = InMemoryTestSuiteRepository()

_mongo_submission_repo: BaseSubmissionRepository | None = None
_mongo_verification_repo: BaseVerificationRunRepository | None = None
_mongo_repair_repo: BaseRepairRepository | None = None
_mongo_test_suite_repo: BaseTestSuiteRepository | None = None


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


def get_repair_repository() -> BaseRepairRepository:
    """
    Factory returning the configured repair repository.
    When STORAGE_BACKEND is 'memory', returns the in-memory repository.
    When STORAGE_BACKEND is 'mongodb', returns the MongoDB repository or raises
    StorageException on connection failure. Never silently falls back.
    """
    global _mongo_repair_repo
    if settings.STORAGE_BACKEND.lower() == "mongodb":
        if _mongo_repair_repo is None:
            db = get_mongo_database()
            _mongo_repair_repo = MongoRepairRepository(db)
        return _mongo_repair_repo
    return _in_memory_repair_repo


def get_test_suite_repository() -> BaseTestSuiteRepository:
    """
    Factory returning the configured trusted test suite repository.
    When STORAGE_BACKEND is 'memory', returns the in-memory repository.
    When STORAGE_BACKEND is 'mongodb', returns the MongoDB repository or raises
    StorageException on connection failure. Never silently falls back.
    """
    global _mongo_test_suite_repo
    if settings.STORAGE_BACKEND.lower() == "mongodb":
        if _mongo_test_suite_repo is None:
            db = get_mongo_database()
            _mongo_test_suite_repo = MongoTestSuiteRepository(db)
        return _mongo_test_suite_repo
    return _in_memory_test_suite_repo


__all__ = [
    "BaseRepairRepository",
    "BaseSubmissionRepository",
    "BaseTestSuiteRepository",
    "BaseVerificationRunRepository",
    "InMemoryRepairRepository",
    "InMemorySubmissionRepository",
    "InMemoryTestSuiteRepository",
    "InMemoryVerificationRunRepository",
    "MongoRepairRepository",
    "MongoSubmissionRepository",
    "MongoTestSuiteRepository",
    "MongoVerificationRunRepository",
    "get_repair_repository",
    "get_submission_repository",
    "get_test_suite_repository",
    "get_verification_repository",
]

