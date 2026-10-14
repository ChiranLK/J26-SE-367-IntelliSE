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
from app.repositories.base import BaseSubmissionRepository, BaseVerificationRunRepository
from app.schemas.common import VerificationStatus
from app.schemas.submission import CodeSubmissionResponse
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
