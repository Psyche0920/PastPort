"""Durable identity and validated model-response receipts for scene recognition."""

from typing import Protocol

from pastport_pdf_vr.domain.recognition import EntityProposal, SceneEntity, SceneInspection


class SceneRepository(Protocol):
    def list_entities(self, project_id: str) -> tuple[SceneEntity, ...]: ...
    def resolve_proposals(
        self, project_id: str, binding: str, proposals: tuple[EntityProposal, ...]
    ) -> dict[str, SceneEntity]: ...
    def load_inspection(self, project_id: str, binding: str) -> SceneInspection | None: ...
    def save_inspection(self, project_id: str, binding: str, result: SceneInspection) -> None: ...
