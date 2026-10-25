"""Typed browser submissions and explicit input-adapter capabilities."""

from typing import Annotated, Literal

from pydantic import Field

from pastport_pdf_vr.domain.models import DomainModel


class InputCapability(DomainModel):
    key: str
    label: str
    category: Literal["document", "scene"]
    status: Literal["supported", "planned", "conversion_required"]
    extensions: tuple[str, ...]
    detail: str


INPUT_CAPABILITIES = (
    InputCapability(
        key="pdf",
        label="匹配 PDF",
        category="document",
        status="supported",
        extensions=(".pdf",),
        detail="读取已确认编号、物件照片及历史对应依据。",
    ),
    InputCapability(
        key="tour_360",
        label="360° 全景导览",
        category="scene",
        status="supported",
        extensions=(".html", ".zip"),
        detail="360 Studio schema 4 静态全景，可上传完整素材文件夹或 ZIP。",
    ),
)


class StudioOptions(DomainModel):
    workflow: Literal["environment_build"] = "environment_build"
    title: Annotated[str, Field(min_length=1, max_length=100)]
    project_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")] | None = None
    document_format: Literal["pdf"] = "pdf"
    scene_format: Literal["tour_360"] = "tour_360"
    # Read older environment-run options without re-enabling legacy workflows.
    mapping_mode: Literal["same_site", "demo_substitution"] = "same_site"
    large_pdf: bool = False
    max_calls: Annotated[int, Field(ge=1, le=100)] = 20
    max_recorded_tokens: Annotated[int, Field(ge=1, le=10_000_000)] = 250_000
    authorize_model: Literal[True]


class StudioJob(DomainModel):
    job_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
    project_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
    title: str
    workflow: Literal["environment_build"] = "environment_build"
    status: Literal["running", "completed", "completed_with_gaps", "failed", "recovery_required"]
    message: str = ""
    stages: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
