"""Bounded local extraction of source text, frame threads and graphic candidates."""
from __future__ import annotations

import hashlib
import math
import stat
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from pastport_evidence.adapters.idml_graphics import IDMLGraphicError, IDMLGraphicLibrary, IDMLGraphicSource
from pastport_evidence.domain.idml import (
    IDMLAssociationCandidate, IDMLDocument, IDMLFrame, IDMLImage,
    IDMLPage, IDMLParagraph, IDMLStory,
)

Matrix = tuple[float, float, float, float, float, float]
Box = tuple[float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class IDMLReadError(ValueError):
    """A source package cannot be safely or consistently read."""


def _matrix(value: str) -> Matrix:
    values = tuple(float(part) for part in value.split())
    if len(values) != 6 or not all(math.isfinite(x) for x in values):
        raise IDMLReadError("Invalid IDML affine transform")
    return (values[0], values[1], values[2], values[3], values[4], values[5])


def _compose(parent: Matrix, local: Matrix) -> Matrix:
    a,b,c,d,e,f = parent
    g,h,i,j,k,l = local
    return (a*g+c*h,b*g+d*h,a*i+c*j,b*i+d*j,a*k+c*l+e,b*k+d*l+f)


def _point(matrix: Matrix, x: float, y: float) -> tuple[float, float]:
    a,b,c,d,e,f = matrix
    return (a*x+c*y+e,b*x+d*y+f)


def _box(points: tuple[tuple[float, float], ...]) -> Box | None:
    if not points:
        return None
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))


def _bounds(element: ET.Element, matrix: Matrix) -> Box | None:
    points = []
    # Graphic transforms differ from the containing clipped frame transform.
    for node in element.findall('./Properties/PathGeometry/GeometryPathType/PathPointArray/PathPointType'):
        values = tuple(float(v) for v in node.attrib.get('Anchor', '').split())
        if len(values) != 2 or not all(math.isfinite(x) for x in values):
            raise IDMLReadError("Invalid frame path")
        points.append(_point(matrix, values[0], values[1]))
    return _box(tuple(points))


def _page_for(bounds: Box | None, pages: tuple[IDMLPage, ...]) -> str | None:
    if bounds is None:
        return None
    areas = []
    for page in pages:
        a,b,c,d = page.bounds
        x,y,z,w = bounds
        area = max(0.0,min(c,z)-max(a,x))*max(0.0,min(d,w)-max(b,y))
        if area > 0:
            areas.append((area,page.page_id))
    if not areas:
        return None
    areas.sort(reverse=True)
    # A frame crossing pages cannot be assigned by arbitrary source ordering.
    return areas[0][1] if len(areas)==1 or areas[0][0] > areas[1][0]*1.05 else None


class IDMLDocumentReader:
    """Read without executing layout software, external links, OCR or model calls."""

    max_archive_bytes = 32 * 1024**2
    max_xml_bytes = 8 * 1024**2
    max_expanded_bytes = 128 * 1024**2

    def read(self, source: Path, links: Path | None = None) -> IDMLDocument:
        if source.is_symlink() or not source.is_file() or not 0 < source.stat().st_size <= self.max_archive_bytes:
            raise IDMLReadError("IDML file missing, linked or oversized")
        try:
            available = self._links(links)
        except (IDMLGraphicError, BadZipFile, OSError) as error:
            raise IDMLReadError(str(error)) from error
        try:
            with ZipFile(source) as archive:
                self._validate_archive(archive)
                design = self._xml(archive, 'designmap.xml')
                stories: list[IDMLStory] = []
                pages: list[IDMLPage] = []
                frames: list[IDMLFrame] = []
                images: list[IDMLImage] = []
                for item in design:
                    kind = item.tag.rsplit('}',1)[-1]
                    member = item.attrib.get('src','')
                    if kind == 'Story':
                        stories.append(self._story(archive, member))
                    elif kind == 'Spread':
                        p,f,i = self._spread(archive, member, available)
                        pages.extend(p);frames.extend(f);images.extend(i)
                if not stories or not pages:
                    raise IDMLReadError("IDML has no source stories or layout pages")
                warnings = self._validate_threads(tuple(stories),tuple(frames))
                associations = []
                for image in images:
                    same_spread = tuple(f for f in frames if f.spread == image.spread)
                    grouped = tuple(f for f in same_spread if image.group_id and f.group_id == image.group_id)
                    same_page = tuple(f for f in same_spread if image.page_id and f.page_id == image.page_id)
                    candidates = grouped or same_page or same_spread
                    associations.append(IDMLAssociationCandidate(
                        image_id=image.image_id,frame_ids=tuple(f.frame_id for f in candidates),
                        story_ids=tuple(sorted({f.story_id for f in candidates})),
                        basis='shared_group' if grouped else 'same_page' if same_page else 'same_spread',
                    ))
                for image in images:
                    if image.link_state != 'available':
                        warnings.append(f'graphic_{image.link_state}:{image.link_id}:{image.filename}')
                return IDMLDocument(
                    source_filename=source.name,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    stories=tuple(stories),pages=tuple(pages),frames=tuple(frames),images=tuple(images),
                    associations=tuple(associations),warnings=tuple(warnings),
                )
        except (BadZipFile, ET.ParseError, KeyError, OSError, UnicodeError) as error:
            raise IDMLReadError(f"Unable to read IDML source: {type(error).__name__}") from error

    def _validate_archive(self, archive: ZipFile) -> None:
        entries = archive.infolist()
        if len(entries)>2000 or sum(e.file_size for e in entries)>self.max_expanded_bytes:
            raise IDMLReadError("IDML expansion exceeds limits")
        names = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                or entry.filename in names or stat.S_ISLNK(entry.external_attr >> 16)
                or entry.flag_bits & 1):
                raise IDMLReadError("Unsafe, duplicate or encrypted IDML member")
            names.add(entry.filename)
            if entry.file_size > self.max_xml_bytes and entry.filename.endswith('.xml'):
                raise IDMLReadError("IDML XML member exceeds limits")
            if entry.file_size > max(1024**2,entry.compress_size*500):
                raise IDMLReadError("IDML compression ratio exceeds limits")
        if 'designmap.xml' not in names:
            raise IDMLReadError("Missing designmap.xml")

    def _xml(self, archive: ZipFile, member: str) -> ET.Element:
        name = PurePosixPath(member)
        if name.is_absolute() or '..' in name.parts or '\\' in member or not member.endswith('.xml'):
            raise IDMLReadError("Invalid IDML component reference")
        raw = archive.read(member)
        if len(raw)>self.max_xml_bytes or b'\x00' in raw:
            raise IDMLReadError("Oversized or unsupported XML encoding")
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise IDMLReadError("XML entity declarations are not accepted")
        return ET.fromstring(raw)

    def _story(self, archive: ZipFile, member: str) -> IDMLStory:
        root = self._xml(archive,member)
        story = next(root.iter('Story'),None)
        if story is None:
            raise IDMLReadError("Missing IDML Story")
        paragraphs = []
        parts = []
        offset = 0
        for index, paragraph in enumerate(story.iter('ParagraphStyleRange')):
            text = ''.join((node.text or '') if node.tag=='Content' else '\n' if node.tag=='Br' else '\t'
                           for node in paragraph.iter() if node.tag in ('Content','Br','Tab'))
            paragraphs.append(IDMLParagraph(index=index,start=offset,end=offset+len(text),text=text,
                                            style=paragraph.attrib.get('AppliedParagraphStyle','')))
            parts.append(text);offset+=len(text)
        return IDMLStory(story_id=story.attrib['Self'],member=member,text=''.join(parts),paragraphs=tuple(paragraphs))

    @staticmethod
    def _links(folder: Path | None) -> dict[str, tuple[IDMLGraphicSource, ...]]:
        return IDMLGraphicLibrary(folder).entries

    def _spread(self, archive: ZipFile, member: str, links: dict[str,tuple[IDMLGraphicSource,...]]) -> tuple[tuple[IDMLPage,...],tuple[IDMLFrame,...],tuple[IDMLImage,...]]:
        root=self._xml(archive,member)
        spread=next(root.iter('Spread'),None)
        if spread is None:
            raise IDMLReadError("Missing IDML Spread")
        pages=[]
        for page in spread.findall('Page'):
            bounds=tuple(float(v) for v in page.attrib['GeometricBounds'].split())
            if len(bounds)!=4 or not all(math.isfinite(v) for v in bounds):
                raise IDMLReadError("Invalid IDML page bounds")
            top,left,bottom,right=bounds
            transform=_compose(_matrix(spread.attrib.get('ItemTransform','1 0 0 1 0 0')), _matrix(page.attrib.get('ItemTransform','1 0 0 1 0 0')))
            box=_box(tuple(_point(transform,x,y) for x,y in ((left,top),(right,top),(right,bottom),(left,bottom))))
            assert box is not None
            pages.append(IDMLPage(page_id=page.attrib['Self'],label=page.attrib.get('Name',''),spread=member,bounds=box))
        frames: list[IDMLFrame]=[]
        images: list[IDMLImage]=[]
        def visit(node: ET.Element, parent: Matrix, group: str | None, clipping: Box | None) -> None:
            transform=_compose(parent,_matrix(node.attrib.get('ItemTransform','1 0 0 1 0 0')))
            if node.tag=='Group':
                group=node.attrib.get('Self')
            bounds=_bounds(node,transform)
            if node.tag=='TextFrame':
                frames.append(IDMLFrame(frame_id=node.attrib['Self'],story_id=node.attrib['ParentStory'],
                    previous_frame=None if node.attrib.get('PreviousTextFrame','n')=='n' else node.attrib['PreviousTextFrame'],
                    next_frame=None if node.attrib.get('NextTextFrame','n')=='n' else node.attrib['NextTextFrame'],
                    spread=member,group_id=group,bounds=bounds,page_id=_page_for(bounds,tuple(pages))))
            if node.tag in ('Rectangle','Oval','Polygon'):
                clipping=bounds
            if node.tag in ('Image','PDF','EPS'):
                for link in node.findall('Link'):
                    uri=urlsplit(link.attrib.get('LinkResourceURI',''))
                    name=unicodedata.normalize('NFC',unquote(uri.path).replace('\\','/').rsplit('/',1)[-1])
                    matches=links.get(name,())
                    state: Literal['unsupported','ambiguous','available','missing'] = 'unsupported' if uri.scheme not in ('','file') else 'ambiguous' if len(matches)>1 else 'available' if matches else 'missing'
                    digest=None
                    if state=='available':
                        digest=matches[0].digest()
                    images.append(IDMLImage(image_id=node.attrib['Self'],link_id=link.attrib.get('Self',node.attrib['Self']),
                        filename=name,spread=member,group_id=group,bounds=clipping,page_id=_page_for(clipping,tuple(pages)),
                        link_state=state,sha256=digest))
            for child in node:
                if child.tag not in ('Properties','Page'):
                    visit(child,transform,group,clipping)
        visit(spread,IDENTITY,None,None)
        return tuple(pages),tuple(frames),tuple(images)

    @staticmethod
    def _validate_threads(stories: tuple[IDMLStory,...], frames: tuple[IDMLFrame,...]) -> list[str]:
        story_ids={s.story_id for s in stories};by_id={f.frame_id:f for f in frames}
        if len(story_ids)!=len(stories) or len(by_id)!=len(frames):
            raise IDMLReadError("Duplicate Story or frame identity")
        warnings=[]
        for frame in frames:
            if frame.story_id not in story_ids:
                raise IDMLReadError("Frame references an unavailable source Story")
            for target in (frame.previous_frame,frame.next_frame):
                if target and target not in by_id:
                    warnings.append(f'thread_link_missing:{frame.frame_id}:{target}')
                elif target and by_id[target].story_id!=frame.story_id:
                    raise IDMLReadError("Thread crosses Story identities")
            seen={frame.frame_id};cursor=frame.next_frame
            while cursor and cursor in by_id:
                if cursor in seen:
                    raise IDMLReadError("Cyclic IDML text thread")
                seen.add(cursor);cursor=by_id[cursor].next_frame
        return warnings
