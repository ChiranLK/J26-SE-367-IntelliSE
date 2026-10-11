"""Source-grounded extraction of a saved project discussion."""
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Path, Request

from intelise_c1.api.extraction_schemas import ExtractionRun
from intelise_c1.core.database import UNAVAILABLE_DETAIL, get_project_repository
from intelise_c1.services.extraction import InvalidExtraction, build_run
from intelise_c1.services.provider import ProviderTimeout, ProviderUnavailable

extractions_router = APIRouter(prefix="/projects", tags=["extractions"])
ProjectId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]


async def context(project_id: str, request: Request):
    project = await get_project_repository(request).get(ObjectId(project_id))
    if project is None:
        raise HTTPException(404, "Project not found.")
    repository = getattr(request.app.state, "extractions", None)
    if repository is None:
        raise HTTPException(503, UNAVAILABLE_DETAIL)
    return project, repository


@extractions_router.post("/{project_id}/extractions", response_model=ExtractionRun, status_code=201)
async def extract(project_id: ProjectId, request: Request) -> ExtractionRun:
    project, repository = await context(project_id, request)
    if len(project.discussion_text) > request.app.state.settings.extraction_max_characters:
        raise HTTPException(413, "Discussion exceeds the configured extraction character limit.")
    provider = request.app.state.extraction_provider
    try:
        output = await provider.extract(project.discussion_text)
        run = build_run(project.discussion_text, output, project.id, provider.model_identifier)
    except ProviderTimeout:
        raise HTTPException(504, "Requirement extraction provider timed out.") from None
    except ProviderUnavailable:
        raise HTTPException(503, "Requirement extraction provider unavailable. Check API credentials, model configuration and provider availability.") from None
    except InvalidExtraction:
        raise HTTPException(502, "Provider output failed structured-output or source-evidence validation. No extraction was saved.") from None
    return await repository.create(run)


@extractions_router.get("/{project_id}/extractions/latest", response_model=ExtractionRun)
async def latest(project_id: ProjectId, request: Request) -> ExtractionRun:
    project, repository = await context(project_id, request)
    run = await repository.latest(project.id)
    if run is None:
        raise HTTPException(404, "No extraction found for this project.")
    return run
