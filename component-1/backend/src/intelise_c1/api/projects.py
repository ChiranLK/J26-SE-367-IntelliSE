"""Project creation, summary listing, and retrieval without AI processing."""

from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Path, Query, Request

from intelise_c1.api.project_schemas import ProjectCreate, ProjectPage, ProjectRecord
from intelise_c1.core.database import get_project_repository

projects_router = APIRouter(prefix="/projects", tags=["projects"])


@projects_router.post("", response_model=ProjectRecord, status_code=201)
async def create_project(payload: ProjectCreate, request: Request) -> ProjectRecord:
    return await get_project_repository(request).create(payload)


@projects_router.get("", response_model=ProjectPage)
async def list_projects(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> ProjectPage:
    return await get_project_repository(request).list(limit=limit, offset=offset)


@projects_router.get("/{project_id}", response_model=ProjectRecord)
async def get_project(
    project_id: Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")],
    request: Request,
) -> ProjectRecord:
    project = await get_project_repository(request).get(ObjectId(project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project
