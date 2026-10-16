"""Cross-package contract checking, distinct from authorisation and runtime execution."""

from typing import Literal, Self

from pydantic import Field, model_validator

from pastport.domain.common import (
    ArtifactRef,
    CanonicalSerializer,
    Contract,
    Environment,
    Identifier,
    ReviewDecision,
    Sha256,
    Text,
    ValidationIssue,
    VersionedPayload,
    unique,
)
from pastport.domain.evidence import EvidencePackage, RouteRecord
from pastport.domain.game import GameContent, InspectTask, NarrativePackage, RuntimeCapabilities


class MediaEntry(Contract):
    asset_id: Identifier
    sha256: Sha256
    relative_path: Text

    @model_validator(mode="after")
    def safe_relative_path(self) -> Self:
        path = self.relative_path
        if path.startswith(("/", "\\")) or "\\" in path or ":" in path or "%" in path:
            raise ValueError("Media path must be a plain package-relative path")
        if any(part in ("", ".", "..") for part in path.split("/")):
            raise ValueError("Unsafe package path")
        return self


class RuntimePackage(VersionedPayload):
    package_id: Identifier
    runtime_compatibility: RuntimeCapabilities
    evidence_package_hash: Sha256
    narrative_package_hash: Sha256
    game: GameContent
    media_manifest: tuple[MediaEntry, ...]


class ValidationReport(Contract):
    artifact_hash: Sha256
    checked: tuple[
        Literal["schema", "references", "review_bindings", "media_hashes", "rule_paths"], ...
    ]
    issues: tuple[ValidationIssue, ...]
    unverified: tuple[Text, ...]


class ReviewTarget(Contract):
    target_id: Identifier
    version: Identifier
    sha256: Sha256
    gate: Literal["evidence", "narrative", "publication"]


class ReviewSnapshot(Contract):
    environment: Environment
    required_targets: tuple[ReviewTarget, ...] = Field(min_length=1)
    decisions: tuple[ReviewDecision, ...]

    @model_validator(mode="after")
    def exact_binding(self) -> Self:
        unique((x.target_id for x in self.required_targets), "review targets")
        unique((x.decision_id for x in self.decisions), "review decisions")
        for target in self.required_targets:
            matching = [
                d
                for d in self.decisions
                if (d.target_id, d.target_version, d.target_hash, d.gate, d.environment)
                == (target.target_id, target.version, target.sha256, target.gate, self.environment)
            ]
            if len(matching) != 1 or matching[0].decision != "approved":
                raise ValueError("Required approval missing, stale, rejected or ambiguous")
        return self


class ContractViolation(ValueError):
    """A bundle is internally inconsistent; this does not replace live policy checks."""


class PackageBundle(Contract):
    environment: Environment
    distribution_scope: Literal["internal_preview", "public"]
    route: RouteRecord
    route_ref: ArtifactRef
    evidence: EvidencePackage
    evidence_ref: ArtifactRef
    narrative: NarrativePackage
    narrative_ref: ArtifactRef
    runtime: RuntimePackage
    runtime_ref: ArtifactRef
    reviews: ReviewSnapshot

    @model_validator(mode="after")
    def coherent(self) -> Self:
        try:
            BundleValidator().validate(self)
        except ContractViolation as error:
            raise ValueError(str(error)) from error
        return self


class BundleValidator:
    """Check content/hash/reference bindings without granting publication authority."""

    @staticmethod
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ContractViolation(message)

    def validate(self, bundle: PackageBundle) -> None:
        require = self.require
        project = bundle.evidence.project_id
        require(
            bundle.environment == "test"
            or all(source.origin != "synthetic" for source in bundle.evidence.sources),
            "Synthetic sources cannot be promoted to production",
        )
        require(bundle.environment == bundle.reviews.environment, "Review environment mismatch")
        require(
            not (bundle.environment == "test" and bundle.distribution_scope == "public"),
            "Synthetic approvals cannot enter public distribution",
        )
        pairs: tuple[tuple[VersionedPayload, ArtifactRef, str], ...] = (
            (bundle.route, bundle.route_ref, "route"),
            (bundle.evidence, bundle.evidence_ref, "evidence"),
            (bundle.narrative, bundle.narrative_ref, "narrative"),
            (bundle.runtime, bundle.runtime_ref, "runtime"),
        )
        for payload, ref, kind in pairs:
            require(payload.project_id == project == ref.project_id, "Cross-project package")
            require(
                ref.kind == kind
                and ref.schema_version == payload.schema_version
                and ref.content_version == payload.content_version
                and ref.sha256 == CanonicalSerializer.digest(payload),
                "Artifact hash/version mismatch",
            )
        require(
            bundle.narrative.evidence_package_hash == bundle.evidence_ref.sha256,
            "Narrative evidence dependency changed",
        )
        require(
            bundle.runtime.evidence_package_hash == bundle.evidence_ref.sha256
            and bundle.runtime.narrative_package_hash == bundle.narrative_ref.sha256,
            "Runtime dependencies changed",
        )
        require(
            bundle.route_ref in bundle.evidence.route_refs
            and bundle.narrative.routes == (bundle.route_ref,),
            "Route binding mismatch",
        )
        require(bundle.route.candidate_id == bundle.narrative.candidate_id, "Direction mismatch")
        require(not bundle.route.unknowns, "Required route remains unresolved")
        require(bundle.runtime.game == bundle.narrative.game, "Assembly must not rewrite gameplay")
        game = bundle.narrative.game
        sites = {x.site_id for x in bundle.evidence.sites}
        places = {x.site_id for x in bundle.route.ordered_places}
        require(places <= sites and places <= set(bundle.evidence.scope), "Unknown route site")
        require(all(x.site_id in places for x in game.scenes), "Scene outside approved route")
        edges = {x.edge_id: x for x in bundle.evidence.spatial_edges}
        require(
            len(bundle.route.edge_refs) == len(bundle.route.ordered_places) - 1,
            "Route needs one edge per transition",
        )
        for i, edge_id in enumerate(bundle.route.edge_refs):
            edge = edges.get(edge_id)
            require(edge is not None, "Route edge missing")
            if edge is not None:
                require(
                    edge.verification_state == "verified"
                    and edge.from_site_id == bundle.route.ordered_places[i].site_id
                    and edge.to_site_id == bundle.route.ordered_places[i + 1].site_id,
                    "Unverified or mismatched route edge",
                )
        sources = {x.source_id: x for x in bundle.evidence.sources}
        for loc in (*bundle.route.source_refs, *bundle.route.entry_refs, *bundle.route.exit_refs):
            source = sources.get(loc.source_id)
            require(
                source is not None
                and source.version == loc.source_version
                and source.file_sha256 == loc.file_sha256,
                "Route source mismatch",
            )
        claims = {x.claim_id: x for x in bundle.evidence.claims}
        assets = {x.asset_id: x for x in bundle.evidence.assets}
        targets: list[ReviewTarget] = []
        for scene in game.scenes:
            for task in scene.tasks:
                for claim_id in task.evidence_refs:
                    claim = claims.get(claim_id)
                    require(claim is not None, "Unknown task claim")
                    if claim is not None:
                        require(
                            claim.judgment in ("supported", "qualified") and bool(claim.support),
                            "Unsupported fact cannot become an answer",
                        )
                        require(
                            claim.content_kind != "original_fiction",
                            "Fiction is not historical evidence",
                        )
                        require(
                            claim.judgment != "qualified" or claim.approved_wording is not None,
                            "Qualified claim needs approved wording",
                        )
                        targets.append(
                            ReviewTarget(
                                target_id=claim.claim_id,
                                version=claim.version,
                                sha256=CanonicalSerializer.digest(claim),
                                gate="evidence",
                            )
                        )
                if isinstance(task, InspectTask):
                    asset = assets.get(task.asset_id)
                    require(asset is not None, "Unknown task asset")
                    if asset is not None:
                        require(
                            asset.site_id == scene.site_id and asset.mapping_state == "verified",
                            "Wrong or unverified image mapping",
                        )
                        require(
                            asset.rights_state in ("permitted_for_scope", "open_license")
                            and bundle.distribution_scope in asset.allowed_uses,
                            "Media rights do not cover use",
                        )
                        targets.append(
                            ReviewTarget(
                                target_id=asset.asset_id,
                                version=asset.version,
                                sha256=CanonicalSerializer.digest(asset),
                                gate="evidence",
                            )
                        )
                    for spot in task.spots:
                        require(
                            set(spot.claim_ids) <= set(task.evidence_refs),
                            "Spot claim outside task evidence",
                        )
        media = bundle.runtime.media_manifest
        unique((x.asset_id for x in media), "media entries")
        require({x.asset_id for x in media} == set(assets), "Media manifest does not match assets")
        require(
            all(x.sha256 == assets[x.asset_id].derivative_sha256 for x in media),
            "Media derivative hash mismatch",
        )
        package_targets: tuple[
            tuple[ArtifactRef, Literal["evidence", "narrative", "publication"]], ...
        ] = (
            (bundle.route_ref, "evidence"),
            (bundle.evidence_ref, "evidence"),
            (bundle.narrative_ref, "narrative"),
            (bundle.runtime_ref, "publication"),
        )
        for ref, gate in package_targets:
            targets.append(
                ReviewTarget(
                    target_id=ref.artifact_id,
                    version=ref.content_version,
                    sha256=ref.sha256,
                    gate=gate,
                )
            )
        require(
            set(targets) <= set(bundle.reviews.required_targets), "Required review target omitted"
        )
