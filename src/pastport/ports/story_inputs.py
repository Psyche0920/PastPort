"""Explicit read-only input injection; neither generation nor review mutation."""

from pathlib import Path
from typing import Protocol

from pastport.domain.story_inputs import (
    EnvironmentReadRequest,
    EnvironmentSnapshot,
    MetricSpatialSnapshot,
)
from pastport.ports.modules import ExecutionContext


class MatchedEnvironmentReader(Protocol):
    async def read(
        self, request: EnvironmentReadRequest, context: ExecutionContext
    ) -> EnvironmentSnapshot: ...


class ContentAuthority(Protocol):
    @property
    def database(self) -> Path:
        """Resolve a verified shared authority; this is explicitly injected trusted code."""
        ...


class EnvironmentSpatialReader(Protocol):
    def read_spatial(
        self, snapshot: EnvironmentSnapshot, context: ExecutionContext
    ) -> MetricSpatialSnapshot:
        """Read registered 3D state and rules without inferring action permissions."""
        ...
