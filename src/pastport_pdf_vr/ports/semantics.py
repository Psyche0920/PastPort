"""Inject a shared metered gateway; application services never instantiate paid SDKs."""

from typing import Protocol

from pastport_pdf_vr.domain.evidence import (
    DraftRequest,
    EvidenceProposal,
    EvidenceSelection,
    PopupProposal,
)
from pastport_pdf_vr.domain.recognition import SceneInspection, SceneInspectionRequest


class EvidenceModel(Protocol):
    """The gateway validates grants and attaches receipts independently of model text."""

    def associate(self, request: EvidenceSelection) -> EvidenceProposal: ...
    def draft(self, request: DraftRequest) -> PopupProposal: ...


class SceneInspector(Protocol):
    """One bounded inspection; receipts come from metered execution, never model output."""

    def inspect(self, request: SceneInspectionRequest) -> SceneInspection: ...
