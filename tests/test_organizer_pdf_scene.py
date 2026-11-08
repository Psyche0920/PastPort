"""General PDF admission uses real scene evidence and preserves requested stage scope."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_organizer import await_job, headers
from test_organizer_inputs import app_inputs, upload

from pastport.adapters.organizer_native import NativeWorldSet, SDKUploadedInputPreparer
from pastport.application.models import ServiceError
from pastport.domain.organizer_inputs import NativeInputRequest, UploadedAsset, UploadedProductionStart, UploadRole
from pastport_matched_environment.application.raw_scene import (
    CaptureQualityReport, CapturedFaceQuality, RawSceneReceipt,
)


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def captures(tmp_path: Path) -> tuple[Path, Path]:
    imported = tmp_path / 'raw-scene'
    scene = imported / 'scene'
    scene.mkdir(parents=True)
    (scene / 'capture.json').write_text('{"schema":"fixture-capture"}')
    faces: list[CapturedFaceQuality] = []
    for index in range(6):
        file = scene / f'face-{index}.png'
        with Image.new('RGB', (16, 16), 'red') as image:
            image.putpixel((0, 0), (0, 0, 0))
            image.save(file)
        faces.append(CapturedFaceQuality(
            file=file.name, sha256=digest(file), maximum_channel_std=20,
            informative=index < 2,
        ))
    quality = CaptureQualityReport(
        capture_sha256=digest(scene / 'capture.json'), faces=tuple(faces),
    )
    (scene / 'capture-quality.json').write_text(quality.model_dump_json())
    receipt = RawSceneReceipt(
        splat_sha256='a' * 64, mesh_sha256='b' * 64, collider_sha256='c' * 64,
        splat_version=2, splat_count=10, vertex_count=3, triangle_count=1,
        minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0), ground_plane_offset=0.0,
    )
    (scene / 'raw-scene.json').write_text(receipt.model_dump_json())
    output = tmp_path / 'output'
    output.mkdir()
    return imported, output


def test_derived_views_preserve_source_hashes_and_exclude_empty_faces(tmp_path: Path) -> None:
    imported, output = captures(tmp_path)
    folder = SDKUploadedInputPreparer._scene_observations(imported, output)
    assert sorted(f.name for f in folder.iterdir()) == ['face-0.png', 'face-1.png']
    provenance = json.loads((output / 'derived-scene-photos.json').read_text())
    assert provenance['origin'] == 'rendered_3d_not_field_photographs'
    assert provenance['source_splat_sha256'] == 'a' * 64
    assert provenance['source_mesh_sha256'] == 'b' * 64
    before = (output / 'derived-scene-photos.json').read_bytes()
    assert SDKUploadedInputPreparer._scene_observations(imported, output) == folder
    assert (output / 'derived-scene-photos.json').read_bytes() == before


@pytest.mark.parametrize('target', ['capture.json', 'face-0.png', 'saved-copy'])
def test_changed_rendered_evidence_is_rejected(tmp_path: Path, target: str) -> None:
    imported, output = captures(tmp_path)
    folder = SDKUploadedInputPreparer._scene_observations(imported, output)
    path = folder / 'face-0.png' if target == 'saved-copy' else imported / 'scene' / target
    path.write_bytes(b'changed fixture')
    with pytest.raises(ServiceError) as stopped:
        SDKUploadedInputPreparer._scene_observations(imported, output)
    assert stopped.value.code == 'SCENE_CAPTURE_CHANGED'


def test_entirely_blank_capture_stops_before_evidence(tmp_path: Path) -> None:
    imported, output = captures(tmp_path)
    report = imported / 'scene/capture-quality.json'
    quality = CaptureQualityReport.model_validate_json(report.read_bytes())
    report.write_text(quality.model_copy(update={
        'faces': tuple(face.model_copy(update={'informative': False}) for face in quality.faces),
    }).model_dump_json())
    with pytest.raises(ServiceError) as stopped:
        SDKUploadedInputPreparer._scene_observations(imported, output)
    assert stopped.value.code == 'SCENE_CAPTURE_EMPTY'
    assert not (output / 'derived-scene-photos').exists()


@pytest.mark.parametrize("content", [
    b"Ordinary historical prose without object numbers.",
    "PP-001\n石阶\n现场所见\n石阶通向\n地下通道。\n用途与来源\n来源待核对。".encode(),
    b"AB-001\nStaircase\nVISIBLE FEATURES\nStone steps.\nPhotographs:",
    b"",  # A scan has the same dispatch; OCR sufficiency is Evidence's responsibility.
])
def test_all_pdf_layouts_dispatch_to_one_shared_scene_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: bytes,
) -> None:
    service = SDKUploadedInputPreparer()
    assets: list[UploadedAsset] = []
    roles: tuple[tuple[UploadRole, str], ...] = (
        ('original_pdf', '.pdf'), ('scene_splat', '.spz'), ('scene_mesh', '.ply'),
    )
    for role, suffix in roles:
        p = tmp_path / (role + suffix)
        p.write_bytes(b'%PDF-fixture\n' + content if role == 'original_pdf' else b'fixture')
        assets.append(UploadedAsset(file_id=role, role=role, filename=p.name, path=p, sha256=digest(p)))
    request = NativeInputRequest(
        project_id='fixture-project', owner_id='owner', job_id='general-pdf',
        entry_level='catalog3d', files=tuple(assets),
        options=UploadedProductionStart(authorize_model=True, stop_after='environment'),
        shared_player_assets=tmp_path,
    )
    calls: list[str] = []

    def shared(req: NativeInputRequest, inputs: Path, original: Path, out: Path) -> NativeWorldSet:
        assert req == request
        assert original.read_bytes() == assets[0].path.read_bytes()
        assert not any(a.role == 'photos' for a in req.files)
        calls.append('shared-evidence')
        raise ServiceError('TEST_SHARED_FLOW', 'Stop before external dispatch', 409)

    monkeypatch.setattr(service, '_raw_scene', shared)
    with pytest.raises(ServiceError) as stopped:
        service.prepare(request, tmp_path / 'job')
    assert stopped.value.code == 'TEST_SHARED_FLOW'
    assert calls == ['shared-evidence']


@pytest.mark.parametrize("custom_assets", [False, True])
def test_pdf_scene_explicit_environment_only_request_still_stops(
    tmp_path: Path, custom_assets: bool,
) -> None:
    app, production, preparation = app_inputs(tmp_path, custom_assets=custom_assets)
    with TestClient(app) as client:
        upload(client, 'catalog3d', ('original_pdf', 'scene_splat', 'scene_mesh'))
        plan = client.get('/organizer/api/materials/fixture-project', headers=headers()).json()['plan']
        assert plan['generation_connected']
        assert not plan['missing_roles']
        assert '原生制作资源尚未配置' not in plan['message']
        response = client.post('/organizer/api/materials/fixture-project/jobs',
                               headers=headers(), json={'authorize_model': True, 'stop_after': 'environment'})
        assert response.status_code == 202
        job = await_job(client, response.json()['job_id'])
        assert job['status'] == 'environment_ready'
        assert preparation.calls[0].options.stop_after == 'environment'
        assert not production.calls
        expected = tmp_path / ('material/museum' if custom_assets else 'server/organizer/player-assets')
        assert preparation.calls[0].shared_player_assets == expected
        assert expected.is_dir()
        if not custom_assets:
            assert not list(expected.iterdir())
