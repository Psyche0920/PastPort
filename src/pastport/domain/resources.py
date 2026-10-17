"""Resource identities and local registrations, independent of provider or filesystem APIs."""

from dataclasses import dataclass
from typing import Literal, Self

from pydantic import model_validator

from pastport.domain.common import Contract, Identifier, Sha256, Text
from pastport.domain.packages import MediaEntry

ResourceKind = Literal["source", "asset"]
MediaType = Literal[
    "image/svg+xml", "image/png", "image/jpeg", "image/webp", "application/octet-stream"
]


class ResourceReference(Contract):
    project_id: Identifier
    resource_id: Identifier
    kind: ResourceKind
    sha256: Sha256
    version: Identifier | None = None
    source_uri: Text | None = None


@dataclass(frozen=True, slots=True)
class ResourceData:
    reference: ResourceReference
    content: bytes
    media_type: MediaType


class RegisteredAsset(Contract):
    project_id: Identifier
    asset_id: Identifier
    version: Identifier
    sha256: Sha256
    relative_path: Text
    media_type: Literal["image/svg+xml", "image/png", "image/jpeg", "image/webp"]

    @model_validator(mode="after")
    def safe_path(self) -> Self:
        MediaEntry(asset_id=self.asset_id, sha256=self.sha256, relative_path=self.relative_path)
        return self


class RegisteredSource(Contract):
    project_id: Identifier
    source_id: Identifier
    version: Identifier
    sha256: Sha256
    uri: Text
    relative_path: Text

    @model_validator(mode="after")
    def safe_path(self) -> Self:
        MediaEntry(asset_id=self.source_id, sha256=self.sha256, relative_path=self.relative_path)
        return self


class ResourceCatalog(Contract):
    sources: tuple[RegisteredSource, ...] = ()
    assets: tuple[RegisteredAsset, ...]

    @model_validator(mode="after")
    def unique_assets(self) -> Self:
        keys = [(item.project_id, item.asset_id, item.sha256) for item in self.assets]
        if len(keys) != len(set(keys)):
            raise ValueError("Asset registrations must have unique project, identity and hash")
        source_keys = [
            (item.project_id, item.source_id, item.version, item.sha256) for item in self.sources
        ]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("Source registrations must be unique")
        return self
