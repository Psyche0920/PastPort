"""Explicit local asset catalog and source URI adapter, bounded to one configured directory."""

from pathlib import Path

from pydantic import ValidationError

from pastport.adapters.package_files import LocalPackageFileReader
from pastport.application.models import ServiceError
from pastport.domain.package_loading import PackageLoadError
from pastport.domain.resources import ResourceCatalog, ResourceData, ResourceReference


class LocalResourceReader:
    def __init__(self, directory: Path, *, fixture_projects: bool = False) -> None:
        self.directory = directory.resolve()
        self.fixture_projects = fixture_projects
        self.files = LocalPackageFileReader()

    def file(self, relative_path: str, maximum_bytes: int) -> bytes:
        target = self.directory / relative_path
        if (
            Path(relative_path).is_absolute()
            or any(part in ("", ".", "..") for part in relative_path.split("/"))
            or "\\" in relative_path
            or ":" in relative_path
            or "%" in relative_path
            or not target.resolve().is_relative_to(self.directory)
            or target.is_symlink()
            or any(
                parent.is_symlink()
                for parent in target.parents
                if parent.is_relative_to(self.directory)
            )
        ):
            raise ServiceError(
                "RESOURCE_PATH_INVALID", "Resource path is outside the registered scope"
            )
        try:
            return self.files.read(target, maximum_bytes)
        except PackageLoadError as error:
            code = (
                "RESOURCE_TOO_LARGE"
                if error.code == "RUNTIME_PACKAGE_TOO_LARGE"
                else "RESOURCE_UNAVAILABLE"
            )
            raise ServiceError(code, "Registered local resource cannot be read", 503) from error

    def read(self, reference: ResourceReference, maximum_bytes: int) -> ResourceData:
        try:
            catalog = ResourceCatalog.model_validate_json(self.file("resources.json", 1024 * 1024))
        except ValidationError as error:
            raise ServiceError(
                "RESOURCE_CATALOG_INVALID", "Resource catalog failed validation"
            ) from error
        if reference.kind == "source":
            source = next(
                (
                    item
                    for item in catalog.sources
                    if (
                        item.project_id == reference.project_id
                        or self.fixture_projects
                        and item.project_id == "fixture-project"
                    )
                    and item.source_id == reference.resource_id
                    and item.version == reference.version
                    and item.sha256 == reference.sha256
                    and item.uri == reference.source_uri
                ),
                None,
            )
            if source is None:
                raise ServiceError(
                    "RESOURCE_NOT_REGISTERED",
                    "Source identity and version are not registered for this project",
                )
            return ResourceData(
                reference,
                self.file(source.relative_path, maximum_bytes),
                "application/octet-stream",
            )
        candidates = [
            item
            for item in catalog.assets
            if item.project_id == reference.project_id
            or (self.fixture_projects and item.project_id == "fixture-project")
        ]
        asset = next(
            (
                item
                for item in candidates
                if item.asset_id == reference.resource_id
                and item.sha256 == reference.sha256
                and (reference.version is None or item.version == reference.version)
            ),
            None,
        )
        if asset is None:
            raise ServiceError(
                "RESOURCE_NOT_REGISTERED",
                "Asset identity, version and hash are not registered for this project",
            )
        return ResourceData(
            reference, self.file(asset.relative_path, maximum_bytes), asset.media_type
        )
