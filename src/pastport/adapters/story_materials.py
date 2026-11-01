"""Normalize explicitly registered upstream exports without regenerating matches."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pastport.application.models import ServiceError
from pastport.domain.common import SourceLocator
from pastport.domain.evidence import (
    Asset,
    Claim,
    Site,
    Source,
    SourceIndexDraft,
    SourceManifestDraft,
)
from pastport.domain.story_inputs import EnvironmentSnapshot


class _Upstream(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class _Asset(_Upstream):
    sha256: str


class _Source(_Upstream):
    project_id: str
    asset: _Asset


class _Page(_Upstream):
    page_index: int
    original_text: str
    extraction_status: str


class _Document(_Upstream):
    source: _Source
    page_count: int
    pages: tuple[_Page, ...]


@dataclass(frozen=True, slots=True)
class StoryMaterials:
    museum: EnvironmentSnapshot
    manifest: SourceManifestDraft
    index: SourceIndexDraft
    source_document_sha256: str
    environment_sha256: str
    original_pdf_sha256: str


class StoryMaterialReader:
    @staticmethod
    def bounded(path: Path, maximum: int) -> bytes:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            raise ServiceError("STORY_INPUT_INVALID", "A registered input exceeds its read profile")
        return path.read_bytes()

    def read(self, pdf: Path, source: Path, environment: Path, media: Path) -> StoryMaterials:
        if pdf.is_symlink() or not pdf.is_file() or pdf.stat().st_size > 512 * 1024**2:
            raise ServiceError("STORY_INPUT_INVALID", "Original PDF exceeds the registered profile")
        with pdf.open("rb") as stream:
            pdf_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        raw = self.bounded(source, 8 * 1024**2)
        document = _Document.model_validate_json(raw)
        raw_museum = self.bounded(environment, 8 * 1024**2)
        museum = EnvironmentSnapshot.model_validate_json(raw_museum)
        if (
            pdf_hash != document.source.asset.sha256
            or pdf_hash != museum.source_pdf_sha256
            or document.source.project_id != museum.project_id
        ):
            raise ServiceError(
                "STORY_SOURCE_MISMATCH", "PDF and upstream snapshots have different identity"
            )
        if document.page_count != len(document.pages) or [
            p.page_index for p in document.pages
        ] != list(range(document.page_count)):
            raise ServiceError("STORY_PAGE_MISMATCH", "Source page coverage is inconsistent")
        registered = Source(
            source_id="original-pdf",
            version="1",
            file_sha256=pdf_hash,
            origin="external",
            title=pdf.name,
            uri="local://story/original.pdf",
            acquisition_state="parsed",
            extraction_state="extracted",
        )
        snapshot_hash = hashlib.sha256(raw_museum).hexdigest()
        spatial_source = Source(
            source_id="environment-snapshot",
            version="1",
            file_sha256=snapshot_hash,
            origin="external",
            title="Registered object/review/3D snapshot",
            uri="local://story/environment.json",
            acquisition_state="parsed",
            extraction_state="extracted",
        )
        fragments = []
        for page in document.pages:
            for start in range(0, len(page.original_text), 8000):
                fragments.append(
                    SourceLocator(
                        source_id=registered.source_id,
                        source_version="1",
                        file_sha256=pdf_hash,
                        page_index=page.page_index,
                        printed_page=None,
                        paragraph_or_region=page.original_text[start : start + 8000],
                    )
                )
        claims, assets = [], []
        for item in museum.objects:
            if item.proposal_state == "invalid_structural_relation" or item.quote is None:
                continue
            page_number = item.quote.pdf_page
            if not 1 <= page_number <= document.page_count:
                raise ServiceError("STORY_QUOTE_INVALID", "An object quote points outside the PDF")

            def normalize(value: str) -> str:
                return re.sub(r"\s+", "", value.replace("-\n", "")).casefold()

            direct_match = normalize(item.quote.text) in normalize(
                document.pages[page_number - 1].original_text
            )
            # Upstream identity and page references remain authoritative candidates.
            # Bilingual extraction order is not a reason to redo or discard matching.
            quote_reason = (
                "Page text matches the upstream quote; independent approval is not inferred"
                if direct_match
                else (
                    "Upstream page-located quote retained; linear extracted-text match "
                    "is unconfirmed"
                )
            )
            locator = SourceLocator(
                source_id=registered.source_id,
                source_version="1",
                file_sha256=pdf_hash,
                page_index=page_number - 1,
                printed_page=None,
                paragraph_or_region=item.quote.text,
            )
            claims.append(
                Claim(
                    claim_id=f"claim-object-{item.object_number}",
                    version="1",
                    text=item.quote.text,
                    site_id=museum.environment_id,
                    structure_id=None,
                    time_scope="Use the source's stated period; no invented date",
                    content_kind="historical_fact",
                    support=(locator,),
                    refute=(),
                    judgment="qualified",
                    reason=quote_reason,
                    approved_wording=None,
                )
            )
            filename = media / f"history-{item.object_number:02}.png"
            data = self.bounded(filename, 16 * 1024**2)
            digest = hashlib.sha256(data).hexdigest()
            assets.append(
                Asset(
                    asset_id=f"object-{item.object_number}",
                    version="1",
                    original_sha256=digest,
                    derivative_sha256=digest,
                    source_locator=locator,
                    site_id=museum.environment_id,
                    structure_id=None,
                    mapping_state="provisional",
                    rights_state="restricted",
                    allowed_uses=("internal_preview",),
                    rights_basis="User-supplied local private preview inputs; not a public licence",
                    alt_text=item.name,
                )
            )
        if not claims:
            raise ServiceError(
                "STORY_NO_EVIDENCE", "No object quotes could be traced to the registered PDF"
            )
        common = dict(
            project_id=museum.project_id,
            schema_version="0.1.0",
            content_version="1",
            source_folder_id="story-inputs",
            sources=(registered, spatial_source),
        )
        manifest = SourceManifestDraft.model_validate(common | {"failures": ()})
        index = SourceIndexDraft.model_validate(
            common
            | {
                "sites": (Site(site_id=museum.environment_id, name=museum.environment_id),),
                "candidate_claims": tuple(claims),
                "candidate_assets": tuple(assets),
                "fragments": tuple(fragments),
                "unresolved_items": (
                    (
                        "Unverified mappings, original fiction and unconfirmed spatial "
                        "calibration remain explicit."
                    ),
                ),
            }
        )
        return StoryMaterials(
            museum, manifest, index, hashlib.sha256(raw).hexdigest(), snapshot_hash, pdf_hash
        )

    @staticmethod
    def spatial_context(materials: StoryMaterials) -> str:
        data = materials.museum.model_dump(mode="json")
        # Route polylines are runtime data; Story retains stations, directed connectivity
        # and outcome reasons. The complete upstream snapshot remains pinned and available.
        for world in data.get("metric_spatial", {}).get("worlds", []):
            result = (world.get("geometry") or {}).get("result")
            if result:
                for route in result["routes"]:
                    route.pop("points", None)
                for item in result["objects"]:
                    item.pop("route", None)
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
