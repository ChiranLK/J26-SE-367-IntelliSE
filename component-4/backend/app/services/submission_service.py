import os
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import UploadFile, status
from app.core.config import settings
from app.core.errors import FileValidationException, ResourceNotFoundException
from app.core.logging import logger
from app.repositories.base import BaseSubmissionRepository
from app.schemas.common import ProgrammingLanguage, SubmissionSource
from app.schemas.submission import (
    CodeSubmissionCreate,
    CodeSubmissionListResponse,
    CodeSubmissionResponse,
)

EXTENSION_TO_LANGUAGE = {
    ".py": ProgrammingLanguage.PYTHON,
    ".js": ProgrammingLanguage.JAVASCRIPT,
    ".jsx": ProgrammingLanguage.JAVASCRIPT,
    ".ts": ProgrammingLanguage.TYPESCRIPT,
    ".tsx": ProgrammingLanguage.TYPESCRIPT,
    ".java": ProgrammingLanguage.JAVA,
    ".cpp": ProgrammingLanguage.CPP,
    ".hpp": ProgrammingLanguage.CPP,
    ".c": ProgrammingLanguage.C,
    ".h": ProgrammingLanguage.C,
    ".cs": ProgrammingLanguage.CSHARP,
    ".go": ProgrammingLanguage.GO,
    ".rs": ProgrammingLanguage.RUST,
}


class SubmissionService:
    """Service handling manual submissions and secure file uploads."""

    def __init__(self, submission_repo: BaseSubmissionRepository) -> None:
        self.repo = submission_repo

    async def create_manual_submission(
        self, payload: CodeSubmissionCreate
    ) -> CodeSubmissionResponse:
        """Processes and stores a manually entered code submission."""
        submission_id = f"sub-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        sanitized_filename = None
        if payload.filename:
            sanitized_filename = os.path.basename(payload.filename.strip())

        submission = CodeSubmissionResponse(
            id=submission_id,
            code=payload.code,
            language=payload.language,
            filename=sanitized_filename,
            requirement_ids=payload.requirement_ids,
            source_type=SubmissionSource.MANUAL_ENTRY,
            created_at=now,
            metadata=payload.metadata,
        )

        logger.info(
            "Created manual submission %s (language=%s, length=%d chars)",
            submission_id,
            submission.language.value,
            len(submission.code),
        )
        return await self.repo.save(submission)

    async def process_file_upload(
        self,
        file: UploadFile,
        language: Optional[ProgrammingLanguage] = None,
        requirement_ids: Optional[List[str]] = None,
    ) -> CodeSubmissionResponse:
        """
        Securely handles a source code file upload.
        Validates filename, extension, file size, and text encoding.
        NOTE: Submitted code is strictly saved as text; it is NEVER executed.
        """
        raw_filename = file.filename or "uploaded_code.txt"

        # Reject null bytes or encoded control characters in filename
        decoded_filename = urllib.parse.unquote(raw_filename)
        if "\x00" in raw_filename or "\x00" in decoded_filename or "%00" in raw_filename.lower():
            raise FileValidationException(
                "Invalid filename: null characters are not permitted.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Handle both Windows and Unix directory separators safely
        sanitized_filename = os.path.basename(raw_filename.replace("\\", "/")).strip()

        # Check for path traversal attempts or empty name
        if not sanitized_filename or sanitized_filename in (".", ".."):
            raise FileValidationException(
                "Invalid filename provided in upload.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Validate file extension
        _, ext = os.path.splitext(sanitized_filename)
        if not ext:
            raise FileValidationException(
                "Uploaded file must include a valid file extension.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ext_lower = ext.lower()
        if ext_lower not in settings.ALLOWED_EXTENSIONS:
            raise FileValidationException(
                f"File extension '{ext_lower}' is not permitted. Allowed extensions: {', '.join(settings.ALLOWED_EXTENSIONS)}",
                status_code=status.HTTP_400_BAD_REQUEST,
                details={"allowed_extensions": settings.ALLOWED_EXTENSIONS, "filename": sanitized_filename},
            )

        # Read file contents in bounded chunks to prevent unbounded memory consumption
        chunk_size = 64 * 1024  # 64 KB
        chunks: List[bytes] = []
        total_size = 0

        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > settings.MAX_UPLOAD_SIZE_BYTES:
                raise FileValidationException(
                    f"File size exceeds the allowed limit of {settings.MAX_UPLOAD_SIZE_BYTES} bytes.",
                    status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413),
                    details={
                        "max_allowed": settings.MAX_UPLOAD_SIZE_BYTES,
                    },
                )
            chunks.append(chunk)

        if total_size == 0:
            raise FileValidationException(
                "Uploaded file is empty.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        file_bytes = b"".join(chunks)
        file_size = total_size

        # Validate text encoding (safe UTF-8 decoding, never executing)
        try:
            code_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                code_text = file_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise FileValidationException(
                    "Uploaded file must be valid UTF-8 plain text. Binary or non-text files are not accepted.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        if not code_text.strip():
            raise FileValidationException(
                "Uploaded file contains only whitespace.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Detect or validate programming language
        resolved_language = language
        if not resolved_language:
            resolved_language = EXTENSION_TO_LANGUAGE.get(ext_lower, ProgrammingLanguage.OTHER)

        clean_requirement_ids = [
            req.strip() for req in (requirement_ids or []) if req and req.strip()
        ]

        submission_id = f"sub-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        submission = CodeSubmissionResponse(
            id=submission_id,
            code=code_text,
            language=resolved_language,
            filename=sanitized_filename,
            requirement_ids=clean_requirement_ids,
            source_type=SubmissionSource.FILE_UPLOAD,
            created_at=now,
            metadata={
                "original_filename": raw_filename,
                "file_size_bytes": file_size,
                "content_type": file.content_type,
            },
        )

        logger.info(
            "Processed safe file upload %s (file=%s, size=%d bytes, language=%s)",
            submission_id,
            sanitized_filename,
            file_size,
            resolved_language.value,
        )
        return await self.repo.save(submission)

    async def get_submission(self, submission_id: str) -> CodeSubmissionResponse:
        """Retrieves a single submission by ID or raises 404."""
        submission = await self.repo.get_by_id(submission_id)
        if not submission:
            raise ResourceNotFoundException("Submission", submission_id)
        return submission

    async def list_submissions(
        self, skip: int = 0, limit: int = 100
    ) -> CodeSubmissionListResponse:
        """Returns paginated submissions."""
        items = await self.repo.list_all(skip=skip, limit=limit)
        total = await self.repo.count()
        return CodeSubmissionListResponse(total=total, items=items)
