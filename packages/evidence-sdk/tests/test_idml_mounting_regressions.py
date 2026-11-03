import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pastport_evidence.adapters.assets import LocalAssetStore
from pastport_evidence.adapters.identity import SQLiteSceneRepository
from pastport_evidence.application.idml_handoff import DistinctIdentityReview, IDMLEnvironmentHandoff
from pastport_evidence.application.idml_workflow import IDMLPhotoWorkflow
from pastport_evidence.application.photos import PhotoRecognitionService, PhotoRegistrar
from pastport_evidence.domain.idml import IDMLCompiledObject, IDMLMatchResult
from pastport_evidence.domain.photos import PhotoInspection, PhotoInspectionRequest, PhotoInventory, PhotoObservation, ScenePhoto
from pastport_evidence.domain.recognition import PixelRegion, SceneEntity
from pastport_evidence.domain.execution import SubscriptionGrant
from pastport_evidence.domain.idml import IDMLDocument, IDMLExactCitation, IDMLParagraph, IDMLStory


def material(tmp_path: Path) -> tuple[LocalAssetStore, tuple[ScenePhoto, ...]]:
    assets = LocalAssetStore(tmp_path / 'assets')
    paths = []
    for i in range(6):
        path = tmp_path / f'photo-{i}.png'
        Image.new('RGB', (16, 16), (i * 30, 0, 0)).save(path)
        paths.append(path)
    return assets, PhotoRegistrar(assets).register('fixture', tuple(paths))


def test_inventory_covers_later_photos_after_twenty_and_resumes_without_calls(tmp_path: Path) -> None:
    assets, photos = material(tmp_path)
    class Inspector:
        calls = 0
        inspected: set[str] = set()
        def inspect_photos(self, request: PhotoInspectionRequest) -> PhotoInspection:
            self.calls += 1
            self.inspected.update(p.photo_id for p in request.photos)
            entities = [] if request.phase == 'recheck' else [
                {'proposal_id':f'p{self.calls}-{i}', 'label':f'object {i}', 'category':'fixture',
                 'distinguishing_features':[str(i)]} for i in range(12)]
            return PhotoInspection.model_validate_json(json.dumps({'entities':entities,
                'sightings':[{'target_ref':e['proposal_id'],'photo_id':request.photos[0].photo_id,
                    'region':{'top_left':{'x':0,'y':0},'bottom_right':{'x':4,'y':4}},
                    'basis':'Visible synthetic fixture'} for e in entities],
                'receipt_ref':f'fixture:{self.calls}'}))
    inspector = Inspector()
    run = tmp_path / 'runs' / 'one'
    run.mkdir(parents=True)
    service = PhotoRecognitionService(SQLiteSceneRepository(tmp_path/'identities.sqlite3'), inspector, assets, batch_size=2)
    result = service.run('fixture', photos, run, 'grant', 'model', 6)
    assert len(result.entities) == 36
    assert inspector.inspected == {p.photo_id for p in photos}
    assert service.run('fixture', photos, run, 'grant', 'model', 6) == result
    assert inspector.calls == 6
    sheets = IDMLPhotoWorkflow._modern_sheets(result, assets, run)
    assert len(sheets) == 3
    for sheet in sheets:
        with Image.open(sheet) as image:
            assert image.width == 1600 and image.height <= 1280


def test_overlap_requires_inventory_bound_distinct_identity_review(tmp_path: Path) -> None:
    assets, photos = material(tmp_path)
    entities = tuple(SceneEntity(object_id=f'object-{i}',display_number=i,label=f'object {i}',
        category='fixture',distinguishing_features=(str(i),)) for i in (7,8))
    inventory = PhotoInventory(photos=photos,entities=entities,observations=tuple(
        PhotoObservation(object_id=e.object_id,photo=photos[0],crop=photos[0].image,
            region=PixelRegion.model_validate_json('{"top_left":{"x":0,"y":0},"bottom_right":{"x":12,"y":12}}'),
            identity_state='confirmed',basis='Synthetic foreground/background') for e in entities))
    result = IDMLMatchResult(source_sha256='a'*64,objects=tuple(
        IDMLCompiledObject(object_id=e.object_id,status='matched',historical_name='Same subject',
            relationship='functional_analogy',image_id=None,image_role='text_evidence',introduction='Fixture',
            citations=(),rationale='Fixture',limitations=(),review_reason='Fixture') for e in entities),receipt_refs=())
    assert IDMLEnvironmentHandoff.identity_conflicts(result,inventory) == {'object-7':{8},'object-8':{7}}
    review = DistinctIdentityReview(inventory_sha256=hashlib.sha256(inventory.model_dump_json().encode()).hexdigest(),
        object_ids=('object-7','object-8'),basis='Different physical entities across views')
    assert IDMLEnvironmentHandoff.identity_conflicts(result,inventory,(review,)) == {}
    with pytest.raises(ValueError,match='current photo inventory'):
        IDMLEnvironmentHandoff.identity_conflicts(result,inventory,(review.model_copy(update={'inventory_sha256':'b'*64}),))


def test_insufficient_photo_budget_stops_before_any_transport_call(tmp_path: Path) -> None:
    material(tmp_path)
    document = IDMLDocument(source_filename="source.idml", source_sha256="a" * 64,
                            stories=(), pages=(), frames=(), images=(), associations=(), warnings=())
    from unittest.mock import Mock
    transport = Mock()
    with patch("pastport_evidence.application.idml_workflow.IDMLDocumentReader.read", return_value=document):
        with pytest.raises(ValueError, match="at least 5 authorized calls"):
            IDMLPhotoWorkflow(transport).run(tmp_path / "source.idml", tmp_path / "links",
                tmp_path, tmp_path / "workspace", SubscriptionGrant(project_id="fixture", grant_ref="grant", max_calls=4))
    transport.execute.assert_not_called()


def test_same_historical_name_keeps_distinct_objects_and_pending_inventory(tmp_path: Path) -> None:
    assets, photos = material(tmp_path)
    source = tmp_path / "source.idml"
    source.write_bytes(b"synthetic-source")
    links = tmp_path / "links"
    links.mkdir()
    text = "Fixture historical subject."
    document = IDMLDocument(source_filename="source.idml", source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        stories=(IDMLStory(story_id="s", member="Stories/s.xml", text=text, paragraphs=(
            IDMLParagraph(index=0, start=0, end=len(text), text=text, style="body"),)),),
        pages=(), frames=(), images=(), associations=(), warnings=())
    entities = tuple(SceneEntity(object_id=f"object-{i}", display_number=i, label=f"object {i}",
        category="fixture", distinguishing_features=(str(i),)) for i in (7, 8, 13))
    inventory = PhotoInventory(photos=photos, entities=entities, observations=tuple(
        PhotoObservation(object_id=e.object_id, photo=photos[index], crop=photos[index].image,
            region=PixelRegion.model_validate_json('{"top_left":{"x":0,"y":0},"bottom_right":{"x":12,"y":12}}'),
            identity_state="confirmed", basis="Distinct synthetic physical entity") for index, e in enumerate(entities)))
    citation = IDMLExactCitation(story_id="s", member="Stories/s.xml", paragraph_index=0, start=0, end=len(text), quote=text)
    result = IDMLMatchResult(source_sha256=document.source_sha256, objects=tuple(
        IDMLCompiledObject(object_id=e.object_id, status="requires_review" if e.display_number == 13 else "matched",
            historical_name="Same historical subject", relationship="functional_analogy", image_id=None,
            image_role="text_evidence", introduction=text, citations=(citation,), rationale="Fixture analogy",
            limitations=("Not physical identity",), review_reason="Fixture") for e in entities), receipt_refs=())
    output = tmp_path / "handoff"
    IDMLEnvironmentHandoff().write(source, links, document, result, inventory, assets, output)
    assert [row["number"] for row in json.loads((output / "objects.json").read_text())["objects"]] == [7, 8]
    assert len(json.loads((output / "idml-review-inventory.json").read_text())) == 3
    coverage = json.loads((output / "mapping-coverage.json").read_text())
    assert coverage["matched"] == 2 and coverage["requires_review"] == 1
    assert coverage["saved_3d_anchors"] == 0 and coverage["mounting_complete"] is False
