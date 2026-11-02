"""Candidate matching is followed by exact source verification, without another model call."""
import io
from pathlib import Path
from PIL import Image

from pastport_evidence.adapters.assets import LocalAssetStore
from pastport_evidence.adapters.execution import SubscriptionExecutor
from pastport_evidence.application.evidence import CorpusIndex
from pastport_evidence.application.preparation import MappingPreparation, DocumentDraft
from pastport_evidence.domain.build import MappingInventory, PDFMatchPage, PDFObjectMatch
from pastport_evidence.domain.evidence import HistoricalSubject
from pastport_evidence.domain.execution import SubscriptionGrant
from pastport_evidence.domain.pdf import RegisteredPDF, PDFPageContent, PDFExtractionStatus
from pastport_evidence.domain.recognition import RecognitionResult, SceneEntity


class NoDispatch:
    def execute(self, request, timeout_seconds):
        raise AssertionError('Exact source verification must not issue a model call')


def test_original_quote_is_preserved_without_semantic_approval_or_model_call(tmp_path: Path) -> None:
    assets = LocalAssetStore(tmp_path/'assets')
    source = assets.register_bytes('p', b'%PDF-fixture', 'application/pdf', 100).reference
    buffer = io.BytesIO()
    Image.new('RGB',(20,20),'white').save(buffer,format='JPEG')
    image = assets.register_bytes('p',buffer.getvalue(),'image/jpeg',10000).reference
    quote='The main iwan was used as a classroom.'
    page=PDFPageContent(page_index=0,page_width=20.0,page_height=20.0,original_text=quote,normalized_text=quote,text_lines=(),image_regions=(),extraction_status=PDFExtractionStatus.TEXT_EXTRACTED,rendered_page=image)
    document=RegisteredPDF(source=source,page_count=1,pages=(page,),extractor_version='fixture')
    passage=CorpusIndex(document).passages[0]
    entity=SceneEntity(object_id='desk',display_number=1,label='Modern desk',category='table',distinguishing_features=('round top',))
    recognition=RecognitionResult(entities=(entity,),calls_used=1,gaps=())
    candidate=PDFObjectMatch(object_id='desk',subject=HistoricalSubject(subject_id='classroom',label='Historical classroom'),page_index=0,passage_ids=(passage.passage_id,),relationship='substitution',target_scale='object',source_scale='space',source_image_role='text_evidence',story_support='documented_activity',basis='Narrative proxy only, not the same physical object')
    inventory=MappingInventory(matches=(candidate,),pages=(PDFMatchPage(page_index=0,image=image,width=20,height=20,passages=(passage,)),),receipt_refs=('existing-match',),gaps=())
    artifacts=tmp_path/'run';artifacts.mkdir()
    for name,value in [('pdf.json',document),('recognition.json',recognition),('mapping.json',inventory)]:
        (artifacts/name).write_text(value.model_dump_json())
    grant=SubscriptionGrant(project_id='p',grant_ref='g')
    executor=SubscriptionExecutor(tmp_path/'ledger.sqlite3',grant,NoDispatch())
    service=MappingPreparation(tmp_path,artifacts,grant,'demo_substitution','test',assets,executor,mapping_prompt_version='v2',indexed_retrieval=True)
    service.evidence()
    draft=DocumentDraft.model_validate_json((artifacts/'review-draft.json').read_bytes())
    evidence=draft.objects[0].source_evidence
    assert evidence is not None and evidence.original_quote==quote
    assert evidence.passages==(passage,)
    assert evidence.claims==() and evidence.image_association_state=='candidate'
    assert draft.objects[0].draft.introduction==quote
    assert executor.remaining_calls()==grant.max_calls
    service.evidence()
    assert executor.remaining_calls()==grant.max_calls
