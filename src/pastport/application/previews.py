"""Typed private preview boundaries, independent of approval and publication."""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import AwareDatetime, Field

from pastport.application.models import Actor
from pastport.domain.common import (
    ArtifactRef,
    Contract,
    Environment,
    Identifier,
    NonNegative,
    Sha256,
)
from pastport.domain.game import ActionResult, PlayerState
from pastport.domain.packages import RuntimePackage


class SessionView(Contract):
    actor_id: Identifier
    roles: tuple[Literal["editor", "evidence", "narrative", "publisher", "operator"], ...]
    project_ids: tuple[Identifier, ...] | None
    environment: Environment


class CreatePreview(Contract):
    expected_revision: NonNegative
    source_ref: ArtifactRef


class PreviewRecord(Contract):
    preview_id: Identifier
    actor_id: Identifier
    project_id: Identifier
    run_id: Identifier
    environment: Environment
    kind: Literal["draft", "test"]
    source_ref: ArtifactRef
    evidence_ref: ArtifactRef
    runtime_ref: ArtifactRef
    runtime_package: RuntimePackage
    expires_at: AwareDatetime
    request_key: str = Field(min_length=1, max_length=160)
    request_hash: Sha256


class PreviewView(Contract):
    preview_id: Identifier
    project_id: Identifier
    run_id: Identifier
    environment: Environment
    kind: Literal["draft", "test"]
    source_ref: ArtifactRef
    runtime_ref: ArtifactRef
    runtime_package: RuntimePackage
    state: PlayerState
    expires_at: AwareDatetime


class PreviewActionView(Contract):
    preview_id: Identifier
    persisted: Literal[True] = True
    result: ActionResult


class PrivatePackageView(Contract):
    runtime_ref: ArtifactRef
    runtime_package: RuntimePackage


class PreviewRepository(Protocol):
    def find_request(self, actor: Actor, run_id: str, request_key: str) -> PreviewRecord | None: ...
    def get(self, actor: Actor, run_id: str, preview_id: str) -> PreviewRecord: ...
    def create_preview(
        self, record: PreviewRecord, state: PlayerState, now: datetime
    ) -> PreviewRecord: ...
    def state(self, record: PreviewRecord) -> PlayerState: ...
    def commit(
        self, record: PreviewRecord, previous: PlayerState, following: PlayerState, now: datetime
    ) -> bool: ...
