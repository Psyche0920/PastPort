"""Retrieve across the corpus, verify exact selectors and enforce display-copy scope."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence

from pastport_pdf_vr.domain.evidence import (
    AssociatedEvidence,
    DisplayCopy,
    DraftRequest,
    EffectiveCopy,
    EvidenceAssessment,
    EvidenceClaim,
    EvidenceProposal,
    EvidenceScope,
    EvidenceSelection,
    ExactPassage,
    HistoricalSubject,
    ImageAssociation,
    PopupProposal,
    SourceImageObservation,
)
from pastport_pdf_vr.domain.pdf import RegisteredPDF
from pastport_pdf_vr.ports.semantics import EvidenceModel


class EvidenceValidationError(ValueError):
    """A candidate quotation, subject relation or sentence is unsupported by its binding."""


class CorpusIndex:
    """Search every source page while retaining original character selectors."""

    def __init__(self, document: RegisteredPDF, passage_characters: int = 1400) -> None:
        if not 100 <= passage_characters <= 8000:
            raise ValueError("Passage character bound must be between 100 and 8000")
        self.document = document
        self.passages = self._chunk(document, passage_characters)

    @staticmethod
    def _chunk(document: RegisteredPDF, size: int) -> tuple[ExactPassage, ...]:
        passages: list[ExactPassage] = []
        for page in document.pages:
            text, start = page.original_text, 0
            while start < len(text):
                while start < len(text) and text[start].isspace():
                    start += 1
                if start == len(text):
                    break
                end = min(start + size, len(text))
                if end < len(text):
                    whitespace = text.rfind(" ", start + size // 2, end)
                    if whitespace != -1:
                        end = whitespace
                while end > start and text[end - 1].isspace():
                    end -= 1
                quote = text[start:end]
                key = f"{document.source.asset.sha256}:{page.page_index}:{start}:{end}"
                passages.append(
                    ExactPassage(
                        passage_id="passage:" + hashlib.sha256(key.encode()).hexdigest(),
                        source=document.source,
                        page_index=page.page_index,
                        start=start,
                        end=end,
                        quote=quote,
                    )
                )
                start = end
        return tuple(passages)

    def select(
        self,
        subject: HistoricalSubject,
        image: SourceImageObservation | None = None,
        max_passages: int = 12,
        max_characters: int = 20_000,
    ) -> tuple[ExactPassage, ...]:
        if not 1 <= max_passages <= 40 or not 100 <= max_characters <= 80_000:
            raise ValueError("Evidence selection exceeds its declared bounds")
        if image is not None:
            self.validate_image(image)
        terms = _tokens(" ".join((subject.label, *subject.retrieval_terms)))
        ranked: list[tuple[float, ExactPassage]] = []
        for passage in self.passages:
            words = _tokens(passage.quote)
            lexical = len(terms & words)
            nearby = image is not None and abs(passage.page_index - image.page_index) <= 1
            if lexical or nearby:
                # Whole-corpus lexical matches outrank mere adjacency.
                ranked.append((lexical * 10.0 + float(nearby), passage))
        ranked.sort(key=lambda item: (-item[0], item[1].page_index, item[1].start))
        selected: list[ExactPassage] = []
        total = 0
        for _, passage in ranked:
            if len(selected) == max_passages:
                break
            if total + len(passage.quote) <= max_characters:
                selected.append(passage)
                total += len(passage.quote)
        return tuple(selected)

    def validate_image(self, image: SourceImageObservation) -> None:
        if image.source != self.document.source or image.page_index >= self.document.page_count:
            raise EvidenceValidationError("Source image belongs to another source/version/page")
        page = self.document.pages[image.page_index]
        if image.region.x0 < 0 or image.region.top < 0:
            raise EvidenceValidationError(
                "Selected source image region lies outside the visible page"
            )
        if image.region.x1 > page.page_width or image.region.bottom > page.page_height:
            raise EvidenceValidationError("Source image region exceeds its PDF page")
        if image.region.x0 >= image.region.x1 or image.region.top >= image.region.bottom:
            raise EvidenceValidationError("Source image region must have positive area")

    def validate_passage(self, passage: ExactPassage) -> None:
        if passage.source != self.document.source or passage.page_index >= self.document.page_count:
            raise EvidenceValidationError("Passage belongs to another source/version/page")
        original = self.document.pages[passage.page_index].original_text
        if original[passage.start : passage.end] != passage.quote:
            raise EvidenceValidationError("Passage selector does not recover its exact quotation")


class EvidenceService:
    def __init__(self, corpus: CorpusIndex, model: EvidenceModel) -> None:
        self._corpus, self._model = corpus, model

    def retrieve_and_associate(
        self, selection: EvidenceSelection, *, allow_partial: bool = False
    ) -> AssociatedEvidence:
        """Permit one corpus-only expansion when the first semantic response needs more context."""
        initial = self.assess(selection, strict=not allow_partial)
        first = initial.proposal
        if not first.retrieval_queries:
            return AssociatedEvidence(
                selection=selection,
                evidence=first,
                retrieval_rounds=1,
                retrieval_gap=False,
                receipt_refs=(first.receipt_ref,),
                validation_gaps=initial.validation_gaps,
            )
        expanded_subject = selection.subject.model_copy(
            update={
                "retrieval_terms": (*selection.subject.retrieval_terms, *first.retrieval_queries)
            }
        )
        found = self._corpus.select(
            expanded_subject, selection.image, max_passages=40, max_characters=40_000
        )
        combined: list[ExactPassage] = []
        seen: set[str] = set()
        characters = 0
        for passage in (*found, *selection.passages):
            if (
                passage.passage_id in seen
                or len(combined) == 40
                or characters + len(passage.quote) > 80_000
            ):
                continue
            seen.add(passage.passage_id)
            combined.append(passage)
            characters += len(passage.quote)
        expanded = selection.model_copy(update={"passages": tuple(combined)})
        final = self.assess(expanded, strict=not allow_partial)
        second = final.proposal
        return AssociatedEvidence(
            selection=expanded,
            evidence=second,
            retrieval_rounds=2,
            retrieval_gap=bool(second.retrieval_queries),
            receipt_refs=(first.receipt_ref, second.receipt_ref),
            validation_gaps=initial.validation_gaps + final.validation_gaps,
        )

    def associate(self, selection: EvidenceSelection) -> EvidenceProposal:
        return self.assess(selection, strict=True).proposal

    def assess(self, selection: EvidenceSelection, *, strict: bool = False) -> EvidenceAssessment:
        """Reject unsupported semantic items independently without rewriting their meaning.

        Invalid source bindings remain fatal. Missing parents never become inferred parents
        or direct facts; a caller opting into partial output receives explicit gaps instead.
        """
        self._validate_selection(selection)
        proposal = self._model.associate(selection)
        passage_ids = {passage.passage_id for passage in selection.passages}
        claims: list[EvidenceClaim] = []
        associations: list[ImageAssociation] = []
        gaps: list[str] = []
        counts: dict[str, int] = {}
        for claim in proposal.claims:
            counts[claim.claim_id] = counts.get(claim.claim_id, 0) + 1
        for claim in proposal.claims:
            try:
                if counts[claim.claim_id] != 1:
                    raise EvidenceValidationError("Model returned duplicate claim IDs")
                self._validate_claim(claim, selection, passage_ids)
            except EvidenceValidationError as error:
                if strict:
                    raise
                gaps.append(f"rejected_claim:{claim.claim_id}:{error}")
            else:
                claims.append(claim)
        for index, association in enumerate(proposal.associations):
            try:
                self._validate_association(association, selection, passage_ids)
            except EvidenceValidationError as error:
                if strict:
                    raise
                gaps.append(f"rejected_association:{index}:{error}")
            else:
                associations.append(association)
        return EvidenceAssessment(
            proposal=proposal.model_copy(
                update={"claims": tuple(claims), "associations": tuple(associations)}
            ),
            validation_gaps=tuple(gaps),
        )

    @staticmethod
    def _validate_association(
        association: ImageAssociation, selection: EvidenceSelection, passage_ids: set[str]
    ) -> None:
        if selection.image is None or association.image_id != selection.image.image_id:
            raise EvidenceValidationError("Image association changed its image or subject binding")
        allowed_subjects = {selection.subject.subject_id}
        if association.scope is EvidenceScope.PARENT_BACKGROUND:
            allowed_subjects = (
                {selection.subject.parent_subject_id}
                if selection.subject.parent_subject_id
                else set()
            )
        if association.subject_id not in allowed_subjects:
            raise EvidenceValidationError("Image subject does not agree with its declared scope")
        if (
            selection.image.depicted_subject_id is not None
            and association.subject_id != selection.image.depicted_subject_id
        ):
            raise EvidenceValidationError("Image depicts a different explicitly identified subject")
        if (
            selection.image.depiction == "page_context"
            and association.scope is EvidenceScope.DIRECT
        ):
            raise EvidenceValidationError("Whole-page context is not a confirmed object photograph")
        if not set(association.passage_ids) <= passage_ids:
            raise EvidenceValidationError("Image association cites an unprovided passage")

    def draft(self, selection: EvidenceSelection, evidence: EvidenceProposal) -> PopupProposal:
        self._validate_selection(selection)
        ids = {passage.passage_id for passage in selection.passages}
        claims = {claim.claim_id: claim for claim in evidence.claims}
        if len(claims) != len(evidence.claims):
            raise EvidenceValidationError("Duplicate claim identity")
        for claim in evidence.claims:
            self._validate_claim(claim, selection, ids)
        popup = self._model.draft(DraftRequest(selection=selection, claims=evidence.claims))
        if popup.subject_id != selection.subject.subject_id:
            raise EvidenceValidationError(
                "Popup subject differs from the assigned historical subject"
            )
        for sentence in (*popup.introduction, *popup.background):
            if not set(sentence.claim_ids) <= claims.keys():
                raise EvidenceValidationError("Popup sentence cites an unknown claim")
        for sentence in popup.introduction:
            if any(claims[key].scope is not EvidenceScope.DIRECT for key in sentence.claim_ids):
                raise EvidenceValidationError(
                    "Broader context cannot be presented as a direct object fact"
                )
        if (
            sum(len(sentence.text) for sentence in popup.introduction) > 1200
            or sum(len(sentence.text) for sentence in popup.background) > 6000
        ):
            raise EvidenceValidationError("Popup copy exceeds its display-length policy")
        return popup

    def _validate_selection(self, selection: EvidenceSelection) -> None:
        if sum(len(passage.quote) for passage in selection.passages) > 80_000:
            raise EvidenceValidationError("Selected evidence exceeds the bounded context profile")
        if len({passage.passage_id for passage in selection.passages}) != len(selection.passages):
            raise EvidenceValidationError("Selected passages contain duplicate identities")
        for passage in selection.passages:
            self._corpus.validate_passage(passage)
        if selection.image:
            self._corpus.validate_image(selection.image)

    @staticmethod
    def _validate_claim(
        claim: EvidenceClaim, selection: EvidenceSelection, passage_ids: set[str]
    ) -> None:
        if not set(claim.passage_ids) <= passage_ids:
            raise EvidenceValidationError("Claim cites an unprovided passage")
        if claim.scope is EvidenceScope.DIRECT:
            valid_subjects = {selection.subject.subject_id}
        elif claim.scope is EvidenceScope.PARENT_BACKGROUND:
            valid_subjects = (
                {selection.subject.parent_subject_id}
                if selection.subject.parent_subject_id
                else set()
            )
        else:
            valid_subjects = {selection.subject.subject_id}
            if selection.subject.parent_subject_id:
                valid_subjects.add(selection.subject.parent_subject_id)
        if (
            claim.scope is EvidenceScope.PARENT_BACKGROUND
            and not selection.subject.parent_subject_id
        ):
            raise EvidenceValidationError(
                "Parent background requires an explicitly registered parent"
            )
        if claim.subject_id not in valid_subjects:
            raise EvidenceValidationError("Claim subject does not agree with its declared scope")


def resolve_effective_copy(
    subject_id: str, ai_versions: Sequence[DisplayCopy], human_versions: Sequence[DisplayCopy]
) -> EffectiveCopy:
    humans = [copy for copy in human_versions if copy.subject_id == subject_id]
    drafts = [copy for copy in ai_versions if copy.subject_id == subject_id]
    mismatch = any(copy.subject_id != subject_id for copy in human_versions)
    mismatch = mismatch and not humans
    if humans:
        return EffectiveCopy(
            content=max(humans, key=lambda copy: copy.version),
            origin="human",
            assignment_mismatch=mismatch,
        )
    return EffectiveCopy(
        content=max(drafts, key=lambda copy: copy.version) if drafts else None,
        origin="ai" if drafts else "unbound",
        assignment_mismatch=mismatch,
    )


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w{2,}", unicodedata.normalize("NFKC", text).casefold()))
