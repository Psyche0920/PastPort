"""Native IDML handoffs reuse localization and review without invoking PDF tools."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch
from PIL import Image
from pastport_matched_environment.application.idml_environment import IDMLEnvironmentWorkflow
from pastport_matched_environment.domain.execution import ExecutionOutput, SubscriptionGrant
from tests.test_environment_agent import sample_inputs


class Transport:
    def __init__(self):self.calls=[]
    def execute(self,request,timeout_seconds):
        self.calls.append(request);raw=json.loads(request.payload_json)
        if 'source_scene_id' not in raw:payload={'relations':[],'review_basis':'Explicit synthetic no-part fixture'}
        elif raw.get('proposals'):payload={'objects':[{'number':12,'verdict':'confirmed','reason':'Synthetic fixture point'}]}
        else:payload={'objects':[{'number':12,'status':'visible','projection_index':0,'center':[0.5,0.5],'basis':'Synthetic fixture point'}]}
        return ExecutionOutput(payload_json=json.dumps(payload),receipt_ref='fixture:receipt',thread_ref='fixture:thread',turn_ref='fixture:turn',input_tokens=1,output_tokens=1,total_tokens=2)


def test_idml_reaches_shared_native_review_without_pdf_parser(tmp_path: Path) -> None:
    _,tour=sample_inputs(tmp_path,'idml-fixture',1)
    (tmp_path/'scene').mkdir();(tmp_path/'scene/raw-scene.json').write_text('{"schema_version":"pastport.raw-scene/1.0"}')
    handoff=tmp_path/'handoff';media=handoff/'media';media.mkdir(parents=True)
    text='Each room has a hearth. The chimneys collapsed in 1855.'
    with ZipFile(handoff/'source.idml','w') as z:z.writestr('Stories/s.xml','<Story><Content>'+text+'</Content></Story>')
    shutil.copyfile(handoff/'source.idml',handoff/'input.idml')
    for filename in ('photo-01.jpg','history-12.png','text-unit-01.png'):
        Image.new('RGB',(100,100),'red').save(media/filename)
    shutil.copyfile(media/'history-12.png',handoff/'proxy-12.png')
    records={
        'objects.json':{'objects':[{'number':12,'object_id':'fixture-modern-12','name':'Fixture modern pipe','boundary':'Whole red fixture','history_id':'fixture-history','history':'Historical hearth','parent':'fixture-source','page':1,'image_page':None,'image_box':None,'image_role':'text_evidence','explanation':'Fixture analogy','proxy':'functional_analogy','limit':'Not real material','quote':text,'introduction':'历史炉灶与烟囱。','observations':[{'photo_number':1,'observation_status':'visible','region_normalized':[0.0,0.0,1.0,1.0],'basis':'Explicit fixture observation'}]}]},
        'inputs.json':{'input_page_count':1,'photos':[{'number':1,'path':'fixture-photo','sha256':hashlib.sha256((media/'photo-01.jpg').read_bytes()).hexdigest(),'oriented_size':[100,100]}]},
        'quote-regions.json':[{'number':12,'page':1,'normalized_text':text,'start':0,'end':len(text)}],
        'source-units.json':{'source_format':'idml','units':[{'unit_id':1,'text':text,'member':'Stories/s.xml','story_id':'s','start':0,'paragraph_index':0,'preview':'media/text-unit-01.png'}]},
    }
    for name,value in records.items():(handoff/name).write_text(json.dumps(value))
    original_run=__import__('subprocess').run
    def bounded_run(args,*positional,**kwargs):
        assert args[0] not in ('pdftoppm','pdftotext'),'IDML path invoked a PDF tool'
        return original_run(args,*positional,**kwargs)
    transport=Transport()
    grant=SubscriptionGrant(project_id='fixture',grant_ref='fixture-idml',max_calls=6,max_recorded_tokens=1000)
    with patch('subprocess.run',bounded_run):
        output=IDMLEnvironmentWorkflow(transport).run(handoff,tour,tmp_path/'workspace','idml-fixture',grant)
    assert len(transport.calls)==3
    manifest=json.loads((output/'import-manifest.json').read_text())
    assert manifest['source_format']=='idml' and (output/'source.idml').is_file()
    assert not (output/'source.pdf').exists()
    with sqlite3.connect(output/'pastport_matching.sqlite3') as db:
        assert db.execute('select original_path from documents').fetchone()[0]=='source.idml'
        assert db.execute('select content from vr_display_contents where object_id=12').fetchone()[0]=='历史炉灶与烟囱。'
    IDMLEnvironmentWorkflow(transport).run(handoff,tour,tmp_path/'workspace','idml-fixture',grant)
    assert len(transport.calls)==3
