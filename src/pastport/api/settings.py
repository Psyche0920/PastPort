"""Server-side accounts and explicit test configuration."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pastport.application.execution_models import ExecutionSettings
from pastport.application.models import Actor
from pastport.application.module_selection import ModuleMode
from pastport.domain.common import Contract, Sha256


class Credential(Contract):
    token_sha256: Sha256
    actor: Actor


class Accounts(Contract):
    accounts: tuple[Credential, ...]


@dataclass(frozen=True, slots=True)
class AppSettings:
    data_directory: Path
    accounts: tuple[Credential, ...]
    environment: Literal["test", "production"] = "production"
    fixture_directory: Path | None = None
    content_directory: Path | None = None
    resource_directory: Path | None = None
    execution: ExecutionSettings = ExecutionSettings()
    skill_directory: Path | None = None
    evidence_mode: ModuleMode | None = None
    narrative_mode: ModuleMode | None = None
    resources_mode: ModuleMode | None = None
    story_3d_preparation_directory: Path | None = None
    story_3d_museum_directory: Path | None = None
    story_3d_output_directory: Path | None = None
    story_host_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        story_paths = (
            self.story_3d_preparation_directory,
            self.story_3d_museum_directory,
            self.story_3d_output_directory,
        )
        if any(path is not None for path in story_paths) and not all(
            path is not None for path in story_paths
        ):
            raise ValueError("Configure preparation, museum and output directories together")
        if not self.accounts:
            raise ValueError("At least one authenticated account must be configured")
        if len({account.token_sha256 for account in self.accounts}) != len(self.accounts):
            raise ValueError("Account token digests must be unique")
        if len({account.actor.actor_id for account in self.accounts}) != len(self.accounts):
            raise ValueError("Account actor identities must be unique")
        if self.fixture_directory is not None and self.content_directory is not None:
            raise ValueError("Choose a test fixture or authored content directory, not both")
        if self.environment == "production" and self.fixture_directory is not None:
            raise ValueError("Fixture adapters are forbidden in production mode")
