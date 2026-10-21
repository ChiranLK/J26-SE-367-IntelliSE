"""Request contract for Component 4 to submit a defect report by generation run."""

from typing import Annotated

from pydantic import Field

from intelise_c3.contracts.defect_report import DefectReport
from intelise_c3.domain.generation_context import DomainModel


class C4DefectReportSubmission(DomainModel):
    """C4 names the run; C3 loads the stored manifest and design context itself."""

    generation_run_id: Annotated[
        str,
        Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
    ]
    defect_report: DefectReport
