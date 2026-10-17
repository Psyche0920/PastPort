"""Load a runtime package against trusted identity and explicit consumer capabilities."""

import json
import math
from pathlib import Path

from pydantic import JsonValue, ValidationError

from pastport.domain.common import ArtifactRef, CanonicalSerializer
from pastport.domain.game import InspectTask, RuntimeCapabilities
from pastport.domain.package_loading import PackageLoadError
from pastport.domain.packages import RuntimePackage
from pastport.ports.package_files import PackageFileReader


class RuntimePackageLoader:
    def __init__(
        self,
        supported_capabilities: RuntimeCapabilities,
        reader: PackageFileReader,
        maximum_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        if type(maximum_bytes) is not int or maximum_bytes <= 0:
            raise ValueError("Package byte limit must be a positive integer")
        self.supported = RuntimeCapabilities.model_validate(supported_capabilities)
        self.reader = reader
        self.maximum_bytes = maximum_bytes

    def load(self, path: Path, expected_reference: ArtifactRef) -> RuntimePackage:
        return self.load_bytes(self.reader.read(path, self.maximum_bytes), expected_reference)

    def load_bytes(self, content: bytes, expected_reference: ArtifactRef) -> RuntimePackage:
        if len(content) > self.maximum_bytes:
            raise PackageLoadError(
                "RUNTIME_PACKAGE_TOO_LARGE", "Package exceeds the configured byte limit"
            )
        try:
            reference = ArtifactRef.model_validate(expected_reference)
        except ValidationError as error:
            raise PackageLoadError(
                "RUNTIME_IDENTITY_MISMATCH", "Expected package reference is invalid"
            ) from error
        if reference.kind != "runtime":
            raise PackageLoadError(
                "RUNTIME_IDENTITY_MISMATCH", "Expected reference must identify a runtime package"
            )
        payload = self._parse_json(content)
        self._check_header(payload)
        self._check_task_profile(payload)
        try:
            # Validate JSON transport rather than coercing its arrays into Python tuples.
            package = RuntimePackage.model_validate_json(content)
        except ValidationError as error:
            unsupported = any(
                finding["type"] == "union_tag_invalid"
                or (
                    finding["type"] == "literal_error"
                    and finding["loc"]
                    and finding["loc"][-1] in ("event", "kind", "answer_rule", "locale")
                )
                or (
                    finding["type"] == "too_long"
                    and finding["loc"]
                    and finding["loc"][-1] in ("effects", "tasks")
                )
                or finding["msg"].endswith("Condition depth exceeds profile limit")
                for finding in error.errors(include_input=False)
            )
            raise PackageLoadError(
                "RUNTIME_CAPABILITY_UNSUPPORTED" if unsupported else "RUNTIME_PACKAGE_INVALID",
                "Package uses unsupported gameplay"
                if unsupported
                else "Package failed contract validation",
                "/game",
            ) from error
        if (
            package.project_id != reference.project_id
            or package.schema_version != reference.schema_version
            or package.content_version != reference.content_version
        ):
            raise PackageLoadError(
                "RUNTIME_IDENTITY_MISMATCH",
                "Package does not match the expected project or version",
            )
        if CanonicalSerializer.digest(package) != reference.sha256:
            raise PackageLoadError(
                "RUNTIME_HASH_MISMATCH", "Package content does not match its trusted hash"
            )
        self._check_media(package)
        return package

    @staticmethod
    def _object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for key, value in pairs:
            if key in result:
                raise PackageLoadError("RUNTIME_INVALID_JSON", "Duplicate JSON keys are forbidden")
            result[key] = value
        return result

    @staticmethod
    def _constant(value: str) -> JsonValue:
        raise PackageLoadError("RUNTIME_INVALID_JSON", "Non-finite JSON numbers are forbidden")

    @staticmethod
    def _float(value: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            raise PackageLoadError("RUNTIME_INVALID_JSON", "Non-finite JSON numbers are forbidden")
        return result

    @classmethod
    def _parse_json(cls, content: bytes) -> dict[str, JsonValue]:
        try:
            payload: JsonValue = json.loads(
                content.decode("utf-8"),
                object_pairs_hook=cls._object,
                parse_constant=cls._constant,
                parse_float=cls._float,
            )
        except PackageLoadError:
            raise
        except (UnicodeError, ValueError, RecursionError) as error:
            raise PackageLoadError(
                "RUNTIME_INVALID_JSON", "Package must contain valid UTF-8 JSON"
            ) from error
        if not isinstance(payload, dict):
            raise PackageLoadError("RUNTIME_INVALID_JSON", "Package JSON must be an object")
        return payload

    def _check_header(self, payload: dict[str, JsonValue]) -> None:
        version = payload.get("schema_version")
        if not isinstance(version, str):
            raise PackageLoadError(
                "RUNTIME_PACKAGE_INVALID", "Package schema version is required", "/schema_version"
            )
        if version != self.supported.contract_version:
            raise PackageLoadError(
                "RUNTIME_VERSION_UNSUPPORTED",
                "Package schema version is unsupported",
                "/schema_version",
            )
        compatibility = payload.get("runtime_compatibility")
        if not isinstance(compatibility, dict):
            raise PackageLoadError(
                "RUNTIME_PACKAGE_INVALID",
                "Package compatibility declaration is required",
                "/runtime_compatibility",
            )
        if compatibility.get("contract_version") != self.supported.contract_version:
            raise PackageLoadError(
                "RUNTIME_VERSION_UNSUPPORTED",
                "Package contract version is unsupported",
                "/runtime_compatibility/contract_version",
            )
        if compatibility.get("profile") != self.supported.profile:
            raise PackageLoadError(
                "RUNTIME_CAPABILITY_UNSUPPORTED",
                "Package capability profile is unsupported",
                "/runtime_compatibility/profile",
            )
        try:
            declared = RuntimeCapabilities.model_validate_json(
                json.dumps(compatibility, allow_nan=False)
            )
        except ValidationError as error:
            raise PackageLoadError(
                "RUNTIME_CAPABILITY_UNSUPPORTED",
                "Package capability declaration is unsupported",
                "/runtime_compatibility",
            ) from error
        for name in ("task_kinds", "condition_kinds", "effect_kinds", "event_kinds", "locales"):
            if not set(getattr(declared, name)) <= set(getattr(self.supported, name)):
                raise PackageLoadError(
                    "RUNTIME_CAPABILITY_UNSUPPORTED",
                    "Package requires an unavailable capability",
                    "/runtime_compatibility/" + name,
                )
        for name in ("max_events_per_action", "max_effects_per_action", "max_condition_depth"):
            if getattr(declared, name) > getattr(self.supported, name):
                raise PackageLoadError(
                    "RUNTIME_CAPABILITY_UNSUPPORTED",
                    "Package requires a higher execution limit",
                    "/runtime_compatibility/" + name,
                )

    @staticmethod
    def _check_task_profile(payload: dict[str, JsonValue]) -> None:
        game = payload.get("game")
        scenes = game.get("scenes") if isinstance(game, dict) else None
        if not isinstance(scenes, list):
            return  # The contract validator reports malformed shape.
        for scene in scenes:
            tasks = scene.get("tasks") if isinstance(scene, dict) else None
            if isinstance(tasks, list) and (
                len(tasks) > 1
                or any(
                    isinstance(task, dict) and task.get("prerequisite_task_ids") for task in tasks
                )
            ):
                raise PackageLoadError(
                    "RUNTIME_CAPABILITY_UNSUPPORTED",
                    "Multi-task scenes and task dependencies require another profile",
                    "/game/scenes",
                )

    @staticmethod
    def _check_media(package: RuntimePackage) -> None:
        assets = [item.asset_id for item in package.media_manifest]
        paths = [item.relative_path for item in package.media_manifest]
        if len(assets) != len(set(assets)) or len(paths) != len(set(paths)):
            raise PackageLoadError(
                "RUNTIME_PACKAGE_INVALID",
                "Media identities and paths must be unique",
                "/media_manifest",
            )
        if any(path in ("package.json", "manifest.json") for path in paths):
            raise PackageLoadError(
                "RUNTIME_PACKAGE_INVALID",
                "Media cannot replace package metadata",
                "/media_manifest",
            )
        for scene in package.game.scenes:
            for task in scene.tasks:
                if isinstance(task, InspectTask) and task.asset_id not in assets:
                    raise PackageLoadError(
                        "RUNTIME_PACKAGE_INVALID",
                        "Inspect task media is missing from the manifest",
                        "/media_manifest",
                    )
