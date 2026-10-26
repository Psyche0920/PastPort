"""Asset storage contract used by application services."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pastport_matched_environment.domain.models import ProjectAssetRef, ProjectId, RegisteredAsset


class AssetStore(Protocol):
    """Register immutable bytes and resolve only previously registered project refs."""

    def register_file(
        self,
        project_id: ProjectId,
        source_path: Path,
        media_type: str,
        max_bytes: int,
    ) -> RegisteredAsset: ...

    def register_bytes(
        self,
        project_id: ProjectId,
        content: bytes,
        media_type: str,
        max_bytes: int,
    ) -> RegisteredAsset: ...

    def resolve_path(self, reference: ProjectAssetRef) -> Path: ...
