"""No semantic verdict may bypass source identity, exact quotes or object coverage."""
from pathlib import Path
import pytest
from pastport_evidence.application.idml_matching import IDMLMatchCompiler, IDMLMatchingService, IDMLMatchRequest
from pastport_evidence.domain.idml import IDMLDocument, IDMLStory, IDMLParagraph, IDMLMatchBatch, IDMLMatchReviews
from pastport_evidence.domain.recognition import SceneEntity


def request() -> IDMLMatchRequest:
    text='Each room has a hearth. The chimneys collapsed in 1855.'
    return IDMLMatchRequest(source=IDMLDocument(source_filename='source.idml',source_sha256='a'*64,
        stories=(IDMLStory(story_id='s',member='Stories/s.xml',text=text,
            paragraphs=(IDMLParagraph(index=0,start=0,end=len(text),text=text,style='body'),)),),
        pages=(),frames=(),images=(),associations=(),warnings=()),objects=(
        SceneEntity(object_id='object-12',display_number=12,label='pipe',category='fixture',distinguishing_features=('silver',)),))


def batch(quote: str = 'Each room has a hearth.') -> IDMLMatchBatch:
    return IDMLMatchBatch.model_validate_json(__import__('json').dumps({'objects':[{
        'object_id':'object-12','status':'matched','historical_name':'Historical hearth',
        'relationship':'functional_analogy','image_id':None,'image_role':'text_evidence',
        'claims':[{'text':'每间房间设有炉灶。','citations':[{'story_id':'s','paragraph_index':0,'quote':quote}]}],
        'rationale':'Functional analogy only','limitations':['No object photograph'] }]}))


def reviews(verdict: str = 'confirmed') -> IDMLMatchReviews:
    return IDMLMatchReviews.model_validate_json(__import__('json').dumps({'objects':[{'object_id':'object-12','verdict':verdict,'reason':'Independent scope check'}]}))


def test_exact_source_offsets_and_introduction_are_separate_from_rationale() -> None:
    result=IDMLMatchCompiler().compile(request(),batch(),reviews(),('proposal','audit'))
    obj=result.objects[0]
    assert obj.status=='matched' and obj.introduction=='每间房间设有炉灶。'
    assert obj.citations[0].start==0 and obj.citations[0].end==23
    assert result.historical_approval is False


def test_uncertain_match_is_not_accepted_as_success() -> None:
    result=IDMLMatchCompiler().compile(request(),batch(),reviews('uncertain'),())
    assert result.objects[0].status=='requires_review'


@pytest.mark.parametrize('corruption',['quote','identity','paragraph','image'])
def test_invalid_model_binding_is_rejected(corruption: str) -> None:
    candidate=batch()
    obj=candidate.objects[0]
    if corruption=='quote':candidate=batch('A fabricated historical quotation.')
    elif corruption=='identity':candidate=candidate.model_copy(update={'objects':(obj.model_copy(update={'object_id':'wrong'}),)})
    elif corruption=='paragraph':
        claim=obj.claims[0];citation=claim.citations[0].model_copy(update={'paragraph_index':99})
        candidate=candidate.model_copy(update={'objects':(obj.model_copy(update={'claims':(claim.model_copy(update={'citations':(citation,)}),)}),)})
    else:candidate=candidate.model_copy(update={'objects':(obj.model_copy(update={'image_id':'unavailable'}),)})
    with pytest.raises(ValueError):IDMLMatchCompiler().compile(request(),candidate,reviews(),())


def test_resuming_same_input_reuses_results_but_changed_input_cannot_read_them(tmp_path: Path) -> None:
    class Gateway:
        calls=0
        def propose(self, req, images):self.calls+=1;return batch(),'proposal'
        def audit(self, req, images):self.calls+=1;return reviews(),'audit'
    gateway=Gateway();service=IDMLMatchingService(gateway)
    persist=lambda path,text:path.write_text(text)
    first=service.run(request(),(),tmp_path,persist)
    assert service.run(request(),(),tmp_path,persist)==first and gateway.calls==2
    changed=request().model_copy(update={'source':request().source.model_copy(update={'source_sha256':'b'*64})})
    with pytest.raises(ValueError,match='different inputs'):service.run(changed,(),tmp_path,persist)
    assert gateway.calls==2


def test_invalid_proposal_stops_before_spending_independent_audit(tmp_path: Path) -> None:
    class Gateway:
        audit_calls=0
        def propose(self, req, images):return batch('Not in the source.'),'proposal'
        def audit(self, req, images):self.audit_calls+=1;return reviews(),'audit'
    gateway=Gateway()
    with pytest.raises(ValueError):IDMLMatchingService(gateway).run(request(),(),tmp_path,lambda p,t:p.write_text(t))
    assert gateway.audit_calls==0


def test_new_identity_policy_excludes_analogy_and_requires_visual_source() -> None:
    from pastport_evidence.domain.idml import IDMLImage

    compiler = IDMLMatchCompiler(strict_identity=True)
    legacy_proposal = batch()
    result = compiler.compile(request(), legacy_proposal, reviews(), ())
    assert result.objects[0].status == 'unmatched'
    assert result.objects[0].historical_name is None
    assert result.objects[0].relationship is None
    assert result.objects[0].introduction == ''
    same = legacy_proposal.objects[0].model_copy(update={'relationship': 'same_object'})
    pending = compiler.compile(request(), legacy_proposal.model_copy(update={'objects': (same,)}), reviews(), ())
    assert pending.objects[0].status == 'requires_review'
    image = IDMLImage(image_id='image-1', link_id='link-1', filename='chair.png', spread='spread',
        group_id=None, bounds=None, page_id=None, link_state='available', sha256='b' * 64)
    actual = request().model_copy(update={'source': request().source.model_copy(update={'images': (image,)})})
    same_with_image = same.model_copy(update={'image_id': 'image-1', 'image_role': 'object_image'})
    proposal = legacy_proposal.model_copy(update={'objects': (same_with_image,)})
    assert compiler.compile(actual, proposal, reviews(), ()).objects[0].status == 'matched'
    assert compiler.compile(actual, proposal, reviews('uncertain'), ()).objects[0].status == 'requires_review'


def test_new_and_legacy_gateway_send_separate_policies_and_identity_schema() -> None:
    import json
    from types import SimpleNamespace
    from pastport_evidence.adapters.idml_matching import MeteredIDMLMatchGateway
    from pastport_evidence.domain.execution import SubscriptionGrant

    class Executor:
        grant = SubscriptionGrant(project_id='fixture', grant_ref='fixture', max_calls=4)
        def __init__(self): self.requests = []
        def remaining_calls(self): return 4
        def execute(self, request):
            self.requests.append(request)
            return SimpleNamespace(payload_json=batch().model_dump_json(), receipt_ref='receipt')

    old = Executor()
    MeteredIDMLMatchGateway(old, policy='v1').propose(request(), ())
    current = Executor()
    MeteredIDMLMatchGateway(current, policy='v2').propose(request(), ())
    old_request, new_request = old.requests[0], current.requests[0]
    assert old_request.prompt_version == 'idml_mapping_v1'
    assert new_request.prompt_version == 'idml_mapping_v2'
    assert 'functional' in old_request.instructions
    assert 'same_object' in new_request.instructions
    old_schema, new_schema = json.loads(old_request.output_schema_json), json.loads(new_request.output_schema_json)
    def relationship_values(schema):
        return schema['$defs']['IDMLObjectMatch']['properties']['relationship']['anyOf'][0]['enum']
    assert 'same_object' not in relationship_values(old_schema)
    assert relationship_values(new_schema) == ['same_object']
    tolerant = Executor()
    MeteredIDMLMatchGateway(tolerant, policy='v3').propose(request(), ())
    tolerant_request = tolerant.requests[0]
    assert tolerant_request.prompt_version == 'idml_mapping_v3'
    assert relationship_values(json.loads(tolerant_request.output_schema_json)) == ['same_object']
    assert 'minor detail' in tolerant_request.instructions
    calibrated = Executor()
    MeteredIDMLMatchGateway(calibrated, policy='v4').propose(request(), ())
    calibrated_request = calibrated.requests[0]
    assert calibrated_request.prompt_version == 'idml_mapping_v4'
    assert relationship_values(json.loads(calibrated_request.output_schema_json)) == ['same_object']


def test_unmatched_without_image_does_not_fail_identity_preflight() -> None:
    obj = batch().objects[0].model_copy(update={
        'status': 'unmatched', 'historical_name': None, 'relationship': None,
        'claims': (), 'image_id': None, 'image_role': 'object_image',
    })
    result = IDMLMatchCompiler(strict_identity=True).compile(
        request(), IDMLMatchBatch(objects=(obj,)), reviews('uncertain'), ())
    assert result.objects[0].status == 'unmatched'
    assert result.objects[0].image_role == 'text_evidence'
    assert result.objects[0].image_id is None


def test_matched_object_image_still_requires_an_image_id() -> None:
    obj = batch().objects[0].model_copy(update={
        'relationship': 'same_object', 'image_id': None, 'image_role': 'object_image',
    })
    with pytest.raises(ValueError, match='photograph cannot be invented'):
        IDMLMatchCompiler(strict_identity=True).compile(
            request(), IDMLMatchBatch(objects=(obj,)), reviews(), ())
