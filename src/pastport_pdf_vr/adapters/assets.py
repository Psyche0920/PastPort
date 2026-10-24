"""Content-addressed local asset storage with atomic, size-bounded registration."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import tempfile
from pathlib import Path
from typing import BinaryIO

from pastport_pdf_vr.domain.models import (
    AssetRef,
    ProjectAssetRef,
    ProjectId,
    RegisteredAsset,
)
from pastport_pdf_vr.ports.assets import AssetStore


class AssetStoreError(OSError):
    """Raised when asset bytes cannot be registered or verified safely."""


class LocalAssetStore(AssetStore):
    """Store immutable content-addressed files under an application-owned directory."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve(strict=True)

    def register_file(
        self,
        project_id: ProjectId,
        source_path: Path,
        media_type: str,
        max_bytes: int,
    ) -> RegisteredAsset:
        if max_bytes < 1:
            raise AssetStoreError("Asset size limit must be positive")
        try:
            descriptor = os.open(source_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as error:
            raise AssetStoreError("Asset source could not be opened safely") from error
        with os.fdopen(descriptor, "rb") as source:
            initial_stat = os.fstat(source.fileno())
            if not stat.S_ISREG(initial_stat.st_mode):
                raise AssetStoreError("Asset source must be a regular file")
            if initial_stat.st_size < 1 or initial_stat.st_size > max_bytes:
                raise AssetStoreError("Asset source is empty or exceeds the configured size limit")
            return self._register_stream(project_id, source, media_type, max_bytes, initial_stat)

    def register_bytes(
        self,
        project_id: ProjectId,
        content: bytes,
        media_type: str,
        max_bytes: int,
    ) -> RegisteredAsset:
        if not content or len(content) > max_bytes:
            raise AssetStoreError("Asset content is empty or exceeds the configured size limit")
        return self._register_stream(project_id, io.BytesIO(content), media_type, max_bytes, None)

    def resolve_path(self, reference: ProjectAssetRef) -> Path:
        expected_resource_id = f"sha256:{reference.asset.sha256}"
        if reference.asset.resource_id != expected_resource_id or reference.asset.version != 1:
            raise AssetStoreError(
                "Asset reference is not a valid local content-addressed reference"
            )
        target = self._path_for_hash(reference.asset.sha256)
        if not target.is_file() or target.is_symlink():
            raise AssetStoreError("Registered asset bytes are missing")
        actual_hash = self._hash_file(target)
        if actual_hash != reference.asset.sha256:
            raise AssetStoreError("Registered asset bytes do not match their content hash")
        return target

    def _register_stream(
        self,
        project_id: ProjectId,
        source: BinaryIO,
        media_type: str,
        max_bytes: int,
        source_stat: os.stat_result | None,
    ) -> RegisteredAsset:
        if max_bytes < 1:
            raise AssetStoreError("Asset size limit must be positive")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".register-", dir=self._root)
        temporary_path = Path(temporary_name)
        byte_length = 0
        digest = hashlib.sha256()
        try:
            with os.fdopen(descriptor, "wb") as destination:
                os.fchmod(destination.fileno(), 0o600)
                while chunk := source.read(1024 * 1024):
                    byte_length += len(chunk)
                    if byte_length > max_bytes:
                        raise AssetStoreError("Asset source exceeds the configured size limit")
                    digest.update(chunk)
                    destination.write(chunk)
                if byte_length < 1:
                    raise AssetStoreError("Asset source is empty")
                destination.flush()
                os.fsync(destination.fileno())
            if byte_length < 1:
                raise AssetStoreError("Asset source is empty")
            if source_stat is not None:
                current_stat = os.fstat(source.fileno())
                if (
                    current_stat.st_ino != source_stat.st_ino
                    or current_stat.st_dev != source_stat.st_dev
                    or current_stat.st_size != source_stat.st_size
                    or current_stat.st_mtime_ns != source_stat.st_mtime_ns
                ):
                    raise AssetStoreError("Asset source changed while it was being registered")
            asset_hash = digest.hexdigest()
            target = self._path_for_hash(asset_hash)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.parent.resolve(strict=True).is_relative_to(self._root):
                raise AssetStoreError("Asset storage path escapes its configured root")
            try:
                os.link(temporary_path, target)
            except FileExistsError:
                if target.is_symlink():
                    raise AssetStoreError(
                        "Existing content-addressed asset is a symbolic link"
                    ) from None
                if self._hash_file(target) != asset_hash:
                    raise AssetStoreError(
                        "Existing content-addressed asset failed verification"
                    ) from None
            asset_ref = AssetRef(resource_id=f"sha256:{asset_hash}", version=1, sha256=asset_hash)
            return RegisteredAsset(
                reference=ProjectAssetRef(project_id=project_id, asset=asset_ref),
                media_type=media_type,
                byte_length=byte_length,
            )
        except AssetStoreError:
            raise
        except OSError as error:
            raise AssetStoreError("Asset registration failed") from error
        finally:
            temporary_path.unlink(missing_ok=True)

    def _path_for_hash(self, asset_hash: str) -> Path:
        return self._root / asset_hash[:2] / asset_hash

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
