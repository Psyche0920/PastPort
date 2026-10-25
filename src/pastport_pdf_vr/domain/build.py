"""Persisted matched-environment generation summary."""

from typing import Literal

from pastport_pdf_vr.domain.models import DomainModel


class BuildSummary(DomainModel):
    project_id: str
    input_binding: str
    mapping_mode: Literal["same_site", "demo_substitution"]
    object_count: int
    anchor_count: int
    gaps: tuple[str, ...]
    status: Literal["completed", "completed_with_gaps"]
