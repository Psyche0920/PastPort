"""Build media manifests from reviewed asset identities; never from a prebuilt runtime template."""

from pastport.application.models import ServiceError
from pastport.application.resources import MEDIA_EXTENSIONS, RESOURCE_LIMIT, VerifiedResourceReader
from pastport.domain.common import CanonicalSerializer
from pastport.domain.modules import AssemblyRequest, AssemblyResult, PackageValidationRequest
from pastport.domain.packages import MediaEntry, RuntimePackage, ValidationReport
from pastport.domain.resources import ResourceReference
from pastport.ports.resources import ResourceReader


class PackageAssembler:
    def __init__(self, resources: ResourceReader) -> None:
        self.resources = VerifiedResourceReader(resources)

    def assemble(self, request: AssemblyRequest) -> AssemblyResult:
        media = []
        for asset in sorted(request.evidence.evidence.assets, key=lambda item: item.asset_id):
            if (
                asset.mapping_state != "verified"
                or asset.rights_state not in ("permitted_for_scope", "open_license")
                or "internal_preview" not in asset.allowed_uses
            ):
                raise ServiceError(
                    "ASSET_NOT_USABLE", "Asset mapping and internal-preview rights must be verified"
                )
            resource = self.resources.read(
                ResourceReference(
                    project_id=request.narrative.project_id,
                    resource_id=asset.asset_id,
                    kind="asset",
                    version=asset.version,
                    sha256=asset.derivative_sha256,
                ),
                RESOURCE_LIMIT,
            )
            extension = MEDIA_EXTENSIONS.get(resource.media_type)
            if extension is None:
                raise ServiceError(
                    "MEDIA_TYPE_UNSUPPORTED", "Asset is not a supported image format"
                )
            media.append(
                MediaEntry(
                    asset_id=asset.asset_id,
                    sha256=asset.derivative_sha256,
                    relative_path="media/"
                    + asset.asset_id
                    + "-"
                    + asset.derivative_sha256
                    + "."
                    + extension,
                )
            )
        package = RuntimePackage(
            project_id=request.narrative.project_id,
            schema_version="0.1.0",
            content_version=request.narrative.content_version,
            package_id="package-" + request.narrative_ref.artifact_id,
            runtime_compatibility=request.runtime_capabilities,
            evidence_package_hash=request.evidence.evidence_ref.sha256,
            narrative_package_hash=request.narrative_ref.sha256,
            game=request.narrative.game,
            media_manifest=tuple(media),
        )
        report = self.validate(
            PackageValidationRequest(
                package=package,
                runtime_capabilities=request.runtime_capabilities,
                checks=("schema", "references", "media_hashes"),
            )
        )
        return AssemblyResult(package=package, report=report)

    def validate(self, request: PackageValidationRequest) -> ValidationReport:
        if request.package.runtime_compatibility != request.runtime_capabilities:
            raise ServiceError(
                "CAPABILITY_UNSUPPORTED",
                "Package capabilities differ from the validator capabilities",
            )
        for item in request.package.media_manifest:
            self.resources.read(
                ResourceReference(
                    project_id=request.package.project_id,
                    resource_id=item.asset_id,
                    kind="asset",
                    sha256=item.sha256,
                ),
                RESOURCE_LIMIT,
            )
        return ValidationReport(
            artifact_hash=CanonicalSerializer.digest(request.package),
            checked=("schema", "references", "media_hashes"),
            issues=(),
            unverified=("Rule paths have not been executed by a player runtime.",),
        )
