"""Explicit synthetic replay imports accepted demo proposals; it performs no inference."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from pastport_pdf_vr.adapters.editorial import SQLiteEditorialRepository
from pastport_pdf_vr.adapters.legacy_replay import LegacyMaterials
from pastport_pdf_vr.domain.editorial import PreviewAnchor, PreviewObject, TextEdit
from pastport_pdf_vr.domain.evidence import DisplayCopy
from pastport_pdf_vr.domain.geometry import AnchorPosition
from pastport_pdf_vr.domain.recognition import SceneEntity
from pastport_pdf_vr.domain.tour import ImportedTour


class ReplayLocation(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    object_id: Annotated[int, Field(ge=1)]
    modern_name: str
    historical_id: str | None = None
    scene_id: str
    yaw: float
    pitch: float
    panorama_sha256: str
    panorama_hash_basis: str
    basis: str


class ReplayReport(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    input_html_sha256: str
    located: Annotated[list[ReplayLocation], Field(max_length=2400)]


class ReplayImporter:
    def __init__(self, repository: SQLiteEditorialRepository) -> None:
        self._repository = repository

    def import_report(
        self, project: str, tour: ImportedTour, path: Path, materials: LegacyMaterials | None = None
    ) -> int:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Replay report exceeds its byte limit")
        data = path.read_bytes()
        report = ReplayReport.model_validate_json(data)
        if report.input_html_sha256 != tour.source.asset.sha256:
            raise ValueError("Replay report is bound to different source tour bytes")
        views = {view.view_id: view for view in tour.views}
        material_by_id = (
            {item.object_number: item for item in materials.objects} if materials else {}
        )
        objects: dict[int, PreviewObject] = {}
        anchors = []
        for location in report.located:
            if location.scene_id not in views:
                raise ValueError("Replay location references a missing tour view")
            view = views[location.scene_id]
            object_id = f"demo-object:{location.object_id:02d}"
            material = material_by_id.get(location.object_id)
            subject = material.historical_subject_id if material else location.historical_id
            candidate = PreviewObject(
                entity=SceneEntity(
                    object_id=object_id,
                    display_number=location.object_id,
                    label=location.modern_name,
                    category="demo target",
                    distinguishing_features=(location.basis,),
                ),
                historical_subject_id=subject,
                draft=DisplayCopy(
                    subject_id=subject,
                    version=1,
                    introduction=material.ai_draft,
                    background=material.background,
                )
                if subject and material and material.ai_draft
                else None,
                replay_evidence=material.evidence if material else None,
                evidence_refs=(f"legacy-source:{subject}",)
                if material and material.evidence
                else (),
            )
            if location.object_id in objects and (
                objects[location.object_id].historical_subject_id != candidate.historical_subject_id
                or objects[location.object_id].entity.label != candidate.entity.label
            ):
                raise ValueError("Replay report assigns conflicting object identities")
            objects.setdefault(location.object_id, candidate)
            # The source HTML hash above binds original data-URI bytes. The imported
            # tour now binds decoded panorama bytes; never reinterpret the old hash as JPEG hash.
            anchors.append(
                PreviewAnchor(
                    object_id=object_id,
                    view_id=view.view_id,
                    panorama=view.panorama,
                    panorama_revision=view.revision,
                    position=AnchorPosition(yaw=location.yaw, pitch=location.pitch),
                )
            )
        material_bytes = materials.model_dump_json().encode() if materials else b""
        binding = (
            "replay:"
            + hashlib.sha256(data + tour.source.asset.sha256.encode() + material_bytes).hexdigest()
        )
        self._repository.publish_proposals(
            project, binding, "synthetic_replay", tuple(objects.values()), tuple(anchors)
        )
        current = {
            row.object.entity.display_number: row
            for row in self._repository.snapshot(project).objects
        }
        for number, row in current.items():
            material = material_by_id.get(number)
            if (
                material
                and material.human_override is not None
                and material.historical_subject_id
                and row.version == 0
            ):
                self._repository.save_text(
                    project,
                    TextEdit(
                        operation_id="legacy-human:"
                        + hashlib.sha256((binding + str(number)).encode()).hexdigest(),
                        object_id=row.object.entity.object_id,
                        historical_subject_id=material.historical_subject_id,
                        expected_version=0,
                        introduction=material.human_override,
                        background=material.background,
                    ),
                )
        return self._repository.snapshot(project).revision
