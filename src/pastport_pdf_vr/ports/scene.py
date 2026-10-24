"""Scene-source boundary; importers normalize supported panoramas before recognition.

A future 3D adapter must supply reference views plus a reversible pixel-to-surface
transform and its own viewer/anchor representation. It must not convert XYZ into
panorama yaw/pitch or pretend to implement this panorama-only result contract.
"""

from pathlib import Path
from typing import Protocol

from pastport_pdf_vr.domain.models import ProcessingLimits, ProjectId
from pastport_pdf_vr.domain.tour import ImportedTour


class PanoramaSourceReader(Protocol):
    def import_html(
        self, project_id: ProjectId, path: Path, limits: ProcessingLimits
    ) -> ImportedTour: ...
