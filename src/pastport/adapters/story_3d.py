"""Join approved shared assembly to the separately versioned local 3D delivery bridge."""

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic import ValidationError

from pastport.adapters.runtime_resources import runtime_root
from pastport.application.models import ServiceError
from pastport.domain.common import CanonicalSerializer, Contract, Sha256
from pastport.domain.modules import AssemblyRequest, AssemblyResult
from pastport.ports.modules import AssemblyPort


class Story3DBuildReceipt(Contract):
    runtime_sha256: Sha256
    preparation_sha256: Sha256
    manifest_sha256: Sha256


class Story3DAssemblyAdapter:
    """Build a private 3D candidate after normal evidence/narrative approval and assembly.

    Gameplay/Presentation owns the preparation artifact, named by exact narrative hash.
    This adapter cannot generate story, grant approval, change rules, or call a provider.
    """

    def __init__(
        self,
        assembler: AssemblyPort,
        preparation_directory: Path,
        museum_directory: Path,
        output_directory: Path,
        *,
        node_path: Path | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        if not 0 < timeout_seconds <= 120:
            raise ValueError("Story build timeout must be between zero and 120 seconds")
        self.assembler = assembler
        self.preparation_directory = preparation_directory.resolve()
        self.museum_directory = museum_directory.resolve()
        self.output_directory = output_directory.resolve()
        self.node_path = node_path
        self.timeout_seconds = timeout_seconds
        self.builder = runtime_root() / "prototype/story-agent-demo/build-story-package.mjs"

    def assemble(self, request: AssemblyRequest) -> AssemblyResult:
        result = self.assembler.assemble(request)
        if any(issue.severity == "blocking" for issue in result.report.issues):
            raise ServiceError("STORY_ASSEMBLY_BLOCKED", "Shared assembly reported blocking issues")
        runtime_hash = CanonicalSerializer.digest(result.package)
        preparation = self.preparation_directory / (request.narrative_ref.sha256 + ".json")
        try:
            if preparation.is_symlink() or preparation.stat().st_size > 8 * 1024 * 1024:
                raise ServiceError(
                    "STORY_PREPARATION_INVALID", "Preparation is not a bounded regular file"
                )
            preparation_bytes = preparation.read_bytes()
        except OSError as error:
            raise ServiceError(
                "STORY_PREPARATION_MISSING",
                "Gameplay/Presentation has no ready preparation for this exact narrative version",
            ) from error
        preparation_hash = hashlib.sha256(preparation_bytes).hexdigest()
        output = self.output_directory / (runtime_hash + "-" + preparation_hash)
        if output.exists():
            self._verify_receipt(output, runtime_hash, preparation_hash)
            return result
        executable = str(self.node_path) if self.node_path else shutil.which("node")
        if executable is None or not self.builder.is_file():
            raise ServiceError(
                "STORY_BUILDER_UNAVAILABLE", "Local Story-to-3D builder is unavailable", 503
            )
        try:
            self.output_directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=".story-input-", dir=self.output_directory
            ) as temporary:
                directory = Path(temporary)
                runtime_file, plan_file = directory / "runtime.json", directory / "preparation.json"
                runtime_file.write_text(result.package.model_dump_json(), encoding="utf-8")
                plan_file.write_bytes(preparation_bytes)
                with tempfile.TemporaryFile() as log:
                    with subprocess.Popen(
                        [
                            executable,
                            "--max-old-space-size=256",
                            str(self.builder),
                            "from-generated",
                            "--input",
                            str(runtime_file),
                            "--preparation",
                            str(plan_file),
                            "--museum",
                            str(self.museum_directory),
                            "--output",
                            str(output),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=log,
                        env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                        cwd=self.builder.parent,
                    ) as process:
                        try:
                            return_code = process.wait(timeout=self.timeout_seconds)
                        except subprocess.TimeoutExpired as error:
                            process.kill()
                            process.wait()
                            raise ServiceError(
                                "STORY_BUILD_TIMEOUT", "3D candidate exceeded its build time limit"
                            ) from error
                    if return_code != 0:
                        raise ServiceError(
                            "STORY_BUILD_FAILED",
                            "Story, museum or preparation inputs failed the local 3D build checks",
                        )
            manifest = output / "manifest.json"
            receipt = Story3DBuildReceipt(
                runtime_sha256=runtime_hash,
                preparation_sha256=preparation_hash,
                manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
            )
            (output / "workflow-build-receipt.json").write_text(
                receipt.model_dump_json(), encoding="utf-8"
            )
        except OSError as error:
            raise ServiceError(
                "STORY_BUILD_IO_FAILED", "3D candidate files could not be prepared"
            ) from error
        return result

    @staticmethod
    def _verify_receipt(output: Path, runtime_hash: str, preparation_hash: str) -> None:
        try:
            receipt = Story3DBuildReceipt.model_validate_json(
                (output / "workflow-build-receipt.json").read_bytes()
            )
            manifest_hash = hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
        except (OSError, ValidationError) as error:
            raise ServiceError(
                "STORY_BUILD_UNVERIFIED", "Existing 3D candidate has no valid build receipt"
            ) from error
        if (
            receipt.runtime_sha256 != runtime_hash
            or receipt.preparation_sha256 != preparation_hash
            or receipt.manifest_sha256 != manifest_hash
        ):
            raise ServiceError(
                "STORY_BUILD_CHANGED", "Existing 3D candidate differs from its build receipt"
            )
