"""Persistent identity allocation boundary."""

from typing import Protocol

from pastport_evidence.domain.recognition import EntityProposal, SceneEntity


class SceneRepository(Protocol):
    def list_entities(self, project_id: str) -> tuple[SceneEntity, ...]: ...

    def resolve_proposals(
        self, project_id: str, binding: str, proposals: tuple[EntityProposal, ...]
    ) -> dict[str, SceneEntity]: ...
