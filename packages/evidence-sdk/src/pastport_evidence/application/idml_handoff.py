"""Export verified IDML matches and real photo observations for existing environment tooling."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image, ImageDraw
from pydantic import Field
from pastport_evidence.domain.models import DomainModel
from pastport_evidence.adapters.assets import LocalAssetStore
from pastport_evidence.adapters.idml_graphics import IDMLGraphicLibrary
from pastport_evidence.domain.idml import IDMLDocument, IDMLMatchResult
from pastport_evidence.domain.photos import PhotoInventory
from pastport_evidence.domain.recognition import PixelRegion



class DistinctIdentityReview(DomainModel):
    """A source-bound review may resolve overlapping boxes, never invent evidence."""

    inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    object_ids: tuple[str, str]
    basis: str = Field(min_length=1)


class IDMLEnvironmentHandoff:
    @staticmethod
    def _overlap(a: PixelRegion, b: PixelRegion) -> bool:
        width = max(0, min(a.bottom_right.x, b.bottom_right.x) - max(a.top_left.x, b.top_left.x))
        height = max(0, min(a.bottom_right.y, b.bottom_right.y) - max(a.top_left.y, b.top_left.y))
        smaller = min(
            (r.bottom_right.x - r.top_left.x) * (r.bottom_right.y - r.top_left.y)
            for r in (a, b)
        )
        return smaller > 0 and width * height >= 0.65 * smaller

    @classmethod
    def identity_conflicts(cls, result: IDMLMatchResult, inventory: PhotoInventory,
                           reviews: tuple[DistinctIdentityReview, ...] = ()) -> dict[str, set[int]]:
        entities = {entity.object_id: entity for entity in inventory.entities}
        inventory_hash = hashlib.sha256(inventory.model_dump_json().encode()).hexdigest()
        distinct: set[frozenset[str]] = set()
        for review in reviews:
            if (review.inventory_sha256 != inventory_hash or len(set(review.object_ids)) != 2
                    or not set(review.object_ids) <= entities.keys() or not review.basis.strip()):
                raise ValueError('Identity review differs from the current photo inventory')
            distinct.add(frozenset(review.object_ids))
        matched_ids = {match.object_id for match in result.objects if match.status == 'matched'}
        sightings = [item for item in inventory.observations if item.object_id in matched_ids]
        overlaps: dict[str, set[int]] = {}
        for index, left in enumerate(sightings):
            for right in sightings[index + 1:]:
                if (
                    left.object_id != right.object_id
                    and frozenset((left.object_id, right.object_id)) not in distinct
                    and left.photo.photo_id == right.photo.photo_id
                    and cls._overlap(left.region, right.region)
                ):
                    overlaps.setdefault(left.object_id, set()).add(entities[right.object_id].display_number)
                    overlaps.setdefault(right.object_id, set()).add(entities[left.object_id].display_number)
        return overlaps

    def write(self, source: Path, links: Path, document: IDMLDocument,
              result: IDMLMatchResult, inventory: PhotoInventory,
              assets: LocalAssetStore, output: Path,
              identity_reviews: tuple[DistinctIdentityReview, ...] = ()) -> None:
        if output.exists():
            raise ValueError('Native source handoff must use an independent new directory')
        if document.source_sha256!=result.source_sha256 or hashlib.sha256(source.read_bytes()).hexdigest()!=document.source_sha256:
            raise ValueError('Native handoff source identity mismatch')
        output.mkdir(parents=True);media=output/'media';media.mkdir()
        shutil.copyfile(source,output/'source.idml');shutil.copyfile(source,output/'input.idml')
        (output/'idml-document.json').write_text(document.model_dump_json(indent=2))
        (output/'idml-matches.json').write_text(result.model_dump_json(indent=2))
        library=IDMLGraphicLibrary(links)
        entities={o.object_id:o for o in inventory.entities}
        image_by_id={i.image_id:i for i in document.images}
        stories={s.story_id:s for s in document.stories}
        photo_numbers={photo.photo_id:index for index,photo in enumerate(inventory.photos,1)}
        photos=[]
        for photo in inventory.photos:
            number=photo_numbers[photo.photo_id];target=media/f'photo-{number:02d}.jpg'
            shutil.copyfile(assets.resolve_path(photo.image),target)
            photos.append({'number':number,'path':f'registered-photo:{photo.photo_id}',
                'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'oriented_size':[photo.width,photo.height],
                'source_kind':'registered_site_photo'})
        objects=[];quotes=[];units: list[dict[str,str|int]]=[];gaps=[]
        overlaps = self.identity_conflicts(result, inventory, identity_reviews)
        review_rows = []
        for match in result.objects:
            entity=entities[match.object_id]
            row = {
                'number': entity.display_number, 'name': entity.label,
                'historical_name': match.historical_name, 'status': match.status,
                'reason': match.review_reason, 'image_role': match.image_role,
            }
            review_rows.append(row)
            if match.object_id in overlaps:
                others = ', '.join(str(number) for number in sorted(overlaps[match.object_id]))
                row['spatial_review_hint'] = f'照片选区与编号 {others} 重叠，定位时请核对物件表面。'
            if match.status!='matched':
                gaps.append({'object_number':entity.display_number,'state':match.status,'reason':match.review_reason});continue
            if not match.citations or not match.historical_name:
                raise ValueError('Accepted match lacks source-grounded identity')
            primary=match.citations[0];story=stories[primary.story_id]
            paragraph=story.paragraphs[primary.paragraph_index]
            if story.text[primary.start:primary.end]!=primary.quote:
                raise ValueError('Compiled quotation no longer matches native source')
            unit=len(units)+1
            preview=media/f'text-unit-{unit:02d}.png'
            with Image.new('RGB',(1000,360),'white') as image:
                ImageDraw.Draw(image).text((35,45),'Native IDML text evidence\nSee the exact source text and selector in the evidence panel.\nNo historical-object photograph is asserted here.',fill='black',font_size=24)
                image.save(preview)
            units.append({'unit_id':unit,'text':paragraph.text,'member':story.member,'story_id':story.story_id,
                'start':paragraph.start,'paragraph_index':paragraph.index,'preview':str(preview.relative_to(output))})
            local_start=primary.start-paragraph.start
            quotes.append({'number':entity.display_number,'page':unit,'normalized_text':paragraph.text,
                'start':local_start,'end':local_start+len(primary.quote)})
            target=media/f'history-{entity.display_number:02d}.png'
            if match.image_id:
                selected=image_by_id[match.image_id]
                graphic=library.entries[selected.filename][0]
                if graphic.digest()!=selected.sha256:raise ValueError('Historical graphic changed')
                temporary=media/f'preview-{entity.display_number}.jpg';graphic.thumbnail(temporary)
                with Image.open(temporary) as raw,raw.convert('RGB') as image:image.save(target)
            else:shutil.copyfile(preview,target)
            observations=[]
            related=tuple(o for o in inventory.observations if o.object_id==entity.object_id)
            if not related:raise ValueError('Mapped object has no site-photo observation')
            for observation in related:
                region=observation.region;photo=observation.photo
                observations.append({'photo_number':photo_numbers[photo.photo_id],'observation_status':'visible',
                    'region_normalized':[region.top_left.x/photo.width,region.top_left.y/photo.height,
                        region.bottom_right.x/photo.width,region.bottom_right.y/photo.height],'basis':observation.basis})
            shutil.copyfile(assets.resolve_path(related[0].crop),output/f'proxy-{entity.display_number}.png')
            identity='historical:'+hashlib.sha256((document.source_sha256+match.historical_name).encode()).hexdigest()[:24]
            objects.append({'number':entity.display_number,'object_id':entity.object_id,'name':entity.label,
                'boundary':'; '.join(entity.distinguishing_features),'history_id':identity,
                'history':match.historical_name,'parent':'source-subject-scope-unconfirmed',
                'page':unit,'image_page':unit if match.image_id else None,'image_box':None,
                'image_role':match.image_role,'explanation':match.rationale,'proxy':match.relationship,
                'limit':'; '.join(match.limitations) or 'Historical approval remains pending',
                'quote':primary.quote,'observations':observations,'introduction':match.introduction})
        if not objects:raise ValueError('No independently reviewed IDML mappings; no environment published')
        for name,payload in {'objects.json':{'title':'IDML historical source','objects':objects},
            'inputs.json':{'input_page_count':len(units),'photos':photos,'source_format':'idml'},
            'source-units.json':{'source_format':'idml','units':units},'quote-regions.json':quotes,
            'mapping-gaps.json':gaps, 'idml-review-inventory.json':review_rows,
            'identity-reviews.json':[review.model_dump() for review in identity_reviews],
            'mapping-coverage.json':{'recognized':len(inventory.entities), 'matched':len(objects),
                'requires_review':sum(row['status']=='requires_review' for row in review_rows),
                'unmatched':sum(row['status']=='unmatched' for row in review_rows),
                'minimum_mounted_objects':15, 'saved_3d_anchors':0,
                'mounting_complete':False, 'photo_gaps':list(inventory.gaps)}}.items():
            (output/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2))
