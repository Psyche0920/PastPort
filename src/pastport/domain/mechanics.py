"""Shared task requirements and capability limits, independent of plugin implementations."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import CanonicalSerializer, Contract, Identifier, Sha256, unique

Dimension = Annotated[int, Field(ge=1, le=8)]


class CoverageProblem(Contract):
    width: Dimension
    height: Dimension
    pieces: Annotated[tuple[tuple[Dimension, Dimension], ...], Field(min_length=1, max_length=32)]
    rotation_allowed: bool = True

    @model_validator(mode="after")
    def exact_area(self) -> Self:
        if sum(w * h for w, h in self.pieces) != self.width * self.height:
            raise ValueError("Requested pieces do not cover the requested board area")
        return self


class SourceChoiceRequirement(Contract):
    target_claim_id: Identifier
    contrast_claim_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def distinct_sources(self) -> Self:
        unique((self.target_claim_id, *self.contrast_claim_ids), "source choice identities")
        return self


class GameplayCapability(Contract):
    capability_id: Identifier
    plugin_id: Identifier
    kind: Literal["dialogue", "tiling"]
    version: Literal["1.0.0"]
    max_items: Annotated[int, Field(ge=1, le=128)]
    board_width: Dimension | None
    board_height: Dimension | None
    minimum_pieces: Annotated[int, Field(ge=1, le=32)] | None
    maximum_pieces: Annotated[int, Field(ge=1, le=32)] | None
    maximum_piece_dimension: Dimension | None
    rotation_allowed: bool
    source_choice_required: bool
    solver_node_limit: Annotated[int, Field(ge=1, le=200000)] | None
    failure_policy: Literal["retry_without_story_progress"]
    exit_policy: Literal["preserve_progress"]

    def accepts(self, problem: CoverageProblem) -> bool:
        return (
            self.kind == "tiling"
            and problem.width == self.board_width
            and problem.height == self.board_height
            and self.minimum_pieces is not None
            and self.maximum_pieces is not None
            and self.minimum_pieces <= len(problem.pieces) <= self.maximum_pieces
            and self.maximum_piece_dimension is not None
            and all(max(piece) <= self.maximum_piece_dimension for piece in problem.pieces)
            and (not problem.rotation_allowed or self.rotation_allowed)
        )


class GameplayCapabilities(Contract):
    schema_version: Literal["gameplay-capabilities/1.0.0"]
    host_profile: Literal["pastport.demo.activities/1"]
    profiles: tuple[GameplayCapability, ...]

    @property
    def sha256(self) -> Sha256:
        return CanonicalSerializer.digest(self)

    def profile(self, capability_id: str) -> GameplayCapability | None:
        return next((item for item in self.profiles if item.capability_id == capability_id), None)

    @model_validator(mode="after")
    def identities(self) -> Self:
        unique((item.capability_id for item in self.profiles), "gameplay capabilities")
        unique((item.plugin_id for item in self.profiles), "gameplay plugin identities")
        return self
