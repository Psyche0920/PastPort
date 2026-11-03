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
