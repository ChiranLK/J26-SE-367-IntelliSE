import io
import os
import posixpath
import urllib.parse
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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
            test_code=payload.test_code,
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

        # Handle multi-file ZIP project uploads securely
        if ext_lower == ".zip":
            return await self._process_zip_project_upload(
                file_bytes=file_bytes,
                raw_filename=raw_filename,
                sanitized_filename=sanitized_filename,
                language=language,
                requirement_ids=requirement_ids,
            )

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

    async def _process_zip_project_upload(
        self,
        file_bytes: bytes,
        raw_filename: str,
        sanitized_filename: str,
        language: Optional[ProgrammingLanguage] = None,
        requirement_ids: Optional[List[str]] = None,
    ) -> CodeSubmissionResponse:
        """
        Securely handles multi-file Python project ZIP archive uploads.
        Enforces path traversal protection, symlink prohibition, zip-bomb size/count bounds,
        and safe text decoding without executing any code outside sandbox.
        """
        try:
            zip_ref = zipfile.ZipFile(io.BytesIO(file_bytes))
        except (zipfile.BadZipFile, Exception):
            raise FileValidationException(
                "Uploaded file is not a valid ZIP archive or is corrupted.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        infolist = zip_ref.infolist()
        if not infolist:
            raise FileValidationException(
                "Uploaded ZIP archive is empty.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # File count limit (zip bomb defense)
        if len(infolist) > settings.MAX_PROJECT_ZIP_FILES:
            raise FileValidationException(
                f"Project ZIP exceeds maximum allowed file count ({settings.MAX_PROJECT_ZIP_FILES} files). Found {len(infolist)} entries.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Uncompressed size limit (zip bomb defense)
        total_uncompressed = sum(info.file_size for info in infolist)
        if total_uncompressed > settings.MAX_PROJECT_UNCOMPRESSED_BYTES:
            raise FileValidationException(
                f"Project ZIP uncompressed size ({total_uncompressed} bytes) exceeds maximum limit of {settings.MAX_PROJECT_UNCOMPRESSED_BYTES} bytes (10MB).",
                status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413),
            )

        # Compression ratio check (zip bomb defense)
        if len(file_bytes) > 0 and (total_uncompressed / len(file_bytes)) > 100:
            raise FileValidationException(
                "Potential ZIP bomb detected: compression ratio exceeds maximum safety threshold.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ALLOWED_PROJECT_EXTENSIONS = {
            ".py", ".txt", ".md", ".json", ".yml", ".yaml", ".ini", ".cfg", ".toml", ".csv"
        }
        ALLOWED_EXACT_NAMES = {
            "requirements.txt", "pipfile", "dockerfile", "license", "authors", "readme"
        }
        DISALLOWED_DANGEROUS_EXTENSIONS = {
            ".exe", ".dll", ".so", ".dylib", ".bin", ".sh", ".bat", ".cmd", ".pyd", ".pyc", ".pyo"
        }

        project_files: Dict[str, str] = {}

        for info in infolist:
            if info.is_dir() or info.filename.endswith("/"):
                continue

            norm_path = info.filename.replace("\\", "/").strip()

            # Skip macOS metadata or hidden files
            if norm_path.startswith("__MACOSX/") or "/.DS_Store" in norm_path or norm_path == ".DS_Store":
                continue

            # Path Traversal Checks
            if (
                "\x00" in norm_path
                or norm_path.startswith("/")
                or (len(norm_path) > 1 and norm_path[1] == ":")
                or "/../" in f"/{norm_path}/"
                or norm_path.startswith("../")
                or norm_path == ".."
            ):
                raise FileValidationException(
                    f"Path traversal attempt detected in project archive: {info.filename}",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            clean_rel_path = posixpath.normpath(norm_path)
            if clean_rel_path.startswith("../") or clean_rel_path == "..":
                raise FileValidationException(
                    f"Path traversal attempt detected in project archive: {info.filename}",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Symlink check: S_IFLNK is 0o120000
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise FileValidationException(
                    f"Symlinks are prohibited for security: {info.filename}",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Extension validation
            _, file_ext = posixpath.splitext(clean_rel_path)
            file_ext_lower = file_ext.lower()
            base_lower = posixpath.basename(clean_rel_path).lower()

            if file_ext_lower in DISALLOWED_DANGEROUS_EXTENSIONS:
                raise FileValidationException(
                    f"Unsafe executable or binary file type prohibited: '{clean_rel_path}'",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if file_ext_lower not in ALLOWED_PROJECT_EXTENSIONS and base_lower not in ALLOWED_EXACT_NAMES:
                raise FileValidationException(
                    f"File type not permitted in Python project: '{clean_rel_path}'. Allowed types: Python, config, docs, and manifests.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Read and decode text content
            try:
                raw_bytes = zip_ref.read(info)
            except Exception as e:
                raise FileValidationException(
                    f"Failed to read file from ZIP archive: {clean_rel_path}: {e}",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            try:
                text_content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text_content = raw_bytes.decode("utf-8-sig")
                except UnicodeDecodeError:
                    raise FileValidationException(
                        f"File '{clean_rel_path}' is not valid UTF-8 text.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

            project_files[clean_rel_path] = text_content

        python_files = [f for f in project_files.keys() if f.endswith(".py")]
        if not python_files:
            raise FileValidationException(
                "Uploaded ZIP project must contain at least one Python (.py) source file.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Identify tests and entrypoint
        test_files = [
            f for f in python_files
            if posixpath.basename(f).startswith("test_") or "/tests/" in f"/{f}" or "/test/" in f"/{f}"
        ]

        non_test_py = [f for f in python_files if f not in test_files]
        if not non_test_py:
            entrypoint = python_files[0]
        else:
            priority_names = ["main.py", "app.py", "solution.py", "server.py", "index.py", "run.py"]
            entrypoint = None
            for p_name in priority_names:
                for f in non_test_py:
                    if posixpath.basename(f) == p_name:
                        entrypoint = f
                        break
                if entrypoint:
                    break
            if not entrypoint:
                non_test_py.sort(key=lambda x: (x.count("/"), len(x)))
                entrypoint = non_test_py[0]

        primary_test_code = None
        if test_files:
            test_files.sort(key=lambda x: (0 if posixpath.basename(x).startswith("test_") else 1, x.count("/")))
            primary_test_code = project_files[test_files[0]]

        clean_requirement_ids = [
            req.strip() for req in (requirement_ids or []) if req and req.strip()
        ]

        submission_id = f"sub-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        metadata: Dict[str, Any] = {
            "is_multi_file": True,
            "project_files": project_files,
            "file_count": len(project_files),
            "python_file_count": len(python_files),
            "entrypoint": entrypoint,
            "test_files": test_files,
            "has_embedded_tests": len(test_files) > 0,
            "original_filename": raw_filename,
            "file_size_bytes": len(file_bytes),
            "uncompressed_size_bytes": total_uncompressed,
        }

        submission = CodeSubmissionResponse(
            id=submission_id,
            code=project_files[entrypoint],
            language=ProgrammingLanguage.PYTHON,
            filename=sanitized_filename,
            requirement_ids=clean_requirement_ids,
            test_code=primary_test_code,
            source_type=SubmissionSource.FILE_UPLOAD,
            created_at=now,
            metadata=metadata,
        )

        logger.info(
            "Processed safe multi-file ZIP project upload %s (%d files, %d Python files, entrypoint=%s)",
            submission_id,
            len(project_files),
            len(python_files),
            entrypoint,
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
