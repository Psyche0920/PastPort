"""Evidence candidates and snapshots; validation never grants human approval."""

from typing import Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import (
    ArtifactRef,
    Contract,
    Identifier,
    NonNegative,
    Sha256,
    SourceLocator,
    Text,
    VersionedPayload,
    unique,
)


class Source(Contract):
    source_id: Identifier
    version: Identifier
    file_sha256: Sha256
    origin: Literal["official", "external", "synthetic"]
    title: Text
    uri: Text
    acquisition_state: Literal["discovered", "downloaded", "parsed", "failed"]
    extraction_state: Literal["extracted", "needs_ocr", "checked", "failed"]


class Site(Contract):
    site_id: Identifier
    name: Text


class Claim(Contract):
    claim_id: Identifier
    version: Identifier
    text: Text
    site_id: Identifier
    structure_id: Identifier | None
    time_scope: Text
    content_kind: Literal["historical_fact", "interpretation", "original_fiction"]
    support: tuple[SourceLocator, ...]
    refute: tuple[SourceLocator, ...]
    judgment: Literal["supported", "qualified", "conflicting", "insufficient"]
    reason: Text
    approved_wording: Text | None


class Asset(Contract):
    asset_id: Identifier
    version: Identifier
    original_sha256: Sha256
    derivative_sha256: Sha256
    source_locator: SourceLocator
    site_id: Identifier
    structure_id: Identifier | None
    mapping_state: Literal["unmapped", "provisional", "verified"]
    rights_state: Literal["unknown", "restricted", "permitted_for_scope", "open_license"]
    allowed_uses: tuple[Literal["internal_preview", "public"], ...]
    rights_basis: Text
    alt_text: Text


class SpatialEdge(Contract):
    edge_id: Identifier
    from_site_id: Identifier
    to_site_id: Identifier
    source_refs: tuple[SourceLocator, ...] = Field(min_length=1)
    verification_state: Literal["unknown", "verified"]
    distance_metres: NonNegative | None
    walking_seconds: NonNegative | None


class Place(Contract):
    site_id: Identifier
    building_id: Identifier | None


class RouteRecord(VersionedPayload):
    route_id: Identifier
    candidate_id: Identifier
    scope_hash: Sha256
    ordered_places: tuple[Place, ...] = Field(min_length=1)
    edge_refs: tuple[Identifier, ...]
    entry_refs: tuple[SourceLocator, ...]
    exit_refs: tuple[SourceLocator, ...]
    source_refs: tuple[SourceLocator, ...] = Field(min_length=1)
    unknowns: tuple[Text, ...]


class Coverage(Contract):
    site_id: Identifier
    disposition: Literal["main", "optional", "deferred", "excluded"]
    reason: Text


class SourceManifestDraft(VersionedPayload):
    source_folder_id: Identifier
    sources: tuple[Source, ...]
    failures: tuple[Text, ...]


class SourceIndexDraft(VersionedPayload):
    source_folder_id: Identifier
    sources: tuple[Source, ...]
    sites: tuple[Site, ...]
    candidate_claims: tuple[Claim, ...]
    candidate_assets: tuple[Asset, ...]
    fragments: tuple[SourceLocator, ...]
    unresolved_items: tuple[Text, ...]


class EvidencePackage(VersionedPayload):
    source_folder_id: Identifier
    scope: tuple[Identifier, ...] = Field(min_length=1)
    sources: tuple[Source, ...] = Field(min_length=1)
    sites: tuple[Site, ...] = Field(min_length=1)
    claims: tuple[Claim, ...]
    assets: tuple[Asset, ...]
    spatial_edges: tuple[SpatialEdge, ...]
    route_refs: tuple[ArtifactRef, ...] = Field(min_length=1)
    coverage: tuple[Coverage, ...]
    unresolved_items: tuple[Text, ...]

    @model_validator(mode="after")
    def identities(self) -> Self:
        for values, label in (
            ((x.source_id for x in self.sources), "source IDs"),
            ((x.site_id for x in self.sites), "site IDs"),
            ((x.claim_id for x in self.claims), "claim IDs"),
            ((x.asset_id for x in self.assets), "asset IDs"),
            ((x.edge_id for x in self.spatial_edges), "edge IDs"),
        ):
            unique(values, label)
        unique(self.scope, "scope sites")
        unique((x.site_id for x in self.coverage), "coverage sites")
        sites = {x.site_id for x in self.sites}
        if not set(self.scope) <= sites or {x.site_id for x in self.coverage} != sites:
            raise ValueError("Scope and coverage must refer to registered sites")
        if any(x.project_id != self.project_id or x.kind != "route" for x in self.route_refs):
            raise ValueError("Route references must belong to this project")
        for claim in self.claims:
            if claim.site_id not in sites:
                raise ValueError("Unknown claim site")
        for asset in self.assets:
            if asset.site_id not in sites:
                raise ValueError("Unknown asset site")
        for edge in self.spatial_edges:
            if edge.from_site_id not in sites or edge.to_site_id not in sites:
                raise ValueError("Unknown spatial endpoint")
        sources = {x.source_id: x for x in self.sources}
        locators = [loc for x in self.claims for loc in (*x.support, *x.refute)]
        locators += [x.source_locator for x in self.assets]
        locators += [loc for x in self.spatial_edges for loc in x.source_refs]
        for loc in locators:
            source = sources.get(loc.source_id)
            if not source or (source.version, source.file_sha256) != (
                loc.source_version,
                loc.file_sha256,
            ):
                raise ValueError("Source locator version/hash mismatch")
        return self
