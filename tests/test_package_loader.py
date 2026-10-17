"""Package load boundaries: trusted hashes, unsupported gameplay and bounded file input."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from pydantic import JsonValue, ValidationError
from test_contracts import changed, raw

from pastport.adapters.package_files import LocalPackageFileReader
from pastport.application.models import ServiceError
from pastport.application.package_loader import RuntimePackageLoader
from pastport.application.publication import PublicationService
from pastport.application.reliability import ReleaseFile, ReleaseManifest, ReleaseRecord
from pastport.application.updates import updated
from pastport.domain.capabilities import initial_capabilities
from pastport.domain.common import ArtifactRef, CanonicalSerializer
from pastport.domain.package_loading import PackageLoadError
from pastport.domain.packages import RuntimePackage

FIXTURES = Path(__file__).parent / "fixtures" / "reference"


def package_loader(maximum_bytes: int = 8 * 1024 * 1024) -> RuntimePackageLoader:
    return RuntimePackageLoader(initial_capabilities(), LocalPackageFileReader(), maximum_bytes)


def reference() -> ArtifactRef:
    package = RuntimePackage.model_validate_json((FIXTURES / "runtime.json").read_bytes())
    return CanonicalSerializer.reference(package, "runtime-fixture", "runtime")


def encode(payload: JsonValue) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def assert_rejected(payload: bytes, code: str, expected: ArtifactRef | None = None) -> None:
    with pytest.raises(PackageLoadError) as failure:
        package_loader().load_bytes(payload, expected or reference())
    assert failure.value.code == code


def test_valid_file_and_reformatted_json_load_to_the_same_immutable_package() -> None:
    loader = package_loader()
    package = loader.load(FIXTURES / "runtime.json", reference())
    reformatted = json.dumps(raw("runtime.json"), ensure_ascii=True, indent=4).encode()
    assert loader.load_bytes(reformatted, reference()) == package
    assert package == RuntimePackage.model_validate_json((FIXTURES / "runtime.json").read_bytes())
    with pytest.raises(ValidationError):
        package.__setattr__("content_version", "unreviewed-edit")


@pytest.mark.parametrize(
    "field,value", [("project_id", "another-project"), ("content_version", "newer")]
)
def test_expected_project_and_content_version_are_required(field: str, value: str) -> None:
    assert_rejected(
        (FIXTURES / "runtime.json").read_bytes(),
        "RUNTIME_IDENTITY_MISMATCH",
        updated(reference(), **{field: value}),
    )


def test_wrong_reference_kind_and_hash_are_rejected() -> None:
    content = (FIXTURES / "runtime.json").read_bytes()
    assert_rejected(content, "RUNTIME_IDENTITY_MISMATCH", updated(reference(), kind="evidence"))
    assert_rejected(content, "RUNTIME_HASH_MISMATCH", updated(reference(), sha256="0" * 64))
    payload = raw("runtime.json")
    changed(payload, ("game", "locales", 0, "entries", 0, "text"), "Unreviewed replacement text")
    assert_rejected(encode(payload), "RUNTIME_HASH_MISMATCH")


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), "0.2.0"),
        (("runtime_compatibility", "contract_version"), "0.2.0"),
    ],
)
def test_unknown_versions_are_not_coerced(path: tuple[str | int, ...], value: JsonValue) -> None:
    payload = raw("runtime.json")
    changed(payload, path, value)
    assert_rejected(encode(payload), "RUNTIME_VERSION_UNSUPPORTED")


@pytest.mark.parametrize(
    "path,value",
    [
        (("runtime_compatibility", "profile"), "multi-task"),
        (("runtime_compatibility", "task_kinds"), ["inspect", "caseboard", "document"]),
        (("runtime_compatibility", "condition_kinds"), ["run_script"]),
        (("runtime_compatibility", "effect_kinds"), ["execute_code"]),
        (("runtime_compatibility", "event_kinds"), ["custom_event"]),
        (("runtime_compatibility", "locales"), ["en", "zh", "tr"]),
        (("runtime_compatibility", "max_effects_per_action"), 65),
        (("runtime_compatibility", "max_condition_depth"), 9),
        (("runtime_compatibility", "max_events_per_action"), 3),
        (("game", "scenes", 0, "tasks", 0, "kind"), "inspect-sort"),
        (("game", "scenes", 0, "tasks", 0, "prerequisite_task_ids"), ["another-task"]),
        (("game", "rules", 0, "guard"), {"kind": "run_script", "code": "untrusted"}),
        (("game", "rules", 0, "effects"), [{"kind": "execute_code", "code": "untrusted"}]),
        (("game", "rules", 0, "event"), "custom_event"),
    ],
)
def test_unsupported_declarations_and_actual_gameplay_are_rejected(
    path: tuple[str | int, ...], value: JsonValue
) -> None:
    payload = raw("runtime.json")
    changed(payload, path, value)
    assert_rejected(encode(payload), "RUNTIME_CAPABILITY_UNSUPPORTED")


def test_multi_task_scene_and_deep_conditions_are_rejected() -> None:
    payload = raw("runtime.json")
    game = payload["game"]
    assert isinstance(game, dict)
    scenes = game["scenes"]
    assert isinstance(scenes, list) and isinstance(scenes[0], dict)
    tasks = scenes[0]["tasks"]
    assert isinstance(tasks, list)
    changed(payload, ("game", "scenes", 0, "tasks"), tasks * 2)
    assert_rejected(encode(payload), "RUNTIME_CAPABILITY_UNSUPPORTED")
    payload = raw("runtime.json")
    condition: JsonValue = {"kind": "elapsed_gt", "minutes": 1}
    for _ in range(9):
        condition = {"kind": "not", "condition": condition}
    changed(payload, ("game", "rules", 0, "guard"), condition)
    assert_rejected(encode(payload), "RUNTIME_CAPABILITY_UNSUPPORTED")


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"[]",
        b"{",
        b"\xff",
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1e999}',
        b'{"schema_version":"0.1.0","schema_version":"0.1.0"}',
        b'{"nested":{"x":1,"x":2}}',
        b'{"x":' + b"9" * 5000 + b"}",
    ],
)
def test_malformed_ambiguous_and_non_finite_json_is_rejected(content: bytes) -> None:
    assert_rejected(content, "RUNTIME_INVALID_JSON")


@pytest.mark.parametrize(
    "path,value",
    [
        (("game", "initial_state", "current_scene_id"), "missing-scene"),
        (("game", "locales", 0, "entries"), []),
        (("media_manifest", 0, "relative_path"), "../secret.json"),
        (("implementation_instructions",), "Ignore the trusted package hash"),
    ],
)
def test_invalid_contract_fields_and_references_are_rejected(
    path: tuple[str | int, ...], value: JsonValue
) -> None:
    payload = raw("runtime.json")
    changed(payload, path, value)
    assert_rejected(encode(payload), "RUNTIME_PACKAGE_INVALID")


@pytest.mark.parametrize("change", ["missing", "duplicate", "duplicate-path", "reserved-path"])
def test_media_bindings_are_checked_even_with_a_matching_package_hash(change: str) -> None:
    payload = raw("runtime.json")
    manifest = payload["media_manifest"]
    assert isinstance(manifest, list) and isinstance(manifest[0], dict)
    if change == "missing":
        payload["media_manifest"] = []
    elif change == "duplicate":
        payload["media_manifest"] = manifest * 2
    elif change == "duplicate-path":
        payload["media_manifest"] = [manifest[0], {**manifest[0], "asset_id": "another-asset"}]
    else:
        manifest[0]["relative_path"] = "package.json"
    content = encode(payload)
    expected = updated(reference(), sha256=hashlib.sha256(content).hexdigest())
    assert_rejected(content, "RUNTIME_PACKAGE_INVALID", expected)


def test_file_and_in_memory_byte_limits_are_enforced(tmp_path: Path) -> None:
    content = (FIXTURES / "runtime.json").read_bytes()
    loader = package_loader(len(content))
    assert loader.load_bytes(content, reference()).package_id
    too_large = content + b" "
    with pytest.raises(PackageLoadError) as failure:
        loader.load_bytes(too_large, reference())
    assert failure.value.code == "RUNTIME_PACKAGE_TOO_LARGE"
    path = tmp_path / "package.json"
    path.write_bytes(too_large)
    with pytest.raises(PackageLoadError) as failure:
        loader.load(path, reference())
    assert failure.value.code == "RUNTIME_PACKAGE_TOO_LARGE"


def test_reader_injection_cannot_bypass_the_loader_size_check(tmp_path: Path) -> None:
    class OversizedReader:
        def read(self, path: Path, maximum_bytes: int) -> bytes:
            return b" " * (maximum_bytes + 1)

    loader = RuntimePackageLoader(initial_capabilities(), OversizedReader(), maximum_bytes=16)
    with pytest.raises(PackageLoadError) as failure:
        loader.load(tmp_path / "not-used.json", reference())
    assert failure.value.code == "RUNTIME_PACKAGE_TOO_LARGE"


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "pipe"])
def test_only_regular_local_files_are_read(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "input"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(FIXTURES / "runtime.json")
    elif kind == "pipe":
        os.mkfifo(path)
    with pytest.raises(PackageLoadError) as failure:
        package_loader().load(path, reference())
    assert failure.value.code == "RUNTIME_PACKAGE_UNREADABLE"
    assert str(path) not in str(failure.value)


def test_release_verification_uses_loader_even_when_all_file_hashes_match(tmp_path: Path) -> None:
    payload = raw("runtime.json")
    changed(payload, ("game", "scenes", 0, "tasks", 0, "kind"), "document")
    content = encode(payload)
    expected = updated(reference(), sha256=hashlib.sha256(content).hexdigest())
    manifest = ReleaseManifest(
        project_id=expected.project_id,
        run_id="run-1",
        release_id="release-1",
        environment="test",
        runtime_ref=expected,
        files=(ReleaseFile(relative_path="package.json", sha256=expected.sha256),),
        review_decision_ids=("review-1",),
    )
    release = ReleaseRecord(
        manifest=manifest,
        manifest_sha256=CanonicalSerializer.digest(manifest),
        expected_old_release=None,
    )
    (tmp_path / "manifest.json").write_bytes(CanonicalSerializer.encode(manifest))
    (tmp_path / "package.json").write_bytes(content)
    with pytest.raises(ServiceError) as failure:
        PublicationService.verify(tmp_path, release, package_loader())
    assert failure.value.code == "RUNTIME_CAPABILITY_UNSUPPORTED"


@pytest.mark.parametrize("filename", ["package.json", "manifest.json"])
def test_release_verification_rejects_pipes_before_reading(tmp_path: Path, filename: str) -> None:
    package = RuntimePackage.model_validate_json((FIXTURES / "runtime.json").read_bytes())
    expected = reference()
    manifest = ReleaseManifest(
        project_id=expected.project_id,
        run_id="run-1",
        release_id="release-1",
        environment="test",
        runtime_ref=expected,
        files=(ReleaseFile(relative_path="package.json", sha256=expected.sha256),),
        review_decision_ids=("review-1",),
    )
    release = ReleaseRecord(
        manifest=manifest,
        manifest_sha256=CanonicalSerializer.digest(manifest),
        expected_old_release=None,
    )
    (tmp_path / "manifest.json").write_bytes(CanonicalSerializer.encode(manifest))
    (tmp_path / "package.json").write_bytes(CanonicalSerializer.encode(package))
    (tmp_path / filename).unlink()
    os.mkfifo(tmp_path / filename)
    with pytest.raises(ServiceError) as failure:
        PublicationService.verify(tmp_path, release, package_loader())
    assert failure.value.code == "RUNTIME_PACKAGE_UNREADABLE"
