"""Component 4 intake: submit a defect report for a stored generation run.

C4 does not hold the C3 manifest or DesignContext, so it sends only the run ID and
the defect report. C3 loads the verified manifest (traceability store), finds the
run workspace, and loads the digest-checked DesignContext, then delegates to the
unchanged ``ScopedRegenerationService``. Every existing check still applies.
"""

from pathlib import Path

from fastapi import APIRouter, Request, status

from intelise_c3.api.routes.scoped_regeneration import _ERRORS, _service
from intelise_c3.contracts.c4_intake import C4DefectReportSubmission
from intelise_c3.contracts.scoped_regeneration import ScopedRegenerationRequest
from intelise_c3.core.errors import ApplicationError, ErrorDetail, ErrorResponse
from intelise_c3.domain.scoped_regeneration import C4RetestHandoff, RegenerationStatus
from intelise_c3.services.design_context_store import DesignContextStore
from intelise_c3.traceability.store import SQLiteTraceabilityStore

router = APIRouter(prefix="/c4", tags=["c4-intake"])


def _fail(code: str, field: str, message: str, status_code: int) -> ApplicationError:
    return ApplicationError(
        [ErrorDetail(code=code, field=field, message=message)], status_code=status_code
    )


def _find_workspace(root: Path, run_id: str) -> str:
    """Locate the run workspace (one or two directories deep) holding its manifest."""
    resolved_root = root.resolve()
    matches = sorted(
        {
            path.resolve()
            for pattern in (f"*/{run_id}", f"*/*/{run_id}")
            for path in resolved_root.glob(pattern)
            if path.is_dir() and (path / "artifact-manifest.json").is_file()
        }
    )
    matches = [path for path in matches if path.is_relative_to(resolved_root)]
    if not matches:
        raise _fail(
            "GENERATION_WORKSPACE_NOT_FOUND",
            "generation_run_id",
            "No workspace with a manifest exists for this generation run.",
            status.HTTP_404_NOT_FOUND,
        )
    if len(matches) > 1:
        raise _fail(
            "GENERATION_WORKSPACE_AMBIGUOUS",
            "generation_run_id",
            "More than one workspace matches this generation run.",
            status.HTTP_409_CONFLICT,
        )
    return matches[0].relative_to(resolved_root).as_posix()


@router.post(
    "/defect-reports",
    response_model=C4RetestHandoff,
    responses={
        **_ERRORS,
        404: {"model": ErrorResponse, "description": "Unknown generation run or workspace."},
        409: {
            "model": ErrorResponse,
            "description": (
                "Stale or mismatched report/run, unpersisted design context, or the "
                "regeneration ended REVIEW_REQUIRED or FAILED (no handoff exists)."
            ),
        },
    },
    summary="Submit a C4 defect report for a stored generation run",
)
async def submit_defect_report(
    payload: C4DefectReportSubmission,
    request: Request,
) -> C4RetestHandoff:
    """Run Trigger C and return the PENDING re-test handoff; never claims a repair."""
    report = payload.defect_report
    if report.source_generation_run_id != payload.generation_run_id:
        raise _fail(
            "DEFECT_REPORT_RUN_MISMATCH",
            "defect_report.source_generation_run_id",
            "The defect report names a different generation run than the request.",
            status.HTTP_409_CONFLICT,
        )
    settings = request.app.state.settings
    found = SQLiteTraceabilityStore(settings.traceability_store_path).find_by_run_id(
        payload.generation_run_id
    )
    if found is None:
        raise _fail(
            "GENERATION_RUN_NOT_FOUND",
            "generation_run_id",
            "No traceability graph is stored for this generation run.",
            status.HTTP_404_NOT_FOUND,
        )
    _graph_id, _version, manifest = found
    workspace_relative_path = _find_workspace(
        settings.generated_workspace_root, payload.generation_run_id
    )
    design_context = DesignContextStore.from_settings(settings).load(
        manifest.run_evidence.input_hashes.design_context_sha256
    )
    result = await _service(request, with_model=True).regenerate(
        ScopedRegenerationRequest(
            defect_report=report,
            manifest=manifest,
            workspace_relative_path=workspace_relative_path,
            design_context=design_context,
        )
    )
    if (
        result.status is not RegenerationStatus.PATCHED_PENDING_INDEPENDENT_RETEST
        or result.c4_retest_handoff is None
    ):
        action = (
            result.escalation.required_action
            if result.escalation is not None
            else "A researcher must review the defect report."
        )
        errors = [
            ErrorDetail(
                code=f"REGENERATION_{result.status.value}",
                field="defect_report",
                message=f"{code.value}: {action}",
            )
            for code in result.reason_codes
        ] or [
            ErrorDetail(
                code=f"REGENERATION_{result.status.value}",
                field="defect_report",
                message=action,
            )
        ]
        raise ApplicationError(errors, status_code=status.HTTP_409_CONFLICT)
    return result.c4_retest_handoff
