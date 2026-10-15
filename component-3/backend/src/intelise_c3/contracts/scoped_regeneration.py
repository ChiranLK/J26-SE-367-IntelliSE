"""API contract for impact selection and scoped regeneration."""

from typing import Annotated

from pydantic import Field

from intelise_c3.contracts.defect_report import DefectReport
from intelise_c3.domain.design_context import DesignContext
from intelise_c3.domain.generation import GenerationManifest
from intelise_c3.domain.generation_context import DomainModel


class ScopedRegenerationRequest(DomainModel):
    """Everything needed to verify one source run and act on one defect report."""

    defect_report: DefectReport
    manifest: GenerationManifest
    workspace_relative_path: Annotated[str, Field(min_length=1, max_length=300)]
    design_context: DesignContext
