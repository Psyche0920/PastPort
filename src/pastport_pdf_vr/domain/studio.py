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
        key="site_photos",
        label="现场多角度照片",
        category="scene",
        status="supported",
        extensions=(".jpg", ".jpeg", ".png", ".webp"),
        detail="第一阶段独立接收 1-100 张照片，统一物品身份并导出替代映射 PDF；不要求 VR。",
    ),
    InputCapability(
        key="pdf",
        label="PDF 文档",
        category="document",
        status="supported",
        extensions=(".pdf",),
        detail="提取原文、页面图片和出处。",
    ),
    InputCapability(
        key="idml_links",
        label="IDML + Links",
        category="document",
        status="planned",
        extensions=(".idml",),
        detail="官方资料含排版文件及独立图片；解析适配尚未接入。",
    ),
    InputCapability(
        key="indd",
        label="InDesign 原文件",
        category="document",
        status="conversion_required",
        extensions=(".indd",),
        detail="请先用 InDesign 导出为 IDML 或 PDF。",
    ),
    InputCapability(
        key="tour_360",
        label="360° 全景导览",
        category="scene",
        status="supported",
        extensions=(".html", ".zip"),
        detail="当前 360 Studio 导出的 schema 3/4 HTML，可连同素材文件夹或 ZIP 上传。",
    ),
    InputCapability(
        key="model_3d",
        label="3D 场景 / 模型",
        category="scene",
        status="planned",
        extensions=(".glb", ".gltf"),
        detail="保留独立适配接口；3D 坐标、参考视图和查看器尚未实现，不作为全景处理。",
    ),
)


class StudioOptions(DomainModel):
    workflow: Literal["vr_build", "photo_mapping", "environment_build"] = "vr_build"
    title: Annotated[str, Field(min_length=1, max_length=100)]
    project_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")] | None = None
    document_format: Literal["pdf", "idml_links", "indd"] = "pdf"
    scene_format: Literal["tour_360", "model_3d"] = "tour_360"
    mapping_mode: Literal["same_site", "demo_substitution"] = "same_site"
    large_pdf: bool = False
    max_calls: Annotated[int, Field(ge=1, le=100)] = 20
    max_recorded_tokens: Annotated[int, Field(ge=1, le=10_000_000)] = 250_000
    authorize_model: Literal[True]


class StudioJob(DomainModel):
    job_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
    project_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
    title: str
    workflow: Literal["vr_build", "photo_mapping", "environment_build"] = "vr_build"
    status: Literal["running", "completed", "completed_with_gaps", "failed", "recovery_required"]
    message: str = ""
    stages: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
