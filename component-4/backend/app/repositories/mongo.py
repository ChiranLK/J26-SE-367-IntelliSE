import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError
from app.core.config import settings
from app.core.errors import StorageException
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
from app.schemas.test_suite import TrustedTestSuite
from app.schemas.verification import VerificationRunResponse


class MongoSubmissionRepository(BaseSubmissionRepository):
    """
    MongoDB Atlas implementation for Code Submissions.
    Used when STORAGE_BACKEND is set to 'mongodb' and a valid MONGODB_URI is provided.
    Executes synchronous PyMongo operations in a worker thread pool via asyncio.to_thread
    to ensure non-blocking asynchronous execution.
    """

    def __init__(self, db: Database) -> None:
        self.collection: Collection = db["submissions"]
        try:
            self.collection.create_index("id", unique=True)
            self.collection.create_index("created_at")
        except PyMongoError as err:
            logger.warning("Could not verify or create MongoDB indexes for submissions: %s", err)

    async def save(self, submission: CodeSubmissionResponse) -> CodeSubmissionResponse:
        try:
            doc = submission.model_dump(mode="json")
            doc["_id"] = submission.id
            await asyncio.to_thread(
                self.collection.replace_one, {"_id": submission.id}, doc, upsert=True
            )
            return submission
        except PyMongoError as e:
            logger.error("MongoDB error saving submission %s: %s", submission.id, e)
            raise StorageException(f"Failed to persist submission to MongoDB: {e}")

    async def get_by_id(self, submission_id: str) -> Optional[CodeSubmissionResponse]:
        try:
            doc = await asyncio.to_thread(
                self.collection.find_one, {"_id": submission_id}
            )
            if not doc:
                return None
            doc.pop("_id", None)
            return CodeSubmissionResponse.model_validate(doc)
        except PyMongoError as e:
            logger.error("MongoDB error fetching submission %s: %s", submission_id, e)
            raise StorageException(f"Failed to fetch submission from MongoDB: {e}")

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[CodeSubmissionResponse]:
        try:
            def _query_all():
                cursor = (
                    self.collection.find()
                    .sort("created_at", -1)
                    .skip(skip)
                    .limit(limit)
                )
                items = []
                for doc in cursor:
                    doc.pop("_id", None)
                    items.append(CodeSubmissionResponse.model_validate(doc))
                return items

            return await asyncio.to_thread(_query_all)
        except PyMongoError as e:
            logger.error("MongoDB error listing submissions: %s", e)
            raise StorageException(f"Failed to list submissions from MongoDB: {e}")

    async def count(self) -> int:
        try:
            return await asyncio.to_thread(self.collection.count_documents, {})
        except PyMongoError as e:
            logger.error("MongoDB error counting submissions: %s", e)
            raise StorageException(f"Failed to count submissions in MongoDB: {e}")


class MongoVerificationRunRepository(BaseVerificationRunRepository):
    """
    MongoDB Atlas implementation for Verification Runs.
    Used when STORAGE_BACKEND is set to 'mongodb' and a valid MONGODB_URI is provided.
    Executes synchronous PyMongo operations in a worker thread pool via asyncio.to_thread
    to ensure non-blocking asynchronous execution.
    """

    def __init__(self, db: Database) -> None:
        self.collection: Collection = db["verification_runs"]
        try:
            self.collection.create_index("id", unique=True)
            self.collection.create_index("submission_id")
            self.collection.create_index("created_at")
        except PyMongoError as err:
            logger.warning("Could not verify or create MongoDB indexes for verification_runs: %s", err)

    async def save(self, run: VerificationRunResponse) -> VerificationRunResponse:
        try:
            doc = run.model_dump(mode="json")
            doc["_id"] = run.id
            await asyncio.to_thread(
                self.collection.replace_one, {"_id": run.id}, doc, upsert=True
            )
            return run
        except PyMongoError as e:
            logger.error("MongoDB error saving verification run %s: %s", run.id, e)
            raise StorageException(f"Failed to persist verification run to MongoDB: {e}")

    async def get_by_id(self, run_id: str) -> Optional[VerificationRunResponse]:
        try:
            doc = await asyncio.to_thread(
                self.collection.find_one, {"_id": run_id}
            )
            if not doc:
                return None
            doc.pop("_id", None)
            return VerificationRunResponse.model_validate(doc)
        except PyMongoError as e:
            logger.error("MongoDB error fetching verification run %s: %s", run_id, e)
            raise StorageException(f"Failed to fetch verification run from MongoDB: {e}")

    async def get_by_submission_id(self, submission_id: str) -> List[VerificationRunResponse]:
        try:
            def _query_by_sub():
                cursor = (
                    self.collection.find({"submission_id": submission_id})
                    .sort("created_at", -1)
                )
                items = []
                for doc in cursor:
                    doc.pop("_id", None)
                    items.append(VerificationRunResponse.model_validate(doc))
                return items

            return await asyncio.to_thread(_query_by_sub)
        except PyMongoError as e:
            logger.error("MongoDB error querying runs for submission %s: %s", submission_id, e)
            raise StorageException(f"Failed to query verification runs from MongoDB: {e}")

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[VerificationRunResponse]:
        try:
            def _query_all():
                cursor = (
                    self.collection.find()
                    .sort("created_at", -1)
                    .skip(skip)
                    .limit(limit)
                )
                items = []
                for doc in cursor:
                    doc.pop("_id", None)
                    items.append(VerificationRunResponse.model_validate(doc))
                return items

            return await asyncio.to_thread(_query_all)
        except PyMongoError as e:
            logger.error("MongoDB error listing verification runs: %s", e)
            raise StorageException(f"Failed to list verification runs from MongoDB: {e}")

    async def update_status(
        self,
        run_id: str,
        status: VerificationStatus,
        error_message: Optional[str] = None,
    ) -> Optional[VerificationRunResponse]:
        try:
            updated_at = datetime.now(timezone.utc).isoformat()
            update_data: Dict[str, Any] = {
                "status": status.value,
                "updated_at": updated_at,
            }
            if error_message is not None:
                update_data["error_message"] = error_message

            def _update():
                return self.collection.find_one_and_update(
                    {"_id": run_id},
                    {"$set": update_data},
                    return_document=ReturnDocument.AFTER,
                )

            result = await asyncio.to_thread(_update)
            if not result:
                return None
            result.pop("_id", None)
            return VerificationRunResponse.model_validate(result)
        except PyMongoError as e:
            logger.error("MongoDB error updating status for run %s: %s", run_id, e)
            raise StorageException(f"Failed to update verification run in MongoDB: {e}")

    async def count(self) -> int:
        try:
            return await asyncio.to_thread(self.collection.count_documents, {})
        except PyMongoError as e:
            logger.error("MongoDB error counting verification runs: %s", e)
            raise StorageException(f"Failed to count verification runs in MongoDB: {e}")


class MongoRepairRepository(BaseRepairRepository):
    """
    MongoDB Atlas implementation for Repair Attempts.
    Stores and retrieves repair iterations in the 'repair_attempts' collection.
    """

    def __init__(self, db: Database) -> None:
        self.collection: Collection = db["repair_attempts"]
        try:
            self.collection.create_index("repair_id")
            self.collection.create_index("id", unique=True)
            self.collection.create_index("original_run_id")
            self.collection.create_index("created_at")
        except PyMongoError as err:
            logger.warning("Could not verify or create MongoDB indexes for repair_attempts: %s", err)

    async def save(self, repair: RepairAttempt) -> RepairAttempt:
        try:
            doc = repair.model_dump(mode="json")
            canonical_id = repair.repair_id or repair.id
            doc["repair_id"] = canonical_id
            doc["id"] = canonical_id

            def _save():
                # Check for existing record under canonical_id as repair_id, id, or _id
                existing = self.collection.find_one(
                    {"$or": [{"repair_id": canonical_id}, {"id": canonical_id}, {"_id": canonical_id}]}
                )
                if existing:
                    # Preserve MongoDB _id from existing record so replace_one does not modify immutable _id
                    mongo_id = existing["_id"]
                    doc["_id"] = mongo_id
                    self.collection.replace_one({"_id": mongo_id}, doc, upsert=False)
                else:
                    doc["_id"] = canonical_id
                    self.collection.replace_one({"_id": canonical_id}, doc, upsert=True)

            await asyncio.to_thread(_save)
            return repair
        except PyMongoError as e:
            logger.error("MongoDB error saving repair attempt %s: %s", repair.repair_id, e)
            raise StorageException(f"Failed to persist repair attempt to MongoDB: {e}")

    async def get_by_id(self, repair_id: str) -> Optional[RepairAttempt]:
        try:
            def _find():
                return self.collection.find_one(
                    {"$or": [{"repair_id": repair_id}, {"id": repair_id}, {"_id": repair_id}]}
                )

            doc = await asyncio.to_thread(_find)
            if not doc:
                return None
            doc.pop("_id", None)
            return RepairAttempt.model_validate(doc)
        except PyMongoError as e:
            logger.error("MongoDB error fetching repair attempt %s: %s", repair_id, e)
            raise StorageException(f"Failed to fetch repair attempt from MongoDB: {e}")

    async def get_by_original_run_id(self, original_run_id: str) -> List[RepairAttempt]:
        try:
            def _query():
                cursor = (
                    self.collection.find({"original_run_id": original_run_id})
                    .sort("created_at", -1)
                )
                items = []
                for doc in cursor:
                    doc.pop("_id", None)
                    items.append(RepairAttempt.model_validate(doc))
                return items

            return await asyncio.to_thread(_query)
        except PyMongoError as e:
            logger.error(
                "MongoDB error fetching repair attempts for run %s: %s",
                original_run_id,
                e,
            )
            raise StorageException(f"Failed to fetch repair attempts from MongoDB: {e}")

    async def list_all(self, skip: int = 0, limit: int = 100) -> List[RepairAttempt]:
        try:
            def _query_all():
                cursor = (
                    self.collection.find()
                    .sort("created_at", -1)
                    .skip(skip)
                    .limit(limit)
                )
                items = []
                for doc in cursor:
                    doc.pop("_id", None)
                    items.append(RepairAttempt.model_validate(doc))
                return items

            return await asyncio.to_thread(_query_all)
        except PyMongoError as e:
            logger.error("MongoDB error listing repair attempts: %s", e)
            raise StorageException(f"Failed to list repair attempts from MongoDB: {e}")

    async def count(self) -> int:
        try:
            return await asyncio.to_thread(self.collection.count_documents, {})
        except PyMongoError as e:
            logger.error("MongoDB error counting repair attempts: %s", e)
            raise StorageException(f"Failed to count repair attempts in MongoDB: {e}")


class MongoTestSuiteRepository(BaseTestSuiteRepository):
    """
    MongoDB Atlas implementation for Trusted Test Suites.
    Used when STORAGE_BACKEND is set to 'mongodb' and a valid MONGODB_URI is provided.
    Executes synchronous PyMongo operations in a worker thread pool via asyncio.to_thread
    to ensure non-blocking asynchronous execution.
    """

    def __init__(self, db: Database) -> None:
        self.collection: Collection = db["trusted_test_suites"]
        try:
            self.collection.create_index("suite_id", unique=True)
            self.collection.create_index("verification_run_id")
            self.collection.create_index("created_at")
        except PyMongoError as err:
            logger.warning("Could not verify or create MongoDB indexes for trusted_test_suites: %s", err)

    async def save(self, suite: TrustedTestSuite) -> TrustedTestSuite:
        try:
            doc = suite.model_dump(mode="json")
            doc["_id"] = suite.suite_id
            await asyncio.to_thread(
                self.collection.replace_one, {"_id": suite.suite_id}, doc, upsert=True
            )
            return suite
        except PyMongoError as e:
            logger.error("MongoDB error saving trusted test suite %s: %s", suite.suite_id, e)
            raise StorageException(f"Failed to persist trusted test suite to MongoDB: {e}")

    async def get_by_id(self, suite_id: str) -> Optional[TrustedTestSuite]:
        try:
            def _find():
                return self.collection.find_one(
                    {"$or": [{"suite_id": suite_id}, {"_id": suite_id}]}
                )

            doc = await asyncio.to_thread(_find)
            if not doc:
                return None
            doc.pop("_id", None)
            return TrustedTestSuite.model_validate(doc)
        except PyMongoError as e:
            logger.error("MongoDB error fetching trusted test suite %s: %s", suite_id, e)
            raise StorageException(f"Failed to fetch trusted test suite from MongoDB: {e}")

    async def get_by_run_id(self, run_id: str) -> Optional[TrustedTestSuite]:
        try:
            def _find_by_run():
                return self.collection.find_one(
                    {"verification_run_id": run_id},
                    sort=[("created_at", -1)],
                )

            doc = await asyncio.to_thread(_find_by_run)
            if not doc:
                return None
            doc.pop("_id", None)
            return TrustedTestSuite.model_validate(doc)
        except PyMongoError as e:
            logger.error(
                "MongoDB error fetching trusted test suite for run %s: %s",
                run_id,
                e,
            )
            raise StorageException(f"Failed to fetch trusted test suite from MongoDB: {e}")

    async def count(self) -> int:
        try:
            return await asyncio.to_thread(self.collection.count_documents, {})
        except PyMongoError as e:
            logger.error("MongoDB error counting trusted test suites: %s", e)
            raise StorageException(f"Failed to count trusted test suites in MongoDB: {e}")


def get_mongo_database() -> Database:
    """
    Initializes a PyMongo Database client for MongoDB Atlas.
    Raises StorageException if MONGODB_URI is empty or connection fails.
    Never silently ignores connection failures when MongoDB is explicitly configured.
    """
    if not settings.MONGODB_URI:
        raise StorageException(
            "STORAGE_BACKEND is set to 'mongodb', but MONGODB_URI is not configured. "
            "Please provide a valid MongoDB Atlas connection URI."
        )
    try:
        client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
        )
        # Ping to test connectivity
        client.admin.command("ping")
        logger.info("Successfully connected to MongoDB Atlas database: %s", settings.MONGODB_DB_NAME)
        return client[settings.MONGODB_DB_NAME]
    except Exception as exc:
        logger.error(
            "Failed to connect to MongoDB Atlas (%s): %s",
            settings.MONGODB_DB_NAME,
            exc,
        )
        raise StorageException(f"Failed to connect to MongoDB Atlas: {exc}")
