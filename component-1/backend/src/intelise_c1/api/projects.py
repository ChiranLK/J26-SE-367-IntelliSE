"""Project creation, summary listing, and retrieval without AI processing."""

from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Path, Query, Request, Response

from intelise_c1.api.project_schemas import ProjectCreate, ProjectPage, ProjectRecord
from intelise_c1.core.database import get_project_repository
from intelise_c1.services.transcription_provenance import TranscriptionReferenceError

projects_router = APIRouter(prefix="/projects", tags=["projects"])


@projects_router.post("", response_model=ProjectRecord, status_code=201, response_model_exclude_unset=True,
                      responses={404: {"description": "Referenced transcription not found"},
                                 409: {"description": "Transcription not completed or speech result unusable"}})
async def create_project(payload: ProjectCreate, request: Request) -> ProjectRecord:
    try:
        return await get_project_repository(request).create(payload)
    except TranscriptionReferenceError as error:
        raise HTTPException(error.status_code, str(error)) from None


@projects_router.get("", response_model=ProjectPage)
async def list_projects(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> ProjectPage:
    return await get_project_repository(request).list(limit=limit, offset=offset)


@projects_router.get("/{project_id}", response_model=ProjectRecord, response_model_exclude_unset=True)
async def get_project(
    project_id: Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")],
    request: Request,
) -> ProjectRecord:
    project = await get_project_repository(request).get(ObjectId(project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@projects_router.delete("/{project_id}", status_code=204, response_class=Response,
    responses={404: {"description": "Project not found"},
               503: {"description": "Project persistence unavailable"}},
    description="Remove project from listing and normal retrieval. Original project, extraction, classification, label-review and transcription records are retained for recovery; this is not permanent erasure. Repeated deletion of the same retained project is idempotent.")
async def delete_project(
    project_id: Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")],
    request: Request,
) -> Response:
    if not await get_project_repository(request).delete(ObjectId(project_id)):
        raise HTTPException(404, "Project not found.")
    return Response(status_code=204)
