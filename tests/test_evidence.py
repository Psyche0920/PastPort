import unittest

from pastport_pdf_vr.application.evidence import (
    CorpusIndex,
    EvidenceService,
    EvidenceValidationError,
    resolve_effective_copy,
)
from pastport_pdf_vr.domain.evidence import (
    DisplayCopy,
    DisplaySentence,
    DraftRequest,
    EvidenceClaim,
    EvidenceProposal,
    EvidenceScope,
    EvidenceSelection,
    HistoricalSubject,
    ImageAssociation,
    PopupProposal,
    SourceImageObservation,
)
from pastport_pdf_vr.domain.pdf import PDFExtractionStatus, PDFPageContent, PDFRegion, RegisteredPDF
from tests.support import asset


class FixtureEvidenceModel:
    """Supplies explicit candidate claims to exercise policy, not historical truth."""

    def __init__(self) -> None:
        self.leak_parent = False

    def associate(self, request: EvidenceSelection) -> EvidenceProposal:
        direct = next(p for p in request.passages if "hearth" in p.quote)
        broader = next(p for p in request.passages if "forty" in p.quote)
        return EvidenceProposal(
            associations=(
                ImageAssociation(
                    image_id="picture",
                    subject_id="room",
                    passage_ids=(direct.passage_id,),
                    basis="Room facilities described on a separate page",
                ),
            ),
            claims=(
                EvidenceClaim(
                    claim_id="direct",
                    subject_id="room",
                    scope=EvidenceScope.DIRECT,
                    statement="The room has a hearth.",
                    passage_ids=(direct.passage_id,),
                ),
                EvidenceClaim(
                    claim_id="building",
                    subject_id="madrasa",
                    scope=EvidenceScope.PARENT_BACKGROUND,
                    statement="The building is forty metres long.",
                    passage_ids=(broader.passage_id,),
                ),
            ),
            receipt_ref="fixture:evidence",
        )

    def draft(self, request: DraftRequest) -> PopupProposal:
        return PopupProposal(
            subject_id="room",
            introduction=(
                DisplaySentence(
                    text="The room has a hearth.",
                    claim_ids=("building" if self.leak_parent else "direct",),
                ),
            ),
            background=(
                DisplaySentence(
                    text="The parent building is forty metres long.", claim_ids=("building",)
                ),
            ),
            receipt_ref="fixture:popup",
        )


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        source = asset("source")
        texts = (
            "Student-room photograph and a short caption.",
            "Each student room contains a hearth and a niche for storage.",
            "The madrasa building is forty metres long.",
        )
        self.document = RegisteredPDF(
            source=source,
            page_count=3,
            extractor_version="fixture-v1",
            pages=tuple(
                PDFPageContent(
                    page_index=index,
                    page_width=600.0,
                    page_height=800.0,
                    original_text=text,
                    normalized_text=text,
                    text_lines=(),
                    image_regions=(),
                    extraction_status=PDFExtractionStatus.TEXT_EXTRACTED,
                    rendered_page=asset(f"page{index}"),
                )
                for index, text in enumerate(texts)
            ),
        )
        self.index = CorpusIndex(self.document)
        subject = HistoricalSubject(
            subject_id="room",
            label="Student room",
            parent_subject_id="madrasa",
            retrieval_terms=("hearth", "madrasa", "forty"),
        )
        image = SourceImageObservation(
            image_id="picture",
            source=source,
            page_index=0,
            region=PDFRegion(x0=10.0, top=10.0, x1=300.0, bottom=300.0),
            description="Student room photograph",
        )
        self.selection = EvidenceSelection(
            subject=subject,
            image=image,
            passages=self.index.select(subject, image),
            prompt_version="evidence-v1",
            policy_version="scope-v1",
            grant_ref="fixture:grant",
            model_id="fixture:vision-v1",
        )

    def test_cross_page_retrieval_exact_quotes_and_separate_background(self) -> None:
        self.assertIn(2, {p.page_index for p in self.selection.passages})
        for passage in self.selection.passages:
            self.index.validate_passage(passage)
        model = FixtureEvidenceModel()
        service = EvidenceService(self.index, model)
        evidence = service.associate(self.selection)
        popup = service.draft(self.selection, evidence)
        self.assertEqual(popup.introduction[0].claim_ids, ("direct",))
        self.assertEqual(popup.background[0].claim_ids, ("building",))
        model.leak_parent = True
        with self.assertRaises(EvidenceValidationError):
            service.draft(self.selection, evidence)
        assert self.selection.image is not None
        page_context = self.selection.model_copy(
            update={"image": self.selection.image.model_copy(update={"depiction": "page_context"})}
        )
        with self.assertRaises(EvidenceValidationError):
            service.associate(page_context)

    def test_modified_quote_wrong_source_and_oversized_region_are_rejected(self) -> None:
        passage = self.selection.passages[0]
        altered = passage.model_copy(update={"quote": "x" * len(passage.quote)})
        with self.assertRaises(EvidenceValidationError):
            self.index.validate_passage(altered)
        wrong = passage.model_copy(update={"source": asset("other")})
        with self.assertRaises(EvidenceValidationError):
            self.index.validate_passage(wrong)
        assert self.selection.image is not None
        wrong_image = self.selection.image.model_copy(
            update={"region": PDFRegion(x0=0.0, top=0.0, x1=900.0, bottom=300.0)}
        )
        with self.assertRaises(EvidenceValidationError):
            self.index.validate_image(wrong_image)
        # PDF bleed is valid raw extraction geometry, but cannot be selected as
        # an on-page visible crop without an explicit intersection with the page.
        bleed = PDFRegion(x0=-0.000061, top=-1.25898, x1=300.0, bottom=300.0)
        self.assertLess(bleed.top, 0)
        with self.assertRaises(EvidenceValidationError):
            self.index.validate_image(self.selection.image.model_copy(update={"region": bleed}))

    def test_missing_parent_rejects_background_without_losing_valid_claims(self) -> None:
        selection = self.selection.model_copy(
            update={
                "subject": self.selection.subject.model_copy(update={"parent_subject_id": None})
            }
        )
        model = FixtureEvidenceModel()
        service = EvidenceService(self.index, model)
        with self.assertRaisesRegex(EvidenceValidationError, "explicitly registered parent"):
            service.associate(selection)
        assessed = service.retrieve_and_associate(selection, allow_partial=True)
        self.assertEqual([c.claim_id for c in assessed.evidence.claims], ["direct"])
        self.assertEqual(len(assessed.evidence.associations), 1)
        self.assertEqual(len(assessed.validation_gaps), 1)
        self.assertIn("rejected_claim:building", assessed.validation_gaps[0])
        self.assertIsNone(assessed.selection.subject.parent_subject_id)
        # Neither fabricate a parent nor promote a rejected background to a direct fact.
        self.assertEqual(len(model.associate(selection).claims), 2)

    def test_latest_human_copy_wins_and_reassignment_never_reuses_old_copy(self) -> None:
        ai = DisplayCopy(subject_id="room", version=99, introduction="Newest AI")
        humans = (
            DisplayCopy(subject_id="room", version=1, introduction="Earlier human"),
            DisplayCopy(subject_id="room", version=2, introduction="Latest human"),
        )
        effective = resolve_effective_copy("room", (ai,), humans)
        self.assertEqual(effective.origin, "human")
        self.assertEqual(effective.content, humans[1])
        changed = resolve_effective_copy("fountain", (ai,), humans)
        self.assertIsNone(changed.content)
        self.assertTrue(changed.assignment_mismatch)

    def test_context_expansion_is_corpus_bound_and_stops_after_two_calls(self) -> None:
        class ExpandingModel(FixtureEvidenceModel):
            def __init__(self, repeat: bool = False) -> None:
                super().__init__()
                self.calls = 0
                self.repeat = repeat

            def associate(self, request: EvidenceSelection) -> EvidenceProposal:
                self.calls += 1
                if self.calls == 1 or self.repeat:
                    return EvidenceProposal(
                        associations=(),
                        claims=(),
                        retrieval_queries=("hearth", "forty"),
                        receipt_ref=f"fixture:search{self.calls}",
                    )
                return super().associate(request)

        reduced = self.selection.model_copy(
            update={"passages": tuple(p for p in self.selection.passages if p.page_index == 0)}
        )
        model = ExpandingModel()
        service = EvidenceService(self.index, model)
        linked = service.retrieve_and_associate(reduced)
        self.assertEqual(linked.retrieval_rounds, 2)
        self.assertEqual(model.calls, 2)
        self.assertFalse(linked.retrieval_gap)
        self.assertTrue(linked.evidence.claims)
        self.assertTrue(service.draft(linked.selection, linked.evidence).introduction)
        repeating = ExpandingModel(repeat=True)
        unresolved = EvidenceService(self.index, repeating).retrieve_and_associate(reduced)
        self.assertTrue(unresolved.retrieval_gap)
        self.assertEqual(repeating.calls, 2)
