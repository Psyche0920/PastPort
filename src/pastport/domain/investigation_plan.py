"""Bounded Story-owned investigation designs, validated before local preparation."""

import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import Contract, Identifier, Sha256, unique
from pastport.domain.gameplay_preparation import LocalizedCopy

ObjectNumber = Annotated[int, Field(ge=1, le=10000)]
PatternId = Annotated[str, Field(pattern=r"^[a-z0-9-]{1,64}$")]
ImagePath = Annotated[str, Field(pattern=r"^assets/[a-zA-Z0-9_./-]+\.(svg|png|jpg|jpeg|webp)$")]
Coordinate = Annotated[int, Field(ge=0, le=10000)]
Region = tuple[Coordinate, Coordinate, Coordinate, Coordinate]


class InvestigationImage(Contract):
    path: ImagePath
    sha256: Sha256
    content_kind: Literal["original_fiction", "source_attributed"]
    source_claim_ids: tuple[Identifier, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def provenance(self) -> Self:
        if ".." in self.path.split("/"):
            raise ValueError("Image path escapes the asset root")
        if (self.content_kind == "original_fiction") != (not self.source_claim_ids):
            raise ValueError("Image source attribution differs from its provenance")
        unique(self.source_claim_ids, "image source claims")
        return self


class InvestigationCopy(Contract):
    prompt: LocalizedCopy
    success: LocalizedCopy
    content_kind: Literal["original_fiction", "source_attributed"]


class ImageDifference(Contract):
    id: PatternId
    left: Region
    right: Region
    label: LocalizedCopy

    @model_validator(mode="after")
    def inside_image(self) -> Self:
        for x, y, width, height in (self.left, self.right):
            if width == 0 or height == 0 or x + width > 10000 or y + height > 10000:
                raise ValueError("Difference region is outside its image")
        return self


class DifferenceDesign(InvestigationCopy):
    kind: Literal["spot-difference"]
    left_image: ImagePath
    right_image: ImagePath
    differences: tuple[ImageDifference, ...] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def distinct_differences(self) -> Self:
        unique((item.id for item in self.differences), "image differences")
        return self


class TimelineCard(Contract):
    id: PatternId
    text: LocalizedCopy
    target_slot: PatternId


class TimelineSlot(Contract):
    id: PatternId
    label: LocalizedCopy


class TimelineDesign(InvestigationCopy):
    kind: Literal["timeline"]
    cards: tuple[TimelineCard, ...] = Field(min_length=1, max_length=12)
    slots: tuple[TimelineSlot, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def permutation(self) -> Self:
        unique((item.id for item in self.cards), "timeline cards")
        unique((item.id for item in self.slots), "timeline slots")
        if len(self.cards) != len(self.slots) or {i.target_slot for i in self.cards} != {
            i.id for i in self.slots
        }:
            raise ValueError("Timeline cards need a complete slot permutation")
        return self


class PuzzleImages(Contract):
    zh: ImagePath | None = None
    en: ImagePath
    tr: ImagePath | None = None


class PuzzlePiece(Contract):
    id: PatternId
    target_slot: Annotated[int, Field(ge=0, le=11)]


class ImagePuzzleDesign(InvestigationCopy):
    kind: Literal["image-puzzle"]
    image: PuzzleImages
    columns: Annotated[int, Field(ge=2, le=4)]
    rows: Annotated[int, Field(ge=2, le=3)]
    pieces: tuple[PuzzlePiece, ...] = Field(min_length=4, max_length=12)

    @model_validator(mode="after")
    def permutation(self) -> Self:
        unique((item.id for item in self.pieces), "image pieces")
        if len(self.pieces) != self.columns * self.rows or {
            item.target_slot for item in self.pieces
        } != set(range(len(self.pieces))):
            raise ValueError("Image pieces need a complete grid permutation")
        return self


class SearchTarget(Contract):
    number: ObjectNumber
    clue: LocalizedCopy


class SceneSearchDesign(InvestigationCopy):
    kind: Literal["scene-search"]
    targets: tuple[SearchTarget, ...] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def distinct_targets(self) -> Self:
        unique((str(item.number) for item in self.targets), "scene search targets")
        return self


InvestigationConfig = Annotated[
    DifferenceDesign | TimelineDesign | ImagePuzzleDesign | SceneSearchDesign,
    Field(discriminator="kind"),
]


class InvestigationLine(Contract):
    speaker: Identifier
    text: LocalizedCopy


class InvestigationInterlude(Contract):
    # One-based selection into ordered tasks, or opening/routes/reunion flattened order.
    after_task: Annotated[int, Field(ge=1, le=18)]
    source_object: ObjectNumber
    required_sources: tuple[ObjectNumber, ...] = Field(min_length=1, max_length=8)
    title: LocalizedCopy
    body: LocalizedCopy
    objective: LocalizedCopy
    opening_lines: tuple[InvestigationLine, ...] = Field(max_length=12)
    plugin: InvestigationConfig
    reward: LocalizedCopy | None = None

    @model_validator(mode="after")
    def source_selection(self) -> Self:
        unique((str(number) for number in self.required_sources), "investigation required sources")
        if isinstance(self.plugin, SceneSearchDesign) and {
            item.number for item in self.plugin.targets
        } != set(self.required_sources):
            raise ValueError("Search targets must equal required source receipts")
        return self


class InvestigationDesign(Contract):
    asset_manifest: tuple[InvestigationImage, ...] = Field(max_length=16)
    interludes: tuple[InvestigationInterlude, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def checked_images(self) -> Self:
        paths = {image.path for image in self.asset_manifest}
        unique((image.path for image in self.asset_manifest), "investigation image paths")
        requested: set[str] = set()
        for row in self.interludes:
            if isinstance(row.plugin, DifferenceDesign):
                requested.update((row.plugin.left_image, row.plugin.right_image))
            elif isinstance(row.plugin, ImagePuzzleDesign):
                requested.add(row.plugin.image.en)
                second = row.plugin.image.tr or row.plugin.image.zh
                if second is not None:
                    requested.add(second)
        if requested != paths:
            raise ValueError("Investigation manifest must cover exactly its requested images")
        if len(json.dumps(self.model_dump(mode="json"), ensure_ascii=True)) > 120000:
            raise ValueError("Investigation design exceeds the bounded text budget")
        return self
