"""Template SRS generation and self-reported client decisions; no AI inference."""
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from intelise_c1.api.classifications import ProjectId
from intelise_c1.api.reviews import get_reviews, review_context
from intelise_c1.api.srs_schemas import ApprovalInput, BulkAcceptInput, DraftInput, FeedbackInput, RevisionInput, SrsState
from intelise_c1.core.database import UNAVAILABLE_DETAIL, get_project_repository
from intelise_c1.services.srs import SrsConflict, accept_remaining, approve, draft, feedback, revise
from intelise_c1.api.reviews import text_hash
from intelise_c1.repositories.srs import InvalidSrs

srs_router = APIRouter(prefix='/projects/{project_id}/srs', tags=['SRS client review'])


async def resources(project_id, request):
    project = await get_project_repository(request).get(ObjectId(project_id))
    if project is None:
        raise HTTPException(404, 'Project not found.')
    repository = getattr(request.app.state, 'srs', None)
    if repository is None:
        raise HTTPException(503, UNAVAILABLE_DETAIL)
    return project, repository


async def apply(project_id, operation, body, request, transform):
    _, repository = await resources(project_id, request)
    try:
        return await repository.apply(project_id.lower(), operation, body, transform)
    except SrsConflict as error:
        raise HTTPException(409, str(error)) from None
    except (ValidationError, InvalidSrs):
        raise HTTPException(503, 'Saved SRS data is invalid. Original records were preserved.') from None


@srs_router.get('', response_model=SrsState)
async def read_srs(project_id: ProjectId, request: Request):
    _, repository = await resources(project_id, request)
    try:
        return await repository.get(project_id.lower())
    except (ValidationError, InvalidSrs):
        raise HTTPException(503, 'Saved SRS data is invalid. Original records were preserved.') from None


@srs_router.post('', response_model=SrsState, description='Create a template draft from model labels with saved human corrections taking priority. Does not call an LLM or approve requirements.')
async def generate_srs(project_id: ProjectId, body: DraftInput, request: Request):
    project, _ = await resources(project_id, request)
    extraction, classification, _, _, _ = await review_context(project_id, body.extraction_run_id, body.classification_id, request)
    page = await get_reviews(project_id, body.extraction_run_id, body.classification_id, request)
    if text_hash(project.discussion_text) != extraction.source_discussion_hash:
        raise HTTPException(409, 'Extraction source does not match this project. No SRS was saved.')

    def create(state):
        if state.versions:
            raise SrsConflict('An SRS already exists. Use the revision workflow to preserve version history.')
        version = draft(project, extraction, classification, page.reviews, body.reviewer_id)
        state.versions.append(version)
        return version
    return await apply(project_id, 'draft', body, request, create)


@srs_router.post('/feedback', response_model=SrsState, description='Append a client decision to the latest draft. Identity is self-reported, not authenticated.')
async def save_feedback(project_id: ProjectId, body: FeedbackInput, request: Request):
    return await apply(project_id, 'feedback', body, request, lambda state: feedback(state, body))


@srs_router.post('/revisions', response_model=SrsState, description='Create a new draft with explicit authored changes. Previous versions remain intact; all client decisions reset.')
async def create_revision(project_id: ProjectId, body: RevisionInput, request: Request):
    return await apply(project_id, 'revision', body, request, lambda state: revise(state, body))


@srs_router.post('/approval', response_model=SrsState, description='Approve only the latest fully accepted version and its exact content hash. Self-reported client approval, not independent verification.')
async def approve_srs(project_id: ProjectId, body: ApprovalInput, request: Request):
    return await apply(project_id, 'approval', body, request, lambda state: approve(state, body))


@srs_router.post('/accept-remaining', response_model=SrsState, description='Explicitly accept pending requirements in one atomic action. Existing change/clarification requests are preserved. Does not approve the SRS.')
async def accept_pending(project_id: ProjectId, body: BulkAcceptInput, request: Request):
    return await apply(project_id, 'accept-remaining', body, request, lambda state: accept_remaining(state, body))
