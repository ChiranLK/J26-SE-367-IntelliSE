"""Append-only extraction runs, isolated from projects and edited requirements."""
from pymongo.asynchronous.collection import AsyncCollection

from intelise_c1.api.extraction_schemas import ExtractionRun


class ExtractionRepository:
    def __init__(self, collection: AsyncCollection):
        self.collection = collection
        self._index_ready = False

    async def ensure_index(self):
        if not self._index_ready:
            await self.collection.create_index(
                [("project_id", 1), ("created_at", -1), ("_id", -1)], name="extractions_latest"
            )
            await self.collection.create_index("run_id", unique=True, name="extractions_run_id")
            self._index_ready = True

    async def create(self, run: ExtractionRun) -> ExtractionRun:
        await self.ensure_index()
        await self.collection.insert_one(run.model_dump())
        return run

    async def latest(self, project_id: str) -> ExtractionRun | None:
        await self.ensure_index()
        document = await self.collection.find_one(
            {"project_id": project_id}, sort=[("created_at", -1), ("_id", -1)]
        )
        if document is None:
            return None
        return ExtractionRun(**{key: value for key, value in document.items() if key != "_id"})

    async def get(self, project_id: str, run_id: str) -> ExtractionRun | None:
        document = await self.collection.find_one({"project_id": project_id, "run_id": run_id})
        return ExtractionRun(**{key: value for key, value in document.items() if key != "_id"}) if document else None
