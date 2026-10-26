"""Source-bound, versioned panorama navigation corrections."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class NavigationPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    yaw: float = Field(ge=-180, le=180, allow_inf_nan=False)
    pitch: float = Field(ge=-90, le=90, allow_inf_nan=False)


class NavigationLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    binding: str
    scene_id: str
    hotspot_id: str
    target_id: str
    position: NavigationPoint
    arrival: NavigationPoint | None = None
    version: int = Field(default=0, ge=0)


class NavigationEdit(NavigationLink):
    operation_id: str = Field(pattern=r"^[a-zA-Z0-9-]{16,80}$")


class TourHotspot(BaseModel):
    id: str
    type: str
    targetId: str | None = None
    yaw: float
    pitch: float
    arrivalView: NavigationPoint | None = None


class TourPanorama(BaseModel):
    data: str


class TourScene(BaseModel):
    id: str
    panorama: TourPanorama
    hotspots: tuple[TourHotspot, ...]


class NavigationTour(BaseModel):
    scenes: tuple[TourScene, ...]


class NavigationStore:
    def __init__(self, root: Path) -> None:
        page = root / "vr_trial/index.html"
        if page.stat().st_size > 64 * 1024**2:
            raise ValueError("Source tour exceeds navigation profile")
        match = re.search(
            r'<script id="tour-data" type="application/json">(.*?)</script>', page.read_text(), re.S
        )
        if match is None:
            raise ValueError("Missing source tour")
        tour = NavigationTour.model_validate_json(match.group(1))
        identities = [
            (
                scene.id,
                hashlib.sha256(scene.panorama.data.encode()).hexdigest(),
                [(hot.id, hot.targetId) for hot in scene.hotspots if hot.type == "scene"],
            )
            for scene in tour.scenes
        ]
        self.binding = hashlib.sha256(json.dumps(identities).encode()).hexdigest()
        ids = {scene.id for scene in tour.scenes}
        self.links = tuple(
            NavigationLink(
                binding=self.binding,
                scene_id=scene.id,
                hotspot_id=hot.id,
                target_id=hot.targetId,
                position=NavigationPoint(yaw=hot.yaw, pitch=hot.pitch),
                arrival=hot.arrivalView,
            )
            for scene in tour.scenes
            for hot in scene.hotspots
            if hot.type == "scene" and hot.targetId is not None and hot.targetId in ids
        )
        self.database = root / "pastport_matching.sqlite3"
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS panorama_navigation(
                    binding TEXT NOT NULL,scene_id TEXT NOT NULL,hotspot_id TEXT NOT NULL,
                    payload TEXT NOT NULL,PRIMARY KEY(binding,scene_id,hotspot_id));
                CREATE TABLE IF NOT EXISTS panorama_navigation_events(
                    operation_id TEXT PRIMARY KEY, request TEXT NOT NULL,response TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """)

    def current(self) -> tuple[NavigationLink, ...]:
        with closing(sqlite3.connect(self.database)) as db:
            rows = db.execute(
                "SELECT scene_id,hotspot_id,payload FROM panorama_navigation WHERE binding=?",
                (self.binding,),
            ).fetchall()
        saved = {(row[0], row[1]): NavigationLink.model_validate_json(row[2]) for row in rows}
        return tuple(saved.get((link.scene_id, link.hotspot_id), link) for link in self.links)

    def save(self, edit: NavigationEdit) -> NavigationLink | None:
        baseline = next(
            (
                link
                for link in self.links
                if link.scene_id == edit.scene_id
                and link.hotspot_id == edit.hotspot_id
                and link.target_id == edit.target_id
            ),
            None,
        )
        if baseline is None or edit.binding != self.binding:
            raise ValueError("Navigation source or destination changed")
        request = edit.model_dump_json()
        with closing(sqlite3.connect(self.database, timeout=5)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            replay = db.execute(
                "SELECT request,response FROM panorama_navigation_events WHERE operation_id=?",
                (edit.operation_id,),
            ).fetchone()
            if replay:
                if replay[0] != request:
                    raise ValueError("Operation reused with different navigation edit")
                return NavigationLink.model_validate_json(replay[1])
            row = db.execute(
                "SELECT payload FROM panorama_navigation "
                "WHERE binding=? AND scene_id=? AND hotspot_id=?",
                (edit.binding, edit.scene_id, edit.hotspot_id),
            ).fetchone()
            current = NavigationLink.model_validate_json(row[0]) if row else baseline
            if current.version != edit.version:
                return None
            saved = NavigationLink.model_validate(
                edit.model_dump(exclude={"operation_id"}) | {"version": edit.version + 1}
            )
            payload = saved.model_dump_json()
            db.execute(
                "INSERT INTO panorama_navigation VALUES(?,?,?,?) "
                "ON CONFLICT(binding,scene_id,hotspot_id) "
                "DO UPDATE SET payload=excluded.payload",
                (edit.binding, edit.scene_id, edit.hotspot_id, payload),
            )
            db.execute(
                "INSERT INTO panorama_navigation_events(operation_id,request,response) "
                "VALUES(?,?,?)",
                (edit.operation_id, request, payload),
            )
            return saved
