"""Raw-file boundaries and derived observations remain local and unapproved."""
import gzip
import json
import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from pastport_matched_environment.application.raw_scene import RawSceneGeometry, RawScenePreparation


def inputs(root: Path) -> tuple[Path, Path]:
    splat=root/'fixture.spz'
    splat.write_bytes(gzip.compress(struct.pack('<4I',0x5053474E,3,3,0)))
    mesh=root/'fixture.ply'
    header=b'ply\nformat binary_little_endian 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n'
    mesh.write_bytes(header+struct.pack('<9f',0,0,0,1,0,0,0,0,1)+struct.pack('<B3i',3,0,1,2))
    return splat,mesh


class Capture:
    def __init__(self, blank: bool=False) -> None:
        self.calls=0
        self.blank=blank

    def capture(self, output: Path, assets: Path, log: Path) -> None:
        self.calls+=1
        faces=[]
        for i,direction in enumerate(((0,0,-1),(1,0,0),(0,0,1),(-1,0,0),(0,1,0),(0,-1,0))):
            f=np.asarray(direction,dtype=float)
            up=np.asarray((0,0,-direction[1]) if direction[1] else (0,1,0),dtype=float)
            right=np.cross(f,up)
            matrix=np.eye(4)
            matrix[:3,0]=right
            matrix[:3,1]=np.cross(right,f)
            matrix[:3,2]=-f
            matrix[:3,3]=(0,1.6,0)
            with Image.new('RGB',(32,32),(20*i,80,120)) as image:
                if not self.blank:ImageDraw.Draw(image).rectangle((0,0,15,31),fill='white')
                else:image.paste((0,0,0),(0,0,32,32))
                image.save(output/f'face-{i}.png')
            faces.append({'file':f'face-{i}.png','matrix':matrix.flatten(order='F').tolist()})
        (output/'capture.json').write_text(json.dumps({'schema':'pastport.raw-capture/1','origin':[0,1.6,0],'faces':faces}))


def test_existing_scene_becomes_one_bound_observation_without_generation(tmp_path: Path) -> None:
    splat,mesh=inputs(tmp_path)
    original=splat.read_bytes()
    capture=Capture()
    preparation=RawScenePreparation(capture)
    output=tmp_path/'prepared'
    tour=preparation.prepare(splat,mesh,output)
    scene=json.loads((output/'scene/scene.json').read_text())
    data=json.loads(tour.read_text().split('application/json">',1)[1].split('</script>',1)[0])
    assert scene['kind']=='imported_3d' and scene['acceptance']=='pending_manual_review'
    assert len(data['scenes'])==1 and data['scenes'][0]['view']['fov']==90
    assert (output/'scene/scene.spz').read_bytes()==original
    preparation.prepare(splat,mesh,output)
    assert capture.calls==1
    splat.write_bytes(gzip.compress(struct.pack('<4I',0x5053474E,3,4,0)))
    with pytest.raises(ValueError,match='Raw inputs changed'):
        preparation.prepare(splat,mesh,output)


def test_blank_observations_never_become_recognition_inputs(tmp_path: Path) -> None:
    splat,mesh=inputs(tmp_path)
    with pytest.raises(ValueError,match='blank'):
        RawScenePreparation(Capture(blank=True)).prepare(splat,mesh,tmp_path/'prepared')
    assert not (tmp_path/'prepared/scene/scene.json').exists()


@pytest.mark.parametrize("blank_faces", [(5,), (0,), (0, 1, 2, 3, 4)])
def test_partial_blank_capture_preserves_empty_directions_and_resumes(
    tmp_path: Path, blank_faces: tuple[int, ...],
) -> None:
    splat, mesh = inputs(tmp_path)
    capture = Capture()
    workspace = tmp_path / "prepared"
    scene = workspace / "scene"
    RawSceneGeometry().prepare(splat, mesh, scene)
    capture.capture(scene, tmp_path, workspace / "capture.log")
    for index in blank_faces:
        with Image.new("RGB", (32, 32), "black") as image:
            image.save(scene / f"face-{index}.png")
    before = {path.name: path.read_bytes() for path in scene.glob("face-*.png")}

    preparation = RawScenePreparation(capture)
    tour = preparation.prepare(splat, mesh, workspace)
    report = json.loads((scene / "capture-quality.json").read_text())
    assert [face["file"] for face in report["faces"] if not face["informative"]] == [
        f"face-{index}.png" for index in blank_faces
    ]
    assert tour.is_file() and (scene / "scene.json").is_file()
    assert before == {path.name: path.read_bytes() for path in scene.glob("face-*.png")}
    with Image.open(scene / "panorama.jpg") as panorama:
        # Cube-face centres in equirectangular coordinates, including both poles.
        centres = ((1024, 512), (1536, 512), (0, 512), (512, 512), (1024, 0), (1024, 1023))
        for index in blank_faces:
            assert max(panorama.getpixel(centres[index])) < 5
    panorama_bytes = (scene / "panorama.jpg").read_bytes()
    preparation.prepare(splat, mesh, workspace)
    assert capture.calls == 1
    assert (scene / "panorama.jpg").read_bytes() == panorama_bytes


def test_differently_coloured_uniform_faces_still_fail(tmp_path: Path) -> None:
    splat, mesh = inputs(tmp_path)
    workspace = tmp_path / "prepared"
    scene = workspace / "scene"
    RawSceneGeometry().prepare(splat, mesh, scene)
    capture = Capture(blank=True)
    capture.capture(scene, tmp_path, workspace / "capture.log")
    for index in range(6):
        with Image.new("RGB", (32, 32), (index * 40, 0, 0)) as image:
            image.save(scene / f"face-{index}.png")
    with pytest.raises(ValueError, match="All rendered views are blank"):
        RawScenePreparation(capture).prepare(splat, mesh, workspace)
    assert (scene / "capture-quality.json").is_file()
    assert not (scene / "panorama.jpg").exists()
    assert not (scene / "scene.json").exists()


@pytest.mark.parametrize('corruption',['truncated','invalid-index','non-triangle'])
def test_invalid_mesh_cannot_publish_registered_scene(tmp_path: Path,corruption: str) -> None:
    splat,mesh=inputs(tmp_path)
    raw=mesh.read_bytes()
    if corruption=='truncated':raw=raw[:-1]
    elif corruption=='invalid-index':raw=raw[:-13]+struct.pack('<B3i',3,0,1,99)
    else:raw=raw[:-13]+struct.pack('<B3i',4,0,1,2)
    mesh.write_bytes(raw)
    with pytest.raises(ValueError):RawSceneGeometry().prepare(splat,mesh,tmp_path/'prepared')
    assert not (tmp_path/'prepared').exists()


def test_admin_token_policy_disables_token_stop_but_keeps_call_ceiling(tmp_path: Path) -> None:
    from pastport_matched_environment.adapters.execution import SubscriptionExecutor
    from pastport_matched_environment.domain.execution import ExecutionInput, ExecutionOutput, ExecutionDenied, SubscriptionGrant
    class Transport:
        def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
            return ExecutionOutput(payload_json="{}",receipt_ref="r",thread_ref="t",turn_ref="u",input_tokens=10,output_tokens=10,total_tokens=20)
    grant = SubscriptionGrant(project_id="p",grant_ref="g",max_calls=2,max_recorded_tokens=1)
    executor = SubscriptionExecutor(tmp_path/'ledger.sqlite3',grant,Transport())
    request = ExecutionInput(project_id="p",grant_ref="g",model_id=grant.model_id,kind="environment_generation",prompt_version="v1",policy_version="test",instructions="test",payload_json="{}",output_schema_json="{}")
    executor.execute(request)
    assert executor.remaining_calls()==0
    (tmp_path/'no-token-threshold-authorized.txt').write_text('Explicit Admin authorization')
    assert executor.remaining_calls()==1
    assert executor.remaining_recorded_tokens() is None
    executor.execute(request.model_copy(update={"payload_json":'{"view":2}'}))
    assert executor.remaining_calls()==0
    with pytest.raises(ExecutionDenied):executor.execute(request.model_copy(update={"payload_json":'{"view":3}'}))


def test_raw_localization_views_cover_ceiling_and_floor_without_extra_image_slots(tmp_path: Path) -> None:
    from pastport_matched_environment.application.environment_build import EnvironmentRun
    from pastport_matched_environment.adapters.assets import LocalAssetStore
    from pastport_matched_environment.domain.tour import TourView
    from pastport_matched_environment.domain.geometry import SphericalPoint
    prepared=tmp_path/'prepared';(prepared/'panoramas').mkdir(parents=True)
    panorama=prepared/'panoramas/view-001.jpg'
    picture=Image.new('RGB',(64,32),'gray');draw=ImageDraw.Draw(picture)
    draw.rectangle((0,0,63,7),fill='red');draw.rectangle((0,24,63,31),fill='blue');picture.save(panorama)
    imported=tmp_path/'raw';(imported/'scene').mkdir(parents=True)
    (imported/'scene/raw-scene.json').write_text('{"schema_version":"pastport.raw-scene/1.0"}')
    assets=LocalAssetStore(tmp_path/'assets');reference=assets.register_file('fixture',panorama,'image/jpeg',100000).reference
    view=TourView(view_id='fixture',label='fixture',panorama=reference,revision=1,width=64,height=32,initial_position=SphericalPoint(yaw=0.0,pitch=0.0),links=())
    context=object.__new__(EnvironmentRun);context.tour_path=imported/'tour.html';context.prepared=prepared;context.run=tmp_path/'run';context.run.mkdir()
    paths,transforms=context.views(1,view)
    assert len(paths)==len(transforms)==7
    assert transforms[-2].center_pitch==80.0 and transforms[-1].center_pitch==-80.0
    with Image.open(paths[-2]) as top,Image.open(paths[-1]) as bottom:
        assert top.getpixel((512,512))[0]>200
        assert bottom.getpixel((512,512))[2]>200



def test_capture_origin_uses_observed_lower_floor_in_stepped_scene(tmp_path: Path) -> None:
    from numpy.typing import NDArray

    class SteppedGeometry(RawSceneGeometry):
        def ply(self, path: Path) -> tuple[NDArray[np.float32], NDArray[np.uint32]]:
            return (np.array([(0, 0, 0), (1, 0, 0), (0, 0, 1),
                              (10, 4, 20), (11, 4, 20), (10, 4, 21)], dtype=np.float32),
                    np.array([(0, 1, 2), (3, 4, 5)], dtype=np.uint32))

    origin = SteppedGeometry().capture_origin(tmp_path / "unused.ply", 4.0)
    assert origin == pytest.approx((10 + 1 / 3, 1.6, -(20 + 1 / 3)))


def test_capture_without_horizontal_floor_retains_provider_origin(tmp_path: Path) -> None:
    from numpy.typing import NDArray

    class WallGeometry(RawSceneGeometry):
        def ply(self, path: Path) -> tuple[NDArray[np.float32], NDArray[np.uint32]]:
            return (np.array([(0, 0, 0), (0, 1, 0), (0, 0, 1)], dtype=np.float32),
                    np.array([(0, 1, 2)], dtype=np.uint32))

    assert WallGeometry().capture_origin(tmp_path / "unused.ply", 4.0) == (0.0, 4.0, 0.0)
