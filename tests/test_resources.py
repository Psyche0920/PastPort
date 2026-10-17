"""Resource storage is replaceable; identity, bounded reads and hashes stay enforced."""

import json
import os
import shutil
from pathlib import Path

import pytest

from pastport.adapters.assembly import PackageAssembler
from pastport.adapters.resources import LocalResourceReader
from pastport.application.models import ServiceError
from pastport.application.resources import VerifiedResourceReader
from pastport.application.updates import updated
from pastport.domain.modules import AssemblyRequest
from pastport.domain.resources import ResourceData, ResourceReference

FIXTURES = Path(__file__).parent / "fixtures/reference"


def asset_reference() -> ResourceReference:
    item = json.loads((FIXTURES / "evidence.json").read_bytes())["assets"][0]
    return ResourceReference(
        project_id="fixture-project",
        resource_id=item["asset_id"],
        kind="asset",
        version=item["version"],
        sha256=item["derivative_sha256"],
    )


def test_deterministic_assembly_uses_registered_assets_without_a_runtime_template(
    tmp_path: Path,
) -> None:
    for name in ("resources.json", "synthetic-source.txt", "synthetic-hatch.svg"):
        shutil.copyfile(FIXTURES / name, tmp_path / name)
    assembler = PackageAssembler(LocalResourceReader(tmp_path))
    request = AssemblyRequest.model_validate_json((FIXTURES / "assembly-request.json").read_bytes())
    first = assembler.assemble(request)
    assert first == assembler.assemble(request)
    assert first.package.game == request.narrative.game
    entry = first.package.media_manifest[0]
    assert entry.sha256 == request.evidence.evidence.assets[0].derivative_sha256
    assert entry.relative_path.endswith(".svg") and entry.relative_path.startswith("media/")
    assert not (tmp_path / "runtime.json").exists()


@pytest.mark.parametrize("tamper", ["project", "version", "hash", "identity"])
def test_local_catalog_requires_registered_identity(tamper: str) -> None:
    reference = asset_reference()
    changes = {
        "project": {"project_id": "another-project"},
        "version": {"version": "999"},
        "hash": {"sha256": "0" * 64},
        "identity": {"resource_id": "another-asset"},
    }
    altered = updated(reference, **changes[tamper])
    with pytest.raises(ServiceError) as failure:
        VerifiedResourceReader(LocalResourceReader(FIXTURES)).read(altered, 10000)
    assert failure.value.code == "RESOURCE_NOT_REGISTERED"


@pytest.mark.parametrize("tamper", ["identity", "bytes", "size"])
def test_injected_reader_cannot_bypass_verification(tamper: str) -> None:
    class BrokenReader:
        def read(self, reference: ResourceReference, maximum_bytes: int) -> ResourceData:
            identity = (
                updated(reference, project_id="another-project")
                if tamper == "identity"
                else reference
            )
            content = (
                (FIXTURES / "synthetic-hatch.svg").read_bytes()
                if tamper == "identity"
                else b"invalid"
            )
            if tamper == "size":
                content = b"x" * (maximum_bytes + 1)
            return ResourceData(identity, content, "image/svg+xml")

    with pytest.raises(ServiceError) as failure:
        VerifiedResourceReader(BrokenReader()).read(asset_reference(), 10000)
    assert (
        failure.value.code
        == {
            "identity": "RESOURCE_IDENTITY_MISMATCH",
            "bytes": "MEDIA_CHANGED",
            "size": "RESOURCE_TOO_LARGE",
        }[tamper]
    )


@pytest.mark.parametrize(
    "path", ["../outside", "/etc/passwd", "nested/../outside", "path%2Ffile", "dir\\file"]
)
def test_local_reader_rejects_path_escape(path: str) -> None:
    with pytest.raises(ServiceError) as failure:
        LocalResourceReader(FIXTURES).file(path, 1000)
    assert failure.value.code == "RESOURCE_PATH_INVALID"


@pytest.mark.parametrize("kind", ["symlink", "parent-symlink", "pipe", "oversized"])
def test_local_reader_bounds_regular_files(tmp_path: Path, kind: str) -> None:
    path = "input"
    if kind == "symlink":
        (tmp_path / path).symlink_to(FIXTURES / "synthetic-hatch.svg")
    elif kind == "parent-symlink":
        (tmp_path / "linked").symlink_to(FIXTURES, target_is_directory=True)
        path = "linked/synthetic-hatch.svg"
    elif kind == "pipe":
        os.mkfifo(tmp_path / path)
    else:
        (tmp_path / path).write_bytes(b"x" * 101)
    with pytest.raises(ServiceError) as failure:
        LocalResourceReader(tmp_path).file(path, 100)
    assert failure.value.code == (
        "RESOURCE_TOO_LARGE"
        if kind == "oversized"
        else "RESOURCE_UNAVAILABLE"
        if kind == "pipe"
        else "RESOURCE_PATH_INVALID"
    )


def test_source_uri_is_metadata_not_an_unrestricted_file_path() -> None:
    source = json.loads((FIXTURES / "evidence.json").read_bytes())["sources"][0]
    reference = ResourceReference(
        project_id="fixture-project",
        resource_id=source["source_id"],
        version=source["version"],
        kind="source",
        sha256=source["file_sha256"],
        source_uri=source["uri"],
    )
    reader = VerifiedResourceReader(LocalResourceReader(FIXTURES))
    assert reader.read(reference, 10000).content == (FIXTURES / "synthetic-source.txt").read_bytes()
    with pytest.raises(ServiceError) as failure:
        reader.read(updated(reference, source_uri="local:/etc/passwd"), 10000)
    assert failure.value.code == "RESOURCE_NOT_REGISTERED"


def test_local_catalog_can_bind_an_opaque_source_uri_without_engine_uri_branches(
    tmp_path: Path,
) -> None:
    catalog = json.loads((FIXTURES / "resources.json").read_bytes())
    catalog["sources"][0]["uri"] = "registered-source:opaque-id"
    (tmp_path / "resources.json").write_text(json.dumps(catalog))
    shutil.copyfile(FIXTURES / "synthetic-source.txt", tmp_path / "synthetic-source.txt")
    source = catalog["sources"][0]
    reference = ResourceReference(
        project_id=source["project_id"],
        resource_id=source["source_id"],
        kind="source",
        version=source["version"],
        sha256=source["sha256"],
        source_uri=source["uri"],
    )
    assert VerifiedResourceReader(LocalResourceReader(tmp_path)).read(reference, 10000).content
