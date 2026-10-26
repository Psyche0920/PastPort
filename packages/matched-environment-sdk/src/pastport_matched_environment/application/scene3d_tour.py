"""Export separate source-ordered worlds and their saved navigation as one package."""

from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from pydantic import Field

from pastport_matched_environment.application.reference_environment import digest, record, string
from pastport_matched_environment.application.scene3d_export import export_scene
from pastport_matched_environment.domain.models import DomainModel
from pastport_matched_environment.domain.scene3d import Point3D, Scene3DArrow


@dataclass(frozen=True, slots=True)
class TourSource:
    number: int
    scene_id: str
    root: Path


class TourArrow(DomainModel):
    hotspot_id: str
    target_scene_id: str
    point: Point3D | None
    version: int
    arrival_yaw: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    arrival_pitch: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)


class TourView(DomainModel):
    number: int
    source_scene_id: str
    package: str
    sha256: str
    arrows: tuple[TourArrow, ...]


class TourManifest(DomainModel):
    schema_version: str = "pastport.scene3d-tour/1.0"
    mode: str = "independent_worlds_with_arrow_plane_transitions"
    entry_scene_id: str
    views: tuple[TourView, ...]


def export_tour(sources: tuple[TourSource, ...], archive: Path) -> None:
    """Snapshot each world's edits, retaining source IDs without live localhost URLs."""
    scene_ids = {source.scene_id for source in sources}
    if not 1 <= len(sources) <= 50 or len(scene_ids) != len(sources):
        raise ValueError("Invalid or duplicate tour viewpoints")
    views: list[TourView] = []
    with TemporaryDirectory(prefix="pastport-tour-assets-") as temporary:
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as bundle:
            total = 0
            for source in sources:
                name = f"views/point-{source.number}.zip"
                package = Path(temporary) / f"point-{source.number}.zip"
                export_scene(source.root.resolve(), package)
                total += package.stat().st_size
                if total > 4 * 1024**3:
                    raise ValueError("Tour exceeds 4 GiB")
                # Use the exported database snapshot, not a second live database read.
                with zipfile.ZipFile(package) as scene_bundle:
                    binding = string(
                        record(json.loads(scene_bundle.read("manifest.json")))["scene_binding"]
                    )
                    snapshot = Path(temporary) / "review.sqlite3"
                    with scene_bundle.open("review.sqlite3") as data, snapshot.open("wb") as out:
                        shutil.copyfileobj(data, out, 65536)
                with closing(sqlite3.connect(snapshot)) as db:
                    exists = db.execute(
                        "SELECT 1 FROM sqlite_master WHERE name='scene3d_arrows'"
                    ).fetchone()
                    rows = (
                        db.execute(
                            "SELECT payload FROM scene3d_arrows WHERE binding=?", (binding,)
                        ).fetchall()
                        if exists
                        else []
                    )
                arrows: list[TourArrow] = []
                for row in rows:
                    arrow = Scene3DArrow.model_validate_json(row[0])
                    if arrow.target_scene_id not in scene_ids:
                        raise ValueError("Navigation target is outside this tour")
                    query = parse_qs(urlsplit(arrow.target_url).query)
                    arrows.append(
                        TourArrow(
                            hotspot_id=arrow.hotspot_id,
                            target_scene_id=arrow.target_scene_id,
                            point=arrow.point,
                            version=arrow.version,
                            arrival_yaw=float(query["arrival_yaw"][0])
                            if "arrival_yaw" in query
                            else None,
                            arrival_pitch=float(query["arrival_pitch"][0])
                            if "arrival_pitch" in query
                            else None,
                        )
                    )
                views.append(
                    TourView(
                        number=source.number,
                        source_scene_id=source.scene_id,
                        package=name,
                        sha256=digest(package),
                        arrows=tuple(arrows),
                    )
                )
                bundle.write(package, name)
                package.unlink()
            manifest = TourManifest(entry_scene_id=sources[0].scene_id, views=tuple(views))
            bundle.writestr("tour.json", manifest.model_dump_json(indent=2))
            bundle.writestr(
                "README.txt",
                (
                    "PastPort multi-view 3D development package\n"
                    "Viewpoint numbers follow the original VR source order.\n"
                    "Extract views/point-N.zip for assets, evidence and numbered data.\n"
                    "tour.json retains saved arrow positions and arrival angles between worlds.\n"
                    "Cross the vertical plane through an arrow, normal to origin-to-arrow in X/Z.\n"
                    "This is not fused geometry or a standalone executable viewer.\n"
                    "Use the Studio View full 3D tour action to play the current tour.\n"
                ),
            )
