"""Native uploaded-material preparation, finite authorization and stage outputs."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from pastport.domain.common import Contract, Identifier, Sha256, Text
from pastport.domain.game_making import GameMakingRequest


class UploadedProductionStart(Contract):
    stop_after: Literal["environment", "game"] = "game"
    authorize_model: bool = False
    authorize_marble: bool = False
    marble_model: Literal["marble-1.1", "marble-1.0-draft"] = "marble-1.1"
    marble_credit_budget: int = Field(default=0, ge=0, le=100000)
    max_evidence_calls: int = Field(default=8, ge=1, le=100)
    max_environment_calls: int = Field(default=20, ge=1, le=40)
    max_recorded_tokens: int = Field(default=250000, ge=1000, le=1000000)
    target_minutes: int = Field(default=10, ge=3, le=60)
    brief: Text = "Create an original concise heritage story with explicit tasks, spatial intents and supported gameplay intents from these registered inputs."


class UploadedAsset(Contract):
    file_id: Identifier
    role: Literal["original_pdf", "photos", "mapping_pdf", "tour", "matched_vr", "mounted_3d", "scene_splat", "scene_mesh", "original_idml", "historical_links"]
    path: Path
    filename: Text
    sha256: Sha256


class NativeInputRequest(Contract):
    project_id: Identifier
    owner_id: Identifier
    job_id: Identifier
    entry_level: Literal["raw", "mapping", "vr", "3d", "raw3d", "idml3d", "catalog3d"]
    files: tuple[UploadedAsset, ...]
    options: UploadedProductionStart
    shared_player_assets: Path


class NativePreparedInputs(Contract):
    state: Literal["ready", "awaiting_materials", "awaiting_external"]
    request: GameMakingRequest | None = None
    mapping_pdf: Path | None = None
    completed_stages: tuple[str, ...]
    message: Text


class RegisteredNativeSource(Contract):
    parent_source_id: Identifier | None = None
    review_binding_file: Path | None = None
    owner_id: Identifier
    project_id: Identifier
    source_id: Identifier
    title: Text
    request_file: Path
