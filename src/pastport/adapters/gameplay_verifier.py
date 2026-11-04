"""Verify only the registered local Demo Activity using a fixed Node runner."""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pastport.adapters.gameplay_catalog import load_gameplay_catalog
from pastport.application.models import ServiceError
from pastport.domain.common import CanonicalSerializer
from pastport.domain.gameplay_preparation import (
    ActivityConfig,
    CoveragePlacement,
    LifecycleReceipt,
    PluginIdentity,
)


class _Result(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    status: str
    catalog_sha256: str
    checks: tuple[str, ...]
    solution: tuple[CoveragePlacement, ...] = ()


class DemoGameplayVerifier:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.plugin = self.root / "gameplay/plugins/plugins.mjs"
        self.runner = self.root / "tools/gameplay_lifecycle.mjs"

    def _plugin_hash(self) -> str:
        digest = hashlib.sha256()
        for name in ("plugins.mjs", "investigation.mjs", "coverage.mjs", "gameplay-catalog.mjs"):
            path = self.plugin.parent / name
            digest.update(name.encode() + b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def identity(self, kind: str = "dialogue") -> PluginIdentity:
        if kind not in ("dialogue", "tiling"):
            raise ServiceError("GAMEPLAY_PLUGIN_UNKNOWN", "No registered plugin for mechanic")
        return PluginIdentity(
            plugin_id=f"pastport.activity.{kind}",
            entrypoint="gameplay/plugins/plugins.mjs",
            code_sha256=self._plugin_hash(),
        )

    def verify(self, config: ActivityConfig) -> LifecycleReceipt:
        executable = shutil.which("node")
        if executable is None:
            raise ServiceError("GAMEPLAY_NODE_MISSING", "Registered Demo host requires Node.js")
        plugin_hash = self.identity().code_sha256
        verifier_hash = hashlib.sha256(self.runner.read_bytes()).hexdigest()
        try:
            result = subprocess.run(
                [executable, "--max-old-space-size=128", str(self.runner)],
                input=config.model_dump_json(),
                text=True,
                capture_output=True,
                cwd=self.root,
                timeout=5,
                check=False,
                env={"PATH": os.defpath, "LANG": "C.UTF-8"},
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ServiceError(
                "GAMEPLAY_PLUGIN_CHECK_FAILED", "Plugin lifecycle did not finish"
            ) from error
        if result.returncode != 0 or len(result.stdout) > 65536:
            raise ServiceError(
                "GAMEPLAY_PLUGIN_CHECK_FAILED", "Registered plugin rejected its configuration"
            )
        if (
            plugin_hash != self.identity().code_sha256
            or verifier_hash != hashlib.sha256(self.runner.read_bytes()).hexdigest()
        ):
            raise ServiceError(
                "GAMEPLAY_CODE_CHANGED", "Plugin or lifecycle verifier changed during execution"
            )
        checked = _Result.model_validate_json(result.stdout)
        if checked.status != "passed" or checked.catalog_sha256 != load_gameplay_catalog().sha256:
            raise ServiceError(
                "GAMEPLAY_PLUGIN_CHECK_FAILED", "Plugin lifecycle checks did not pass"
            )
        return LifecycleReceipt(
            plugin_code_sha256=plugin_hash,
            verifier_sha256=verifier_hash,
            config_sha256=CanonicalSerializer.digest(config),
            checks=checked.checks,
            solution=checked.solution,
        )
