from fastapi import Depends
from app.repositories import (
    BaseRepairRepository,
    BaseSubmissionRepository,
    BaseTestSuiteRepository,
    BaseVerificationRunRepository,
    get_repair_repository,
    get_submission_repository,
    get_test_suite_repository,
    get_verification_repository,
)
from app.services.defect_resolution_service import DefectResolutionService
from app.services.repair_service import RepairService
from app.services.submission_service import SubmissionService
from app.services.verification_service import VerificationService


def get_sub_repo() -> BaseSubmissionRepository:
    """Dependency provider for submission repository."""
    return get_submission_repository()


def get_verif_repo() -> BaseVerificationRunRepository:
    """Dependency provider for verification run repository."""
    return get_verification_repository()


def get_repair_repo() -> BaseRepairRepository:
    """Dependency provider for repair attempt repository."""
    return get_repair_repository()


def get_test_suite_repo() -> BaseTestSuiteRepository:
    """Dependency provider for trusted test suite repository."""
    return get_test_suite_repository()


def get_submission_service(
    repo: BaseSubmissionRepository = Depends(get_sub_repo),
) -> SubmissionService:
    """Dependency provider for SubmissionService."""
    return SubmissionService(submission_repo=repo)


def get_verification_service(
    submission_repo: BaseSubmissionRepository = Depends(get_sub_repo),
    verification_repo: BaseVerificationRunRepository = Depends(get_verif_repo),
    test_suite_repo: BaseTestSuiteRepository = Depends(get_test_suite_repo),
) -> VerificationService:
    """Dependency provider for VerificationService."""
    return VerificationService(
        submission_repo=submission_repo,
        verification_repo=verification_repo,
        test_suite_repo=test_suite_repo,
    )


def get_defect_resolution_service() -> DefectResolutionService:
    """Dependency provider for DefectResolutionService."""
    return DefectResolutionService()


def get_repair_service(
    repair_repo: BaseRepairRepository = Depends(get_repair_repo),
    submission_repo: BaseSubmissionRepository = Depends(get_sub_repo),
    verification_repo: BaseVerificationRunRepository = Depends(get_verif_repo),
    verification_service: VerificationService = Depends(get_verification_service),
    defect_resolution_service: DefectResolutionService = Depends(get_defect_resolution_service),
    test_suite_repo: BaseTestSuiteRepository = Depends(get_test_suite_repo),
) -> RepairService:
    """Dependency provider for RepairService."""
    return RepairService(
        repair_repo=repair_repo,
        submission_repo=submission_repo,
        verification_repo=verification_repo,
        verification_service=verification_service,
        defect_resolution_service=defect_resolution_service,
        test_suite_repo=test_suite_repo,
    )

