"""Prepare registered visual inputs for the repository's environment-generation skill."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from PIL import Image

from pastport_matched_environment.adapters.assets import LocalAssetStore
from pastport_matched_environment.adapters.pdf import PopplerPDFReader
from pastport_matched_environment.adapters.projection import PanoramaProjector
from pastport_matched_environment.adapters.tour import TourImporter
from pastport_matched_environment.application.pdf_ingestion import PDFIngestionService
from pastport_matched_environment.domain.geometry import PerspectiveTransform
from pastport_matched_environment.domain.models import ProcessingLimits


@dataclass(frozen=True, slots=True)
class PreparedEnvironment:
    workspace: Path
    manifest: Path
    page_count: int
    viewpoint_count: int


def offline_input_limits(*, large_pdf: bool = False) -> ProcessingLimits:
    """Reuse input ceilings without constructing an executor or granting execution."""
    return ProcessingLimits(
        pdf_max_bytes=(512 if large_pdf else 64) * 1024 * 1024,
        max_model_calls=1,
        budget_usd=Decimal("0.0001"),
    )


class EnvironmentAgentPreparation:
    """Reuse safe input adapters without executing models or uploaded HTML scripts."""

    def __init__(self, pdftoppm: Path) -> None:
        self._reader = PopplerPDFReader(pdftoppm)

    def prepare(
        self, pdf: Path, tour_path: Path, workspace: Path, *, large_pdf: bool = False
    ) -> PreparedEnvironment:
        if workspace.exists():
            raise FileExistsError("Use a new preparation directory; existing work is never reset")
        project = "environment-" + uuid.uuid4().hex
        workspace.mkdir(parents=True)
        assets = LocalAssetStore(workspace / "assets")
        limits = offline_input_limits(large_pdf=large_pdf)
        source = tour_path / "index.html" if tour_path.is_dir() else tour_path
        tour = TourImporter(assets).import_html(project, source, limits)
        if tour.schema_version != 4:
            raise ValueError("The exact demonstrated renderer currently requires schema 4")
        document = PDFIngestionService(assets, self._reader).register_and_extract(
            project, pdf, limits
        )
        for directory in ("pages", "panoramas", "details", "evidence/media"):
            (workspace / directory).mkdir(parents=True)
        (workspace / "document.json").write_text(document.model_dump_json(indent=2))
        (workspace / "tour.json").write_text(tour.model_dump_json(indent=2))
        projector = PanoramaProjector()
        for page in document.pages:
            shutil.copy2(
                assets.resolve_path(page.rendered_page),
                workspace / "pages" / f"page-{page.page_index + 1:03d}.jpg",
            )
        for index, view in enumerate(tour.views, 1):
            panorama = assets.resolve_path(view.panorama)
            with Image.open(panorama) as original:
                with original.convert("RGB") as inspection:
                    inspection.save(
                        workspace / "panoramas" / f"view-{index:03d}.jpg", "JPEG", quality=95
                    )
            for direction, yaw in enumerate((-150.0, -90.0, -30.0, 30.0, 90.0, 150.0), 1):
                image = projector.render(
                    panorama,
                    PerspectiveTransform(
                        source_width=view.width,
                        source_height=view.height,
                        image_width=1024,
                        image_height=1024,
                        center_yaw=yaw,
                        center_pitch=0.0,
                        horizontal_fov=100.0,
                    ),
                )
                (workspace / "details" / f"view-{index:03d}-{direction}.jpg").write_bytes(image)
        evidence = workspace / "evidence"
        shutil.copy2(assets.resolve_path(document.source), evidence / "input.pdf")
        shutil.copy2(assets.resolve_path(document.source), evidence / "source.pdf")
        manifest = workspace / "preparation.json"
        manifest.write_text(
            json.dumps(
                {
                    "project_id": project,
                    "input_pdf_sha256": document.source.asset.sha256,
                    "input_vr_sha256": tour.source.asset.sha256,
                    "input_pdf": str(pdf.resolve()),
                    "input_vr": str(source.resolve()),
                    "page_count": document.page_count,
                    "viewpoint_count": len(tour.views),
                    "status": "prepared_for_agent_inspection_not_generated",
                    "semantic_judgment": "Agent must inspect actual images and evidence",
                    "old_object_hotspots": "ignored; new localization required",
                    "preparation_model_calls": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return PreparedEnvironment(workspace, manifest, document.page_count, len(tour.views))
