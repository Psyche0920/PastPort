"""Parse data-only tour exports; imported HTML is never served or executed."""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pastport_matched_environment.application.projection import wrap_yaw
from pastport_matched_environment.domain.geometry import SphericalPoint
from pastport_matched_environment.domain.models import ProcessingLimits, ProjectId
from pastport_matched_environment.domain.tour import ImportedTour, TourLink, TourView
from pastport_matched_environment.ports.assets import AssetStore


class TourImportError(ValueError):
    """A tour export or panorama cannot be safely imported."""


# Vendor source DTOs deliberately tolerate unrelated editing metadata. Only admitted
# fields are translated to strict domain types, and no source scripts are evaluated.
class _VendorModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class _Panorama(_VendorModel):
    data: str


class _Pose(_VendorModel):
    yaw: float = 0.0
    pitch: float = 0.0


class _Link(_Pose):
    type: str
    targetId: str | None = None
    label: str = ""


class _Scene(_VendorModel):
    id: str
    name: str
    panorama: _Panorama
    panoramaRevision: int = 1
    hotspots: list[_Link] = Field(default_factory=list)
    view: _Pose = Field(default_factory=_Pose)


class _Export(_VendorModel):
    schemaVersion: int
    id: str
    firstSceneId: str
    scenes: Annotated[list[_Scene], Field(min_length=1, max_length=100)]


class _DataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.inside = False
        self.found = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == "tour-data":
            if self.found or attributes.get("type") != "application/json":
                raise TourImportError("Duplicate or invalid tour-data script")
            self.inside = self.found = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.inside = False

    def handle_data(self, data: str) -> None:
        if self.inside:
            self.parts.append(data)


class TourImporter:
    def __init__(self, assets: AssetStore) -> None:
        self._assets = assets

    def import_html(
        self, project_id: ProjectId, path: Path, limits: ProcessingLimits
    ) -> ImportedTour:
        registered = self._assets.register_file(
            project_id, path, "text/html", limits.tour_max_expanded_bytes
        )
        try:
            content = self._assets.resolve_path(registered.reference).read_text(encoding="utf-8")
            parser = _DataParser()
            parser.feed(content)
            if not parser.found:
                raise TourImportError("Missing application/json tour-data block")
            data = _Export.model_validate_json("".join(parser.parts))
        except (OSError, UnicodeError, ValidationError, json.JSONDecodeError) as error:
            raise TourImportError("Tour JSON could not be decoded or validated") from error
        if data.schemaVersion not in (3, 4):
            raise TourImportError("Unsupported tour schema version")
        views: list[TourView] = []
        for scene in data.scenes:
            raw = self._read_panorama(scene.panorama.data, path.parent, limits)
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    width, height = image.size
                    if image.format not in ("JPEG", "PNG", "WEBP"):
                        raise TourImportError("Panorama must be JPEG, PNG or WebP")
                    media_type = Image.MIME[image.format]
                    if width != height * 2 or width * height > limits.panorama_max_pixels:
                        raise TourImportError(
                            "Panorama must be full 2:1 and within decoded-pixel limits"
                        )
                    image.verify()
            except (OSError, Image.DecompressionBombError) as error:
                raise TourImportError("Panorama image could not be verified") from error
            media = self._assets.register_bytes(
                project_id, raw, media_type, limits.panorama_max_bytes
            )
            links = []
            for link in scene.hotspots:
                if link.type != "scene":
                    continue
                if not link.targetId:
                    raise TourImportError("Scene navigation is missing its target")
                links.append(
                    TourLink(
                        target_view_id=link.targetId,
                        label=link.label,
                        position=SphericalPoint(yaw=wrap_yaw(link.yaw), pitch=link.pitch),
                    )
                )
            views.append(
                TourView(
                    view_id=scene.id,
                    label=scene.name,
                    panorama=media.reference,
                    revision=scene.panoramaRevision,
                    width=width,
                    height=height,
                    initial_position=SphericalPoint(
                        yaw=wrap_yaw(scene.view.yaw), pitch=scene.view.pitch
                    ),
                    links=tuple(links),
                )
            )
        return ImportedTour(
            tour_id=data.id,
            source=registered.reference,
            schema_version=data.schemaVersion,
            first_view_id=data.firstSceneId,
            views=tuple(views),
        )

    @staticmethod
    def _read_panorama(value: str, root: Path, limits: ProcessingLimits) -> bytes:
        if value.startswith("data:"):
            match = re.fullmatch(r"data:image/(?:jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)", value)
            if not match or len(match[1]) > limits.panorama_max_bytes * 4 // 3 + 4096:
                raise TourImportError("Panorama data URI is invalid or oversized")
            try:
                result = base64.b64decode(re.sub(r"\s+", "", match[1]), validate=True)
            except (ValueError, binascii.Error) as error:
                raise TourImportError("Panorama base64 is invalid") from error
        else:
            if ":" in value or "\\" in value or Path(value).is_absolute():
                raise TourImportError("Only local relative panorama assets are supported")
            target = (root / value).resolve(strict=True)
            if not target.is_relative_to(root.resolve(strict=True)) or not target.is_file():
                raise TourImportError("Panorama path escapes the tour directory")
            if target.stat().st_size > limits.panorama_max_bytes:
                raise TourImportError("Panorama encoded size exceeds its limit")
            result = target.read_bytes()
        if not result or len(result) > limits.panorama_max_bytes:
            raise TourImportError("Panorama is empty or exceeds its encoded-size limit")
        return result
