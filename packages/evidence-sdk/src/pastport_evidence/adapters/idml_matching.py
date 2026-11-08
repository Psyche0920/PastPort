"""Two bounded IDML semantic requests through the existing subscription ledger."""
from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Literal
from typing import TypeVar
from pastport_evidence.adapters.execution import SubscriptionExecutor
from pastport_evidence.adapters.structured_output import StrictOutputSchema
from pastport_evidence.application.idml_matching import IDMLMatchRequest
from pastport_evidence.domain.execution import ExecutionDenied, ExecutionInput
from pastport_evidence.domain.idml import IDMLMatchBatch, IDMLMatchReviews
from pastport_evidence.domain.models import DomainModel

Payload=TypeVar('Payload',bound=DomainModel)


class MeteredIDMLMatchGateway:
    def __init__(self, executor: SubscriptionExecutor, *, policy: Literal["v1", "v2", "v3", "v4"] = "v1") -> None:
        self.executor=executor
        self.policy=policy

    def _execute(self, request: IDMLMatchRequest, images: tuple[Path,...],
                 output: type[Payload], policy: str) -> tuple[Payload,str]:
        if len(images)>8 or any(p.is_symlink() or not p.is_file() or p.stat().st_size>4*1024**2 for p in images):
            raise ExecutionDenied('IDML images exceed existing transport profile')
        grant=self.executor.grant
        instructions=files('pastport_evidence').joinpath('prompts',policy+'.txt').read_text()
        hashes=[]
        for image in images:
            with image.open('rb') as stream:
                hashes.append(hashlib.file_digest(stream,'sha256').hexdigest())
        schema = output.model_json_schema()
        if self.policy == "v1" and output is IDMLMatchBatch:
            schema["$defs"]["IDMLObjectMatch"]["properties"]["relationship"]["anyOf"][0]["enum"].remove("same_object")
        elif self.policy == "v2" and output is IDMLMatchBatch:
            schema["$defs"]["IDMLObjectMatch"]["properties"]["relationship"]["anyOf"][0]["enum"] = ["same_object"]
        elif self.policy in ("v3", "v4") and output is IDMLMatchBatch:
            schema["$defs"]["IDMLObjectMatch"]["properties"]["relationship"]["anyOf"][0]["enum"] = ["same_object"]
        result=self.executor.execute(ExecutionInput(
            project_id=grant.project_id,grant_ref=grant.grant_ref,model_id=grant.model_id,
            kind='idml_mapping',prompt_version=policy,policy_version='idml-source-'+self.policy,
            instructions=instructions,payload_json=request.model_dump_json(),
            output_schema_json=StrictOutputSchema.convert(json.dumps(schema)),
            image_paths=tuple(str(p) for p in images),image_hashes=tuple(hashes),
        ))
        return output.model_validate_json(result.payload_json),result.receipt_ref

    def propose(self, request: IDMLMatchRequest, images: tuple[Path,...]) -> tuple[IDMLMatchBatch,str]:
        if self.executor.remaining_calls()<2:
            raise ExecutionDenied('IDML proposal and independent audit require two authorized calls')
        return self._execute(request,images,IDMLMatchBatch,'idml_mapping_'+self.policy)

    def audit(self, request: IDMLMatchRequest, images: tuple[Path,...]) -> tuple[IDMLMatchReviews,str]:
        return self._execute(request,images,IDMLMatchReviews,'idml_mapping_audit_'+self.policy)
