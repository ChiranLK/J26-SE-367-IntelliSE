"""Append-only predictions; never update projects or extracted requirements."""
from pymongo.asynchronous.collection import AsyncCollection

from intelise_c1.api.classification_schemas import ClassificationRun


class ClassificationRepository:
    def __init__(self, collection: AsyncCollection):
        self.collection = collection
        self._index_ready = False

    async def ensure_index(self):
        if not self._index_ready:
            await self.collection.create_index(
                [("project_id", 1), ("extraction_run_id", 1), ("classified_at", -1), ("_id", -1)], name="classifications_latest"
            )
            await self.collection.create_index("classification_id", unique=True, name="classification_run_id")
            self._index_ready = True

    async def create(self, run: ClassificationRun) -> ClassificationRun:
        await self.ensure_index()
        await self.collection.insert_one(run.model_dump())
        return run

    async def latest(self, project_id: str, extraction_run_id: str) -> ClassificationRun | None:
        await self.ensure_index()
        document = await self.collection.find_one(
            {"project_id": project_id, "extraction_run_id": extraction_run_id},
            sort=[("classified_at", -1), ("_id", -1)],
        )
        return ClassificationRun(**{key: value for key, value in document.items() if key != "_id"}) if document else None

    async def get(self, project_id: str, extraction_run_id: str, classification_id: str) -> ClassificationRun | None:
        document = await self.collection.find_one({"project_id": project_id, "extraction_run_id": extraction_run_id,
                                                   "classification_id": classification_id})
        return ClassificationRun(**{key: value for key, value in document.items() if key != "_id"}) if document else None
