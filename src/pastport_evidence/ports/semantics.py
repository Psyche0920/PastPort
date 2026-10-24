"""Inject a shared metered gateway; application services never instantiate paid SDKs."""

from typing import Protocol

from pastport_evidence.domain.evidence import (
    EvidenceProposal,
    EvidenceSelection,
)


class EvidenceModel(Protocol):
    """The gateway validates grants and attaches receipts independently of model text."""

    def associate(self, request: EvidenceSelection) -> EvidenceProposal: ...
