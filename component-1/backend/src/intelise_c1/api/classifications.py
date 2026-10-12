"""Classify a particular saved extraction, never an implicit latest run."""
from typing import Annotated
from uuid import UUID

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Path, Request
from starlette.concurrency import run_in_threadpool

from intelise_c1.api.classification_schemas import ClassificationRun
from intelise_c1.core.database import UNAVAILABLE_DETAIL, get_project_repository
from intelise_c1.services.classifier import ClassifierUnavailable, UNAVAILABLE, classification_run

classifications_router = APIRouter(prefix="/projects", tags=["classifications"])
ProjectId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


async def context(project_id: str, run_id: UUID, request: Request):
    project = await get_project_repository(request).get(ObjectId(project_id))
    if project is None:
        raise HTTPException(404, "Project not found.")
    extractions = getattr(request.app.state, "extractions", None)
    repository = getattr(request.app.state, "classifications", None)
    if extractions is None or repository is None:
        raise HTTPException(503, UNAVAILABLE_DETAIL)
    extraction = await extractions.get(project.id, str(run_id))
    if extraction is None:
        raise HTTPException(404, "Extraction run not found for this project.")
    return extraction, repository


@classifications_router.post("/{project_id}/extractions/{run_id}/classifications", response_model=ClassificationRun, status_code=201)
async def classify(project_id: ProjectId, run_id: UUID, request: Request):
    extraction, repository = await context(project_id, run_id, request)
    try:
        labels, model, version = await run_in_threadpool(
            request.app.state.classifier.predict, [candidate.requirement_text for candidate in extraction.candidates]
        )
        run = classification_run(extraction, labels, model, version)
    except ClassifierUnavailable:
        raise HTTPException(503, UNAVAILABLE) from None
    return await repository.create(run)


@classifications_router.get("/{project_id}/extractions/{run_id}/classifications/latest", response_model=ClassificationRun)
async def latest(project_id: ProjectId, run_id: UUID, request: Request):
    extraction, repository = await context(project_id, run_id, request)
    run = await repository.latest(extraction.project_id, extraction.run_id)
    if run is None:
        raise HTTPException(404, "No classification found for this extraction run.")
    return run
