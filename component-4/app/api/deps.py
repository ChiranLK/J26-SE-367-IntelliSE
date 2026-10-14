from fastapi import Depends
from app.repositories import (
    BaseSubmissionRepository,
    BaseVerificationRunRepository,
    get_submission_repository,
    get_verification_repository,
)
from app.services.submission_service import SubmissionService
from app.services.verification_service import VerificationService


def get_sub_repo() -> BaseSubmissionRepository:
    """Dependency provider for submission repository."""
    return get_submission_repository()


def get_verif_repo() -> BaseVerificationRunRepository:
    """Dependency provider for verification run repository."""
    return get_verification_repository()


def get_submission_service(
    repo: BaseSubmissionRepository = Depends(get_sub_repo),
) -> SubmissionService:
    """Dependency provider for SubmissionService."""
    return SubmissionService(submission_repo=repo)


def get_verification_service(
    submission_repo: BaseSubmissionRepository = Depends(get_sub_repo),
    verification_repo: BaseVerificationRunRepository = Depends(get_verif_repo),
) -> VerificationService:
    """Dependency provider for VerificationService."""
    return VerificationService(
        submission_repo=submission_repo,
        verification_repo=verification_repo,
    )
