"""Coordinate contracts: image edges, top-left pixels, yaw-zero forward and pitch-up."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from pastport_pdf_vr.domain.models import DomainModel

Finite = Annotated[float, Field(allow_inf_nan=False)]
PositiveSize = Annotated[int, Field(ge=1)]


class PixelPoint(DomainModel):
    x: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class SphericalPoint(DomainModel):
    yaw: Annotated[float, Field(ge=-180, lt=180, allow_inf_nan=False)]
    pitch: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]


class AnchorPosition(DomainModel):
    yaw: Annotated[float, Field(ge=-180, lt=180, allow_inf_nan=False)]
    pitch: Annotated[float, Field(ge=-85, le=85, allow_inf_nan=False)]


class ImageGeometry(DomainModel):
    source_width: PositiveSize
    source_height: PositiveSize
    image_width: Annotated[int, Field(ge=1, le=2048)]
    image_height: Annotated[int, Field(ge=1, le=2048)]

    @model_validator(mode="after")
    def validate_panorama(self) -> ImageGeometry:
        if self.source_width != 2 * self.source_height:
            raise ValueError("Only full 2:1 equirectangular panoramas are supported")
        if self.source_width * self.source_height > 64_000_000:
            raise ValueError("Panorama exceeds the decoded-pixel ceiling")
        return self


class EquirectangularTransform(ImageGeometry):
    kind: Literal["equirectangular"] = "equirectangular"


class CropTransform(ImageGeometry):
    kind: Literal["crop"] = "crop"
    source_x: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    source_y: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    crop_width: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    crop_height: Annotated[float, Field(gt=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def validate_crop(self) -> CropTransform:
        if self.source_x >= self.source_width or self.crop_width > self.source_width:
            raise ValueError("Crop horizontal bounds exceed the panorama")
        if self.source_y + self.crop_height > self.source_height:
            raise ValueError("Crop vertical bounds exceed the panorama")
        return self


class PerspectiveTransform(ImageGeometry):
    kind: Literal["perspective"] = "perspective"
    center_yaw: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
    center_pitch: Annotated[float, Field(ge=-85, le=85, allow_inf_nan=False)]
    horizontal_fov: Annotated[float, Field(ge=5, le=150, allow_inf_nan=False)]
    roll: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] = 0.0


ImageTransform = Annotated[
    EquirectangularTransform | CropTransform | PerspectiveTransform, Field(discriminator="kind")
]
