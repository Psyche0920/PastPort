"""Reuse source navigation across registered independent 3D deliveries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from pastport_matched_environment.application.navigation import NavigationStore
from pastport_matched_environment.domain.scene3d import Scene3DNavigation, Scene3DTransition


@dataclass(frozen=True, slots=True)
class TourDestination:
    scene_id: str
    viewer_url: str


class Scene3DTourNavigator:
    """Resolve saved VR links against explicitly registered destination viewers."""

    def __init__(self, source: Path, destinations: tuple[TourDestination, ...]) -> None:
        ids = tuple(item.scene_id for item in destinations)
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Register distinct tour viewpoints")
        self.source = source
        self.destinations = {item.scene_id: item.viewer_url for item in destinations}

    def current(self, scene_id: str) -> Scene3DNavigation:
        if scene_id not in self.destinations:
            raise ValueError("Viewpoint is not registered in this tour")
        transitions: list[Scene3DTransition] = []
        for link in NavigationStore(self.source).current():
            if link.scene_id != scene_id or link.target_id not in self.destinations:
                continue
            url = self.destinations[link.target_id]
            if link.arrival:
                query = urlencode(
                    {"arrival_yaw": link.arrival.yaw, "arrival_pitch": link.arrival.pitch}
                )
                url += ("&" if "?" in url else "?") + query
            transitions.append(
                Scene3DTransition(
                    hotspot_id=link.hotspot_id,
                    target_scene_id=link.target_id,
                    yaw=link.position.yaw,
                    pitch=link.position.pitch,
                    target_url=url,
                )
            )
        return Scene3DNavigation(source_scene_id=scene_id, transitions=tuple(transitions))
