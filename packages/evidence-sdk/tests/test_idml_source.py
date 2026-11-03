"""Threaded source text and visual proximity must not become false image evidence."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import pytest
from pastport_evidence.adapters.idml import IDMLDocumentReader, IDMLReadError


def package(root: Path, *, cycle: bool = False, entity: bool = False) -> Path:
    target=root/'source.idml'
    design='<Document xmlns:p="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"><p:Story src="Stories/a.xml"/><p:Spread src="Spreads/a.xml"/><p:Spread src="Spreads/b.xml"/></Document>'
    text='<Story Self="s"><ParagraphStyleRange AppliedParagraphStyle="body"><CharacterStyleRange><Content>Şeyh Sırrî</Content><Br/><Content>炉灶与烟囱</Content></CharacterStyleRange></ParagraphStyleRange></Story>'
    path='<Properties><PathGeometry><GeometryPathType><PathPointArray><PathPointType Anchor="0 0"/><PathPointType Anchor="80 0"/><PathPointType Anchor="80 80"/><PathPointType Anchor="0 80"/></PathPointArray></GeometryPathType></PathGeometry></Properties>'
    with ZipFile(target,'w') as z:
        z.writestr('designmap.xml',design)
        z.writestr('Stories/a.xml',('<!DOCTYPE Story [<!ENTITY bad "bad">]>' if entity else '')+text)
        for name,frame,previous,following in [('a','f1','f2' if cycle else 'n','f2'),('b','f2','f1','f1' if cycle else 'n')]:
            z.writestr(f'Spreads/{name}.xml',f'<Spread Self="{name}" ItemTransform="1 0 0 1 0 2000"><Page Self="p{name}" Name="1" GeometricBounds="0 0 100 100" ItemTransform="1 0 0 1 0 0"/><TextFrame Self="{frame}" ParentStory="s" PreviousTextFrame="{previous}" NextTextFrame="{following}">{path}</TextFrame><Rectangle Self="r{name}">{path}<Image Self="i{name}"><Link Self="l{name}" LinkResourceURI="file:C:/original/Links/photo%20%C5%9F.jpg"/></Image></Rectangle></Spread>')
    return target


def test_threaded_story_is_read_once_and_same_page_is_only_a_candidate(tmp_path: Path) -> None:
    source=package(tmp_path);links=tmp_path/'Links';links.mkdir();photo=links/'photo ş.jpg';photo.write_bytes(b'graphic-fixture')
    result=IDMLDocumentReader().read(source,links)
    assert len(result.stories)==1 and result.stories[0].text=='Şeyh Sırrî\n炉灶与烟囱'
    assert result.frames[0].next_frame=='f2' and result.frames[1].previous_frame=='f1'
    assert all(f.page_id is not None and f.text_range_state=='requires_composition' for f in result.frames)
    assert all(i.link_state=='available' and i.sha256==hashlib.sha256(photo.read_bytes()).hexdigest() for i in result.images)
    assert all(a.status=='requires_semantic_review' and len(a.frame_ids)==1 for a in result.associations)
    assert result.historical_approval is False


def test_missing_graphic_retains_text_but_reports_link_gap(tmp_path: Path) -> None:
    result=IDMLDocumentReader().read(package(tmp_path))
    assert result.stories[0].text.startswith('Şeyh')
    assert all(i.link_state=='missing' for i in result.images)
    assert len(result.warnings)==2


@pytest.mark.parametrize('kind',['cycle','entity','traversal','duplicate','linked-image'])
def test_unsafe_or_inconsistent_sources_are_not_silently_accepted(tmp_path: Path,kind: str) -> None:
    source=package(tmp_path,cycle=kind=='cycle',entity=kind=='entity')
    if kind in ('traversal','duplicate'):
        with ZipFile(source,'a') as z:
            with pytest.warns(UserWarning) if kind=='duplicate' else __import__('contextlib').nullcontext():
                z.writestr('designmap.xml' if kind=='duplicate' else '../escape.xml','<root/>')
    links=None
    if kind=='linked-image':
        links=tmp_path/'Links';links.mkdir();(links/'photo ş.jpg').symlink_to(source)
    with pytest.raises(IDMLReadError):IDMLDocumentReader().read(source,links)


def test_large_zip_library_is_streamed_and_duplicate_basenames_are_not_guessed(tmp_path: Path) -> None:
    source=package(tmp_path);links=tmp_path/'graphics.zip'
    with ZipFile(links,'w') as z:z.writestr('Links/photo ş.jpg',b'graphic-fixture')
    result=IDMLDocumentReader().read(source,links)
    assert all(i.link_state=='available' for i in result.images)
    assert not (tmp_path/'Links').exists()
    with ZipFile(links,'a') as z:z.writestr('Other/photo ş.jpg',b'different-image')
    ambiguous=IDMLDocumentReader().read(source,links)
    assert all(i.link_state=='ambiguous' and i.sha256 is None for i in ambiguous.images)
