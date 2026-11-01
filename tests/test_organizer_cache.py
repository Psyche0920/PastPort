"""Default cache selection is a complete lineage, not a collection of filenames."""

import hashlib
import json
from pathlib import Path

import pytest
from test_organizer import setup

from pastport.adapters.organizer_store import OrganizerStore
from pastport.application.models import ServiceError
from pastport.application.organizer import OrganizerService
from pastport.application.organizer_cache import (
    CachedBundleValidator,
    CachedFile,
    CachedWorld,
    OrganizerCachedBundle,
)
from pastport.domain.common import CanonicalSerializer
from pastport.domain.game_making import GameMakingRequest
from pastport.domain.organizer import OrganizerCatalog, OrganizerSource
from pastport.domain.story_inputs import EnvironmentSpatialRevision


def bundle_fixture(root: Path):
    settings, production = setup(root)
    request = GameMakingRequest.model_validate_json((root / "request.json").read_bytes())
    directory = root / "cache"
    directory.mkdir()

    def file(name: str, content: bytes):
        path = directory / name
        path.write_bytes(content)
        return CachedFile(path=path, sha256=hashlib.sha256(content).hexdigest())

    original = CachedFile(
        path=request.original_pdf,
        sha256=hashlib.sha256(request.original_pdf.read_bytes()).hexdigest(),
    )
    photo = file("photo.jpg", b"synthetic photo")
    mapping = file("mapping.pdf", b"%PDF-synthetic mapping")
    objects = file("objects.json", b"{}")
    tour = file("tour.html", b"synthetic tour")
    photo_manifest = file(
        "inputs.json",
        json.dumps(
            {
                "source": {"sha256": original.sha256, "pages": 1},
                "photos": [{"sha256": photo.sha256}],
            }
        ).encode(),
    )
    native = file(
        "import.json",
        json.dumps(
            {
                "source_pdf_sha256": original.sha256,
                "input_pdf_sha256": mapping.sha256,
                "input_vr_sha256": tour.sha256,
                "upstream_objects_sha256": objects.sha256,
            }
        ).encode(),
    )
    environment = json.loads(request.environment.read_text())
    environment["import_manifest_sha256"] = native.sha256
    environment["views"].append(
        dict(environment["views"][0], view_id="two", source_view_id="original-two")
    )
    # The fixture tests lineage only; geometry admission remains in the production port.
    environment["spatial_profile"] = "panorama_positions_only"
    environment["metric_spatial"] = None
    request.environment.write_text(json.dumps(environment))
    worlds = []
    for scene in ("one", "two"):
        panorama = file(scene + "-pano.jpg", b"synthetic pano")
        for view in environment["views"]:
            if view["view_id"] == scene:
                view["panorama_sha256"] = panorama.sha256
        attachment = file(
            scene + "-attachment.json",
            json.dumps({"source_scene_id": scene, "source_import_sha256": native.sha256}).encode(),
        )
        worlds.append(
            CachedWorld(
                attachment=attachment,
                collider=file(scene + ".glb", b"glTF"),
                splat=file(scene + ".spz", b"splat"),
                source_panorama=panorama,
            )
        )
    spatial = EnvironmentSpatialRevision.model_validate_json(
        json.dumps({key: environment[key] for key in ("entry_view_id", "views", "positions")})
    )
    environment["spatial_revision"] = CanonicalSerializer.digest(spatial)
    request.environment.write_text(json.dumps(environment))
    result = OrganizerCachedBundle(
        request_sha256=CanonicalSerializer.digest(request),
        original_pdf=original,
        photo_manifest=photo_manifest,
        photos=(photo,),
        mapping_pdf=mapping,
        objects=objects,
        tour=tour,
        native_import=native,
        worlds=tuple(worlds),
    )
    path = root / "bundle.json"
    path.write_text(result.model_dump_json())
    return request, result, path


def test_complete_bundle_validates_all_source_links(tmp_path):
    request, bundle, path = bundle_fixture(tmp_path)
    assert CachedBundleValidator.validate(path, request) == bundle


def test_a_different_pdf_cache_is_not_accepted_even_with_same_photo(tmp_path):
    request, bundle, path = bundle_fixture(tmp_path)
    body = json.loads(bundle.photo_manifest.path.read_text())
    body["source"]["sha256"] = "f" * 64
    bundle.photo_manifest.path.write_text(json.dumps(body))
    updated = bundle.model_copy(
        update={
            "photo_manifest": CachedFile(
                path=bundle.photo_manifest.path,
                sha256=hashlib.sha256(bundle.photo_manifest.path.read_bytes()).hexdigest(),
            )
        }
    )
    path.write_text(updated.model_dump_json())
    with pytest.raises(ServiceError, match="同一套缓存"):
        CachedBundleValidator.validate(path, request)


def test_one_changed_file_invalidates_whole_bundle(tmp_path):
    request, bundle, path = bundle_fixture(tmp_path)
    bundle.mapping_pdf.path.write_bytes(b"%PDF-another mapping")
    with pytest.raises(ServiceError, match="文件改变"):
        CachedBundleValidator.validate(path, request)


def test_default_without_complete_bundle_is_rejected(tmp_path):
    settings, production = setup(tmp_path)
    catalog = OrganizerCatalog(
        sources=(
            OrganizerSource(
                source_id="default",
                title="Incomplete",
                project_id="fixture-project",
                request_file=tmp_path / "request.json",
                is_default=True,
            ),
        )
    )
    with pytest.raises(ValueError, match="complete registered cache"):
        OrganizerService(OrganizerStore(tmp_path / "store"), catalog, production)


def test_missing_saved_story_stops_complete_cache_reuse(tmp_path):
    request, bundle, path = bundle_fixture(tmp_path)
    (request.saved_story_run / "narrative-draft.json").unlink()
    with pytest.raises(ServiceError, match="缺少已保存故事"):
        CachedBundleValidator.validate(path, request)
