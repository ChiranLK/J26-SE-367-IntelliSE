"""Store original discussions and fetch bounded project summaries."""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import PyMongoError
from pydantic import ValidationError

from intelise_c1.api.project_schemas import ProjectCreate, ProjectPage, ProjectRecord, ProjectSummary
from intelise_c1.services.transcription_provenance import build_provenance, TranscriptionReferenceError, INVALID_RESULT


def public_fields(document: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(document["_id"]), **{key: value for key, value in document.items() if key != "_id"}}


class ProjectRepository:
    def __init__(self, collection: AsyncCollection, transcriptions=None) -> None:
        self.collection = collection
        self.transcriptions = transcriptions
        self._index_ready = False

    async def ensure_index(self) -> None:
        if not self._index_ready:
            await self.collection.create_index(
                [("created_at", -1), ("_id", -1)], name="projects_newest_first"
            )
            self._index_ready = True

    async def create(self, payload: ProjectCreate) -> ProjectRecord:
        if payload.transcription_id is not None:
            if self.transcriptions is None:
                raise PyMongoError('Transcription persistence is unavailable')
            identifier = str(payload.transcription_id)
            try:
                job = await self.transcriptions.get(identifier)
            except ValidationError:
                raise TranscriptionReferenceError(409, INVALID_RESULT) from None
        now = datetime.now(timezone.utc)
        # BSON datetime precision is milliseconds; return the exact stored value.
        now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
        provenance = None
        if payload.transcription_id is not None:
            provenance = build_provenance(job, identifier, payload.discussion_text, now)
        await self.ensure_index()
        document = {
            "_id": ObjectId(),
            **payload.model_dump(exclude={"transcription_id"}),
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        if provenance is not None:
            document["transcription_provenance"] = provenance.model_dump()
        await self.collection.insert_one(document)
        return ProjectRecord(**public_fields(document))

    async def list(self, *, limit: int, offset: int) -> ProjectPage:
        await self.ensure_index()
        cursor = (
            self.collection.find({"deleted_at": {"$exists": False}}, {"discussion_text": 0, "transcription_provenance": 0})
            .sort([("created_at", -1), ("_id", -1)])
            .skip(offset)
            .limit(limit + 1)
        )
        documents = await cursor.to_list(length=limit + 1)
        return ProjectPage(
            items=[ProjectSummary(**public_fields(document)) for document in documents[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(documents) > limit,
        )

    async def get(self, project_id: ObjectId) -> ProjectRecord | None:
        document = await self.collection.find_one({"_id": project_id, "deleted_at": {"$exists": False}})
        return ProjectRecord(**public_fields(document)) if document is not None else None

    async def delete(self, project_id: ObjectId) -> bool:
        """Atomically hide a project, retaining original source and dependent history."""
        timestamp = datetime.now(timezone.utc)
        timestamp = timestamp.replace(microsecond=(timestamp.microsecond // 1000) * 1000)
        result = await self.collection.update_one(
            {"_id": project_id, "deleted_at": {"$exists": False}},
            {"$set": {"deleted_at": timestamp}},
        )
        if result.matched_count:
            return True
        # Identical explicit retries succeed without changing the first timestamp.
        return await self.collection.find_one({"_id": project_id}, {"_id": 1}) is not None
