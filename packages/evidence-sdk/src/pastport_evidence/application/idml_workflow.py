"""Source-native IDML/photo matching with no PDF parsing or implicit external search."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
from pastport_evidence.adapters.assets import LocalAssetStore
from pastport_evidence.adapters.codex_semantics import CodexSemanticGateway
from pastport_evidence.adapters.execution import SubscriptionExecutor
from pastport_evidence.adapters.identity import SQLiteSceneRepository
from pastport_evidence.adapters.idml import IDMLDocumentReader
from pastport_evidence.adapters.idml_graphics import IDMLGraphicLibrary
from pastport_evidence.adapters.idml_matching import MeteredIDMLMatchGateway
from pastport_evidence.application.bootstrap import atomic_write
from pastport_evidence.application.idml_matching import IDMLMatchingService, IDMLMatchRequest
from pastport_evidence.application.photos import PhotoRecognitionService, PhotoRegistrar
from pastport_evidence.domain.execution import SubscriptionGrant
from pastport_evidence.domain.idml import IDMLDocument, IDMLMatchResult
from pastport_evidence.domain.photos import PhotoInventory
from pastport_evidence.ports.execution import SemanticTransport


class IDMLPhotoWorkflow:
    """Keep existing photo identities, grants, receipts and independent review."""

    def __init__(self, transport: SemanticTransport) -> None:
        self.transport=transport

    def run(self, source: Path, links: Path | None, photos: Path, workspace: Path,
            grant: SubscriptionGrant, *, allow_missing_graphics: bool = False) -> IDMLMatchResult:
        workspace.mkdir(parents=True,exist_ok=True)
        atomic_write(workspace/'progress.json',json.dumps({'phase':'idml_import'}))
        document=IDMLDocumentReader().read(source,links)
        if not allow_missing_graphics and any(image.link_state!='available' for image in document.images):
            raise ValueError('IDML graphic references must be complete before paid matching')
        paths=tuple(sorted(p for p in photos.iterdir() if p.is_file() and not p.name.startswith('.')))
        assets=LocalAssetStore(workspace/'assets')
        registered=PhotoRegistrar(assets).register(grant.project_id,paths)
        minimum_calls = math.ceil(len(registered) / 2) + 2
        if grant.max_calls < minimum_calls:
            raise ValueError(
                f'Full photo coverage and mapping require at least {minimum_calls} authorized calls; '
                'no model dispatched, extend the finite grant before running'
            )
        policy_file = workspace / 'idml-match-policy.txt'
        if policy_file.exists():
            policy = policy_file.read_text().strip()
            if policy not in ('v1', 'v2', 'v3', 'v4'):
                raise ValueError('Unknown IDML matching policy')
        else:
            policy = 'v1' if (workspace / 'idml-input.sha256').exists() else 'v4'
            atomic_write(policy_file, policy)
        fingerprint=hashlib.sha256(b'idml-full-photo-coverage-v1')
        fingerprint.update(document.model_dump_json().encode())
        if allow_missing_graphics:
            fingerprint.update(b'explicit-available-graphics-only-v1')
        fingerprint.update((Path(__file__).parents[1]/'prompts'/'photo_inspection_v2.txt').read_bytes())
        for photo in registered:
            fingerprint.update(photo.original.asset.sha256.encode())
        # Prompt changes create separate workspaces instead of rewriting paid receipts.
        for name in (f'idml_mapping_{policy}.txt',f'idml_mapping_audit_{policy}.txt'):
            fingerprint.update((Path(__file__).parents[1]/'prompts'/name).read_bytes())
        lock=workspace/'idml-input.sha256'
        if lock.exists() and lock.read_text()!=fingerprint.hexdigest():
            raise ValueError('IDML source or photo identity changed; choose a new workspace')
        atomic_write(lock,fingerprint.hexdigest())
        run=workspace/'runs'/fingerprint.hexdigest();run.mkdir(parents=True,exist_ok=True)
        atomic_write(run/'idml-document.json',document.model_dump_json(indent=2))
        executor=SubscriptionExecutor(workspace/'codex-executions.sqlite3',grant,self.transport)
        if (workspace/'no-token-threshold-authorized.txt').is_file():
            executor.remove_token_threshold('Explicit Admin policy: record usage and retain call ceilings without a cumulative token stop')
        atomic_write(workspace/'progress.json','{"phase":"recognize_photos"}')
        inventory=PhotoRecognitionService(SQLiteSceneRepository(workspace/'identities.sqlite3'),
            CodexSemanticGateway(executor,assets,photo_prompt_version='v2'),assets,
            batch_size=2,allow_partial_inventory=True).run(grant.project_id,registered,run,
                grant.grant_ref,grant.model_id,max(0, grant.max_calls - 2))
        if not inventory.entities:
            raise ValueError('No recognized site objects available for historical mapping')
        if any(gap.startswith('photo_call_budget_exhausted:inventory:') for gap in inventory.gaps):
            raise ValueError('Photo coverage incomplete; retain receipts and extend the finite grant before mapping')
        # Missing links remain recorded in the original document, never offered as image evidence.
        available_images = tuple(image for image in document.images if image.link_state == 'available')
        available_ids = {image.image_id for image in available_images}
        matching_document = document.model_copy(update={
            'images': available_images,
            'associations': tuple(item for item in document.associations if item.image_id in available_ids),
        })
        source_sheets=self._source_sheets(matching_document,IDMLGraphicLibrary(links),run)
        modern=self._modern_sheets(inventory,assets,run)
        from typing import cast, Literal
        selected_policy = cast(Literal['v1', 'v2', 'v3', 'v4'], policy)
        service = IDMLMatchingService(MeteredIDMLMatchGateway(executor, policy=selected_policy), strict_identity=policy in ('v2', 'v3', 'v4'))
        batches: list[IDMLMatchResult] = []
        for index, sheet in enumerate(modern):
            start = index * 16
            request = IDMLMatchRequest(source=matching_document, objects=inventory.entities[start:start + 16])
            atomic_write(workspace / 'progress.json', json.dumps({
                'phase': 'idml_mapping', 'recognized_objects': len(inventory.entities),
                'completed_calls': index * 2,
            }))
            batch_dir = run / f'mapping-batch-{index:03d}'
            batches.append(service.run(request, source_sheets + (sheet,), batch_dir, atomic_write))
        result = IDMLMatchResult(
            source_sha256=document.source_sha256,
            objects=tuple(item for batch in batches for item in batch.objects),
            receipt_refs=tuple(receipt for batch in batches for receipt in batch.receipt_refs),
        )
        atomic_write(workspace/'result.json',result.model_dump_json(indent=2))
        atomic_write(workspace/'progress.json',json.dumps({'phase':'idml_mapping_ready','recognized_objects':len(inventory.entities)}))
        return result

    @staticmethod
    def _source_sheets(document: IDMLDocument, library: IDMLGraphicLibrary, run: Path) -> tuple[Path,...]:
        if len(document.images)>144:
            raise ValueError('Current visual mapping profile allows at most 144 linked image placements')
        sheets=[]
        for start in range(0,len(document.images),24):
            target=run/f'history-sheet-{start//24}.jpg'
            group=document.images[start:start+24]
            with Image.new('RGB',(1800,4*280),'white') as sheet:
                draw=ImageDraw.Draw(sheet)
                for offset,image in enumerate(group):
                    preview=run/f'history-{hashlib.sha256(image.image_id.encode()).hexdigest()}.jpg'
                    if not preview.exists():library.entries[image.filename][0].thumbnail(preview,edge=1024)
                    x,y=(offset%6)*300,(offset//6)*280
                    draw.text((x+5,y+5),image.image_id,fill='black',font_size=20)
                    with Image.open(preview) as raw,raw.convert('RGB') as picture:
                        picture.thumbnail((290,240));sheet.paste(picture,(x+5,y+35))
                sheet.save(target,'JPEG',quality=90)
            sheets.append(target)
        return tuple(sheets)

    @staticmethod
    def _modern_sheets(inventory: PhotoInventory, assets: LocalAssetStore, run: Path) -> tuple[Path, ...]:
        sheets: list[Path] = []
        for start in range(0, len(inventory.entities), 16):
            group = inventory.entities[start:start + 16]
            target = run / f'modern-object-sheet-{start // 16}.jpg'
            with Image.new('RGB', (1600, math.ceil(len(group) / 4) * 320), 'white') as sheet:
                draw = ImageDraw.Draw(sheet)
                for offset, entity in enumerate(group):
                    matches = tuple(o for o in inventory.observations if o.object_id == entity.object_id)
                    if not matches:
                        raise ValueError('Recognized object lacks a registered physical observation')
                    observation = next((o for o in matches if o.identity_state == 'confirmed'), matches[0])
                    x, y = (offset % 4) * 400, (offset // 4) * 320
                    draw.text((x + 6, y + 6), str(entity.display_number), fill='black', font_size=24)
                    with Image.open(assets.resolve_path(observation.crop)) as raw, raw.convert('RGB') as image:
                        image.thumbnail((380, 270))
                        sheet.paste(image, (x + 8, y + 40))
                sheet.save(target, 'JPEG', quality=92)
            sheets.append(target)
        return tuple(sheets)
