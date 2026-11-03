"""Organizer production contracts; cached replay and fresh dispatch never alias."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr

from pastport.domain.common import Contract, Identifier, Sha256, Text
from pastport.domain.story_reuse import StoryIntroductionChange


class OrganizerSource(Contract):
    source_id: Identifier
    title: Text
    project_id: Identifier
    request_file: Path
    bundle_file: Path | None = None
    is_default: bool = False
    review_binding_file: Path | None = None


class OrganizerCatalog(Contract):
    sources: tuple[OrganizerSource, ...] = ()


class OrganizerSelection(Contract):
    source_id: Identifier


class OrganizerWorkspace(Contract):
    project_id: Identifier
    source_id: Identifier
    story_ready: bool


class OrganizerStart(Contract):
    source_id: Identifier
    mode: Literal["reuse", "regenerate"]
    authorize_model: bool = False
    stop_after: Literal["environment", "story", "game"] = "game"
    brief: Text | None = None
    target_minutes: int = Field(default=10, ge=3, le=60)


class OrganizerSourceView(Contract):
    source_id: Identifier
    title: Text
    project_id: Identifier
    ready: bool
    reuse_ready: bool = False
    reuse_checked: bool = False
    reuse_confirmation_sha256: Sha256 | None = None
    reuse_changes: tuple[StoryIntroductionChange, ...] = ()
    reuse_issues: tuple[Text, ...] = ()
    complete_bundle: bool = False
    review_ready: bool = False
    is_default: bool = False
    message: Text
    input_sha256: Sha256 | None = None


class OrganizerJob(Contract):
    job_id: Identifier
    owner_id: Identifier
    project_id: Identifier
    source_id: Identifier
    mode: Literal["reuse", "regenerate"]
    status: Literal[
        "queued",
        "running",
        "completed",
        "failed",
        "recovery_required",
        "awaiting_materials",
        "awaiting_external",
        "environment_ready",
        "story_ready",
    ]
    input_kind: Literal["registered", "uploads"] = "registered"
    entry_level: Literal["raw", "mapping", "vr", "3d", "raw3d", "idml3d"] | None = None
    completed_stages: tuple[str, ...] = ()
    message: Text
    new_model_calls: int | None = None
    input_sha256: Sha256
    request_key: Identifier
    payload_sha256: Sha256
    result_ready: bool = False
    mounted_preview_ready: bool = False
    prepared_source_id: Identifier | None = None
    cache_directory: Path | None = None
    game_directory: Path | None = None
    error_code: Identifier | None = None
    issues: tuple[Text, ...] = ()


class OrganizerRecovery(Contract):
    confirm_continue: Literal[True]
    authorize_marble: bool = False
    marble_credit_budget: int = Field(default=0, ge=0, le=100000)


class OrganizerFile(Contract):
    file_id: Identifier
    role: Literal["original_pdf", "photos", "mapping_pdf", "tour", "matched_vr", "mounted_3d", "scene_splat", "scene_mesh", "original_idml", "historical_links"]
    filename: Text
    sha256: Sha256
    size_bytes: int = Field(gt=0, le=4 * 1024**3)


class OrganizerMaterials(Contract):
    project_id: Identifier
    owner_id: Identifier
    entry_level: Literal["raw", "mapping", "vr", "3d", "raw3d", "idml3d"]
    files: tuple[OrganizerFile, ...] = ()


class OrganizerProjectCreate(Contract):
    project_id: Identifier
    entry_level: Literal["raw", "mapping", "vr", "3d", "raw3d", "idml3d"]


class OrganizerPlan(Contract):
    entry_level: Literal["raw", "mapping", "vr", "3d", "raw3d", "idml3d"]
    missing_roles: tuple[str, ...]
    reused: tuple[str, ...]
    stages: tuple[str, ...]
    review_focus: tuple[str, ...]
    generation_connected: bool
    message: Text


class OrganizerPasswordLogin(Contract):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)


class OrganizerAdminSetup(Contract):
    password: SecretStr = Field(min_length=1, max_length=1024)
    password_confirmation: SecretStr = Field(min_length=1, max_length=1024)


class OrganizerStorageView(Contract):
    """Locations refer to the server computer, never the visitor's device."""

    cache_directory: Path
    uploads_directory: Path
    jobs_directory: Path


class OrganizerNativeProgress(Contract):
    phase: Text
    recognized_objects: int = Field(default=0, ge=0)
    target_objects: int | None = Field(default=None, ge=1)
    completed_calls: int = Field(default=0, ge=0)
