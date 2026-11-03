"""Localize a source-native IDML handoff using the existing environment execution stages."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from pydantic import BaseModel, ConfigDict
from pastport_matched_environment.adapters.assets import LocalAssetStore
from pastport_matched_environment.adapters.tour import TourImporter
from pastport_matched_environment.application.environment_agent import offline_input_limits
from pastport_matched_environment.application.environment_build import EnvironmentRun
from pastport_matched_environment.application.reference_environment import CandidateBuilder, digest, reference_assets
from pastport_matched_environment.domain.environment import MatchedBatch, MatchedObject, PageCrop
from pastport_matched_environment.domain.execution import SubscriptionGrant
from pastport_matched_environment.ports.execution import SemanticTransport
from pastport_matched_environment.workflow.graph import StageJournal, FixedWorkflow, FixedStage, StageCommand, StageOutput


class _Observation(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra='ignore')
    photo_number: int
    region_normalized: tuple[float,float,float,float]
    basis: str


class _Object(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra='ignore')
    number: int
    name: str
    boundary: str
    history_id: str
    history: str
    parent: str
    page: int
    quote: str
    explanation: str
    proxy: str
    limit: str
    observations: tuple[_Observation,...]


class _Objects(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra='ignore')
    objects: tuple[_Object,...]


class NativeIDMLEnvironmentRun(EnvironmentRun):
    def page_image(self, page: int) -> Path:
        # The structural review consumes real site-photo images, never PDF renders.
        return self.evidence/'media'/f'photo-{page:02d}.jpg'


class _Stage:
    def __init__(self, run: NativeIDMLEnvironmentRun, name: str) -> None:
        self.run,self.name=run,name

    def execute(self, command: StageCommand) -> StageOutput:
        if self.name=='localize':return self.run.localize()
        if self.name=='structure':return self.run.review_structure()
        return self.run.publish()


class IDMLEnvironmentWorkflow:
    def __init__(self, transport: SemanticTransport) -> None:
        self.transport=transport

    def run(self, handoff: Path, tour: Path, workspace: Path, run_id: str,
            grant: SubscriptionGrant) -> Path:
        if not run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in run_id):
            raise ValueError('Invalid native environment run identity')
        source=handoff/'source.idml'
        # Bind every handoff input, including original observations and full introductions.
        binding=hashlib.sha256(grant.model_dump_json().encode())
        for path in sorted(handoff.rglob('*')):
            if path.is_symlink():raise ValueError('Native handoff links are not accepted')
            if path.is_file():
                binding.update(path.relative_to(handoff).as_posix().encode());binding.update(digest(path).encode())
        binding.update(digest(tour).encode())
        context=NativeIDMLEnvironmentRun(source,tour,grant,workspace,run_id,'IDML historical environment',
            False,Path('unused-for-native-idml'),self.transport,binding.hexdigest())
        lock=context.run/'idml-input.sha256'
        if lock.exists() and lock.read_text()!=binding.hexdigest():
            raise ValueError('Native environment inputs changed; choose a new run')
        lock.write_text(binding.hexdigest())
        context.prepared.mkdir(exist_ok=True)
        if not context.evidence.exists():shutil.copytree(handoff,context.evidence)
        for path in handoff.glob('proxy-*.png'):
            destination=context.run/path.name
            if not destination.exists():shutil.copyfile(path,destination)
        importer=TourImporter(LocalAssetStore(context.prepared/'assets'))
        admitted=importer.import_html(grant.project_id,tour,offline_input_limits())
        (context.prepared/'tour.json').write_text(admitted.model_dump_json())
        panorama=context.prepared/'panoramas';panorama.mkdir(exist_ok=True)
        asset_store=LocalAssetStore(context.prepared/'assets')
        for index,view in enumerate(admitted.views,1):
            destination=panorama/f'view-{index:03d}.jpg'
            if not destination.exists():shutil.copyfile(asset_store.resolve_path(view.panorama),destination)
        objects=_Objects.model_validate_json((handoff/'objects.json').read_bytes())
        inventory=MatchedBatch(objects=tuple(MatchedObject(
            number=obj.number,name=obj.name,boundary=obj.boundary,history_key=obj.history_id,
            history=obj.history,parent=obj.parent,page=obj.page,quote=obj.quote,historical_image=None,
            modern_images=tuple(PageCrop(page=o.photo_number,box=o.region_normalized,basis=o.basis) for o in obj.observations),
            explanation=obj.explanation[:300],proxy=obj.proxy[:300],limitation=obj.limit[:300],
            whole_number=None,historical_relation=None,
        ) for obj in objects.objects),gaps=())
        (context.run/'matched.json').write_text(inventory.model_dump_json())
        FixedWorkflow(StageJournal(workspace/'stages.sqlite3'),(
            FixedStage('fresh_localization',_Stage(context,'localize')),
            FixedStage('structural_review',_Stage(context,'structure')),
            FixedStage('publish',_Stage(context,'publish')),
        ),'idml-native-environment-v1').run(grant.project_id,run_id,binding.hexdigest())
        return context.run/'result'
