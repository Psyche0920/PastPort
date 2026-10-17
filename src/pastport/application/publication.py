"""Stage durable immutable files, then atomically publish their recorded identity."""

import hashlib
import os
import shutil
from pathlib import Path
from uuid import uuid4

from pastport.application.models import RunRecord, ServiceError
from pastport.application.package_loader import RuntimePackageLoader
from pastport.application.reliability import ReleaseFile, ReleaseManifest, ReleaseRecord
from pastport.application.resources import VerifiedResourceReader
from pastport.domain.common import CanonicalSerializer
from pastport.domain.package_loading import PackageLoadError
from pastport.domain.packages import RuntimePackage
from pastport.domain.resources import ResourceReference
from pastport.ports.editorial import EditorialRepository
from pastport.ports.resources import ResourceReader


class PublicationService:
    def __init__(
        self,
        database: EditorialRepository,
        directory: Path,
        resources: ResourceReader,
        package_loader: RuntimePackageLoader,
    ) -> None:
        self.database = database
        self.directory = directory
        self.resources = VerifiedResourceReader(resources)
        self.package_loader = package_loader

    @staticmethod
    def sync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def verify(
        directory: Path, release: ReleaseRecord, package_loader: RuntimePackageLoader
    ) -> None:
        if CanonicalSerializer.digest(release.manifest) != release.manifest_sha256:
            raise ServiceError("RELEASE_CHANGED", "Recorded manifest failed its content hash")
        manifest = directory / "manifest.json"
        if directory.is_symlink() or manifest.is_symlink():
            raise ServiceError("RELEASE_PATH_INVALID", "Release metadata cannot be a symlink")
        try:
            manifest_bytes = package_loader.reader.read(manifest, package_loader.maximum_bytes)
            if hashlib.sha256(manifest_bytes).hexdigest() != release.manifest_sha256:
                raise ServiceError("RELEASE_CHANGED", "Immutable release manifest failed its hash")
            package_bytes: bytes | None = None
            for item in release.manifest.files:
                path = directory / item.relative_path
                if (
                    path.is_symlink()
                    or not path.resolve().is_relative_to(directory.resolve())
                    or any(
                        parent.is_symlink() for parent in path.parents if parent != directory.parent
                    )
                ):
                    raise ServiceError(
                        "RELEASE_PATH_INVALID",
                        "Release files cannot traverse symlinks or escape their directory",
                    )
                maximum_bytes = (
                    package_loader.maximum_bytes
                    if item.relative_path == "package.json"
                    else 20 * 1024 * 1024
                )
                content = package_loader.reader.read(path, maximum_bytes)
                if hashlib.sha256(content).hexdigest() != item.sha256:
                    raise ServiceError(
                        "RELEASE_CHANGED", "Immutable release file failed its content hash"
                    )
                if item.relative_path == "package.json":
                    package_bytes = content
            if package_bytes is None:
                raise ServiceError(
                    "RELEASE_CHANGED", "Release manifest is missing its runtime package"
                )
            # Validate exactly the same bytes that passed release-integrity checking.
            package_loader.load_bytes(package_bytes, release.manifest.runtime_ref)
        except PackageLoadError as error:
            raise ServiceError(error.code, str(error)) from error

    def stage(
        self, run: RunRecord, package: RuntimePackage, decision_ids: tuple[str, ...]
    ) -> ReleaseRecord:
        if run.environment != "test" or run.state.runtime_ref is None:
            raise ServiceError("PUBLICATION_NOT_READY", "Only private test publication is enabled")
        if (
            package.project_id != run.state.project_id
            or CanonicalSerializer.digest(package) != run.state.runtime_ref.sha256
        ):
            raise ServiceError(
                "RELEASE_STALE", "Runtime package does not match its frozen reference"
            )
        release_id = "release-" + run.state.run_id
        if run.control.release_generation:
            release_id += "-review-" + str(run.control.release_generation)
        manifest = ReleaseManifest(
            project_id=run.state.project_id,
            run_id=run.state.run_id,
            release_id=release_id,
            environment=run.environment,
            runtime_ref=run.state.runtime_ref,
            files=(
                ReleaseFile(
                    relative_path="package.json", sha256=CanonicalSerializer.digest(package)
                ),
                *(
                    ReleaseFile(relative_path=item.relative_path, sha256=item.sha256)
                    for item in package.media_manifest
                ),
            ),
            review_decision_ids=decision_ids,
        )
        paths = [item.relative_path for item in manifest.files] + ["manifest.json"]
        if len(paths) != len(set(paths)) or any(
            Path(path).is_absolute() or ".." in Path(path).parts for path in paths
        ):
            raise ServiceError(
                "RELEASE_PATH_INVALID", "Release file paths must be unique and local"
            )
        release = ReleaseRecord(
            manifest=manifest,
            manifest_sha256=CanonicalSerializer.digest(manifest),
            expected_old_release=run.expected_old_release,
        )
        self.database.prepare_release(release)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.sync_directory(self.directory.parent)
        destination = self.directory / run.state.project_id / release_id
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.sync_directory(self.directory)
            temporary = destination.parent / (".pending-" + str(uuid4()))
            temporary.mkdir()
            try:
                self.write(temporary / "package.json", CanonicalSerializer.encode(package))
                for item in package.media_manifest:
                    self.write(
                        temporary / item.relative_path,
                        self.resources.read(
                            ResourceReference(
                                project_id=run.state.project_id,
                                resource_id=item.asset_id,
                                kind="asset",
                                sha256=item.sha256,
                            ),
                            20 * 1024 * 1024,
                        ).content,
                    )
                self.write(temporary / "manifest.json", CanonicalSerializer.encode(manifest))
                self.verify(temporary, release, self.package_loader)
                directories = sorted(
                    (path for path in temporary.rglob("*") if path.is_dir()),
                    key=lambda path: len(path.parts),
                    reverse=True,
                )
                for directory in (*directories, temporary):
                    self.sync_directory(directory)
                os.replace(temporary, destination)
                self.sync_directory(destination.parent)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        self.verify(destination, release, self.package_loader)
        return release
