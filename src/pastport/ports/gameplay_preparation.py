"""A local plugin verifier cannot approve Story, geometry or global task completion."""

from typing import Protocol

from pastport.domain.gameplay_preparation import ActivityConfig, LifecycleReceipt


class GameplayVerifier(Protocol):
    def verify(self, config: ActivityConfig) -> LifecycleReceipt: ...
