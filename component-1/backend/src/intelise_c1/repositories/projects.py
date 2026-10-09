"""Store original discussions and fetch bounded project summaries."""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection

from intelise_c1.api.project_schemas import ProjectCreate, ProjectPage, ProjectRecord, ProjectSummary


def public_fields(document: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(document["_id"]), **{key: value for key, value in document.items() if key != "_id"}}


class ProjectRepository:
    def __init__(self, collection: AsyncCollection) -> None:
        self.collection = collection
        self._index_ready = False

    async def ensure_index(self) -> None:
        if not self._index_ready:
            await self.collection.create_index(
                [("created_at", -1), ("_id", -1)], name="projects_newest_first"
            )
            self._index_ready = True

    async def create(self, payload: ProjectCreate) -> ProjectRecord:
        await self.ensure_index()
        now = datetime.now(timezone.utc)
        # BSON datetime precision is milliseconds; return the exact stored value.
        now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
        document = {
            "_id": ObjectId(),
            **payload.model_dump(),
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(document)
        return ProjectRecord(**public_fields(document))

    async def list(self, *, limit: int, offset: int) -> ProjectPage:
        await self.ensure_index()
        cursor = (
            self.collection.find({}, {"discussion_text": 0})
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
        document = await self.collection.find_one({"_id": project_id})
        return ProjectRecord(**public_fields(document)) if document is not None else None
