"""Portable matched-VR snapshot; exports live review content without copying credentials."""

import hashlib
import shutil
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pastport_matched_environment.application.shared_content import SharedContentAuthority
from pastport_matched_environment.domain.models import DomainModel


class VRExportFile(DomainModel):
    path: str
    sha256: str
    size_bytes: int


class MatchedVRManifest(DomainModel):
    schema_version: Literal["pastport.matched-vr/1.0"] = "pastport.matched-vr/1.0"
    source_pdf_sha256: str
    import_manifest_sha256: str
    files: tuple[VRExportFile, ...]
    historical_approval: Literal[False] = False


class MatchedVRExporter:
    @staticmethod
    def digest(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def export(self, source: Path, archive: Path) -> MatchedVRManifest:
        root = source.resolve(strict=True)
        if source.is_symlink() or archive.exists():
            raise ValueError("Use a regular source and a new archive path")
        required = ("source.pdf", "mapping-demo.pdf", "import-manifest.json", "vr_trial/index.html")
        paths = [root / name for name in required]
        paths.extend(path for path in (root / "media").rglob("*") if path.is_file())
        if any(path.is_symlink() or not path.is_file() for path in paths):
            raise ValueError("Matched VR data is incomplete or contains links")
        if len(paths) > 5000 or sum(path.stat().st_size for path in paths) > 2 * 1024**3:
            raise ValueError("Matched VR exceeds its export profile")
        database = root / "pastport_matching.sqlite3"
        with TemporaryDirectory(prefix="pastport-vr-export-") as temporary:
            staging = Path(temporary)
            snapshot = staging / "pastport_matching.sqlite3"
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
                with closing(sqlite3.connect(snapshot)) as destination:
                    db.backup(destination)
            SharedContentAuthority(root).snapshot_content(snapshot)
            entries = []
            for path in paths:
                relative = path.relative_to(root)
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                before = self.digest(path)
                shutil.copyfile(path, target)
                if self.digest(target) != before or self.digest(path) != before:
                    raise ValueError("Matched VR changed during export")
                entries.append(
                    VRExportFile(
                        path=relative.as_posix(), sha256=before, size_bytes=target.stat().st_size
                    )
                )
            entries.append(
                VRExportFile(
                    path="pastport_matching.sqlite3",
                    sha256=self.digest(snapshot),
                    size_bytes=snapshot.stat().st_size,
                )
            )
            manifest = MatchedVRManifest(
                source_pdf_sha256=self.digest(staging / "source.pdf"),
                import_manifest_sha256=self.digest(staging / "import-manifest.json"),
                files=tuple(entries),
            )
            archive.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
                    for entry in entries:
                        bundle.write(staging / entry.path, entry.path)
                    bundle.writestr("matched-vr.json", manifest.model_dump_json(indent=2))
            except (OSError, ValueError):
                archive.unlink(missing_ok=True)
                raise
            return manifest
