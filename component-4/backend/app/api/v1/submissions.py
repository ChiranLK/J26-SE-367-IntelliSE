from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from app.api.deps import get_submission_service
from app.schemas.common import ProgrammingLanguage
from app.schemas.submission import (
    CodeSubmissionCreate,
    CodeSubmissionListResponse,
    CodeSubmissionResponse,
)
from app.services.submission_service import SubmissionService

router = APIRouter(prefix="/submissions", tags=["Submissions"])


@router.post(
    "",
    response_model=CodeSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Code Manually",
    description="Accepts source code snippet, programming language, optional filename, and optional requirement IDs.",
)
async def submit_code_manually(
    payload: CodeSubmissionCreate,
    service: SubmissionService = Depends(get_submission_service),
) -> CodeSubmissionResponse:
    return await service.create_manual_submission(payload)


@router.post(
    "/upload",
    response_model=CodeSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload Source Code File",
    description=(
        "Safely uploads a source code file. Validates filename, file extension, max size, "
        "and text encoding. Code is stored safely for subsequent verification; it is NEVER executed."
    ),
)
async def upload_code_file(
    file: UploadFile = File(..., description="Source code file to upload"),
    language: Optional[ProgrammingLanguage] = Form(
        None, description="Optional programming language override"
    ),
    requirement_ids: Optional[str] = Form(
        None,
        description="Comma-separated requirement identifiers (e.g. 'REQ-01,REQ-02')",
    ),
    service: SubmissionService = Depends(get_submission_service),
) -> CodeSubmissionResponse:
    parsed_req_ids: List[str] = []
    if requirement_ids:
        parsed_req_ids = [
            req.strip() for req in requirement_ids.split(",") if req.strip()
        ]

    return await service.process_file_upload(
        file=file,
        language=language,
        requirement_ids=parsed_req_ids,
    )


@router.get(
    "",
    response_model=CodeSubmissionListResponse,
    summary="List Code Submissions",
    description="Lists all submissions currently stored.",
)
async def list_submissions(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Number of items to return"),
    service: SubmissionService = Depends(get_submission_service),
) -> CodeSubmissionListResponse:
    return await service.list_submissions(skip=skip, limit=limit)


@router.get(
    "/{submission_id}",
    response_model=CodeSubmissionResponse,
    summary="Get Submission Details",
    description="Retrieves full details of a specific code submission by ID.",
)
async def get_submission(
    submission_id: str,
    service: SubmissionService = Depends(get_submission_service),
) -> CodeSubmissionResponse:
    return await service.get_submission(submission_id)
