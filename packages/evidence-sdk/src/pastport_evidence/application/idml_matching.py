"""Match every recognized identity and compile only exact source-native citations."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol
import hashlib
from pastport_evidence.domain.idml import (
    IDMLCompiledObject, IDMLDocument, IDMLExactCitation, IDMLMatchBatch,
    IDMLMatchResult, IDMLMatchReviews, IDMLMatchReview,
)
from pastport_evidence.domain.models import DomainModel
from pastport_evidence.domain.recognition import SceneEntity


class IDMLMatchRequest(DomainModel):
    source: IDMLDocument
    objects: tuple[SceneEntity, ...]
    proposals: IDMLMatchBatch | None = None


class IDMLMatchPort(Protocol):
    def propose(self, request: IDMLMatchRequest, images: tuple[Path, ...]) -> tuple[IDMLMatchBatch,str]: ...
    def audit(self, request: IDMLMatchRequest, images: tuple[Path, ...]) -> tuple[IDMLMatchReviews,str]: ...


class IDMLMatchCompiler:
    """Semantic approval cannot override missing identities or nonexistent quotations."""

    def compile(self, request: IDMLMatchRequest, proposals: IDMLMatchBatch,
                reviews: IDMLMatchReviews, receipts: tuple[str,...]) -> IDMLMatchResult:
        expected={obj.object_id for obj in request.objects}
        if len(expected)!=len(request.objects) or not expected:
            raise ValueError('Recognized identities must be nonempty and unique')
        for rows in (proposals.objects,reviews.objects):
            if len(rows)!=len(expected) or {row.object_id for row in rows}!=expected:
                raise ValueError('Every recognized identity needs exactly one disposition')
        stories={story.story_id:story for story in request.source.stories}
        images={image.image_id:image for image in request.source.images}
        verdicts={review.object_id:review for review in reviews.objects}
        compiled=[]
        for proposal in proposals.objects:
            citations=[]
            for claim in proposal.claims:
                for selected in claim.citations:
                    story=stories.get(selected.story_id)
                    if story is None or not 0<=selected.paragraph_index<len(story.paragraphs):
                        raise ValueError('Historical claim refers to nonexistent IDML paragraph')
                    paragraph=story.paragraphs[selected.paragraph_index]
                    if paragraph.text.count(selected.quote)!=1:
                        raise ValueError('Quotation is missing or ambiguous in selected source paragraph')
                    start=paragraph.start+paragraph.text.index(selected.quote)
                    citations.append(IDMLExactCitation(story_id=story.story_id,member=story.member,
                        paragraph_index=selected.paragraph_index,start=start,end=start+len(selected.quote),quote=selected.quote))
            if proposal.image_id is not None:
                image=images.get(proposal.image_id)
                if image is None or image.link_state!='available':
                    raise ValueError('Historical image was not supplied and fingerprinted')
            if proposal.image_role=='object_image' and proposal.image_id is None:
                raise ValueError('Historical object photograph cannot be invented')
            verdict=verdicts[proposal.object_id]
            status: Literal['unmatched','matched','requires_review']='unmatched' if proposal.status=='unmatched' else 'matched' if verdict.verdict=='confirmed' else 'requires_review'
            compiled.append(IDMLCompiledObject(
                object_id=proposal.object_id,status=status,
                historical_name=proposal.historical_name,relationship=proposal.relationship,
                image_id=proposal.image_id,image_role=proposal.image_role,
                introduction='\n\n'.join(claim.text for claim in proposal.claims),
                citations=tuple(citations),rationale=proposal.rationale,
                limitations=proposal.limitations,review_reason=verdict.reason,
            ))
        return IDMLMatchResult(source_sha256=request.source.source_sha256,
                               objects=tuple(compiled),receipt_refs=receipts)


class IDMLMatchingService:
    def __init__(self, gateway: IDMLMatchPort) -> None:
        self.gateway=gateway

    def run(self, request: IDMLMatchRequest, images: tuple[Path,...], output: Path,
            persist: Callable[[Path,str], None]) -> IDMLMatchResult:
        # Gateway retains its normal ledger, cancellation, grants and no-retry policy.
        binding=hashlib.sha256(request.model_dump_json().encode())
        for image in images:
            with image.open('rb') as stream:
                binding.update(hashlib.file_digest(stream,'sha256').digest())
        output.mkdir(parents=True,exist_ok=True)
        lock=output/'idml-match-input.sha256'
        if lock.exists() and lock.read_text()!=binding.hexdigest():
            raise ValueError('Saved IDML matching belongs to different inputs')
        if not lock.exists():
            persist(lock,binding.hexdigest())
        proposal_file=output/'idml-proposals.json'
        review_file=output/'idml-review.json'
        receipts=[]
        if proposal_file.exists():
            proposals=IDMLMatchBatch.model_validate_json(proposal_file.read_bytes())
            receipts.append((output/'idml-proposal-receipt.txt').read_text())
        else:
            proposals,receipt=self.gateway.propose(request,images)
            persist(proposal_file,proposals.model_dump_json())
            persist(output/'idml-proposal-receipt.txt',receipt);receipts.append(receipt)
        preflight=IDMLMatchReviews(objects=tuple(
            IDMLMatchReview(object_id=obj.object_id,verdict='uncertain',reason='preflight')
            for obj in request.objects))
        IDMLMatchCompiler().compile(request,proposals,preflight,())
        if review_file.exists():
            reviews=IDMLMatchReviews.model_validate_json(review_file.read_bytes())
            receipts.append((output/'idml-review-receipt.txt').read_text())
        else:
            reviews,receipt=self.gateway.audit(request.model_copy(update={'proposals':proposals}),images)
            persist(review_file,reviews.model_dump_json())
            persist(output/'idml-review-receipt.txt',receipt);receipts.append(receipt)
        result=IDMLMatchCompiler().compile(request,proposals,reviews,tuple(receipts))
        persist(output/'idml-matches.json',result.model_dump_json(indent=2))
        return result
