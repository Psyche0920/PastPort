"""Server-side accounts and explicit test configuration."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from pastport.adapters.passwords import PasswordHasher
from pastport.application.execution_models import ExecutionSettings
from pastport.application.models import Actor
from pastport.application.module_selection import ModuleMode
from pastport.domain.common import Contract, Sha256


class Credential(Contract):
    token_sha256: Sha256 | None = None
    actor: Actor
    username: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    password_hash: str | None = Field(default=None, repr=False)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_methods(self) -> Self:
        if (self.username is None) != (self.password_hash is None):
            raise ValueError("Configure username and password hash together")
        if self.password_hash is not None and not PasswordHasher.valid_hash(self.password_hash):
            raise ValueError("Unsupported password hash format")
        if self.token_sha256 is None and self.password_hash is None:
            raise ValueError("At least one authentication method is required")
        return self


class Accounts(Contract):
    accounts: tuple[Credential, ...]

    @model_validator(mode="after")
    def unique_accounts(self) -> Self:
        if not self.accounts:
            raise ValueError("At least one authenticated account must be configured")
        for values in (
            [a.token_sha256 for a in self.accounts if a.token_sha256 is not None],
            [a.username for a in self.accounts if a.username is not None],
            [a.actor.actor_id for a in self.accounts],
        ):
            if len(values) != len(set(values)):
                raise ValueError("Account identities and credentials must be unique")
        return self


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
    story_structure: Literal["authored_graph", "compiled_plan_v1"] = "authored_graph"
    accounts_file: Path | None = None
    organizer_local_admin_setup: bool = False
    organizer_catalog: Path | None = None
    organizer_player_assets: Path | None = None

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
        Accounts(accounts=self.accounts)
        if self.fixture_directory is not None and self.content_directory is not None:
            raise ValueError("Choose a test fixture or authored content directory, not both")
        if self.environment == "production" and self.fixture_directory is not None:
            raise ValueError("Fixture adapters are forbidden in production mode")
