"""Coordinate contracts: image edges, top-left pixels, yaw-zero forward and pitch-up."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from pastport_evidence.domain.models import DomainModel


class PixelPoint(DomainModel):
    x: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, allow_inf_nan=False)]
