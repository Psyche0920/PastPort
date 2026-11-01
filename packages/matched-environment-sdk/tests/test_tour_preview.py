"""Independent tours retain saved navigation and reject unregistered destinations."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from pastport_matched_environment.api.tour_preview import TourPreviewApplication, TourPreviewView
from pastport_matched_environment.application.navigation import NavigationLink, NavigationPoint
from pastport_matched_environment.application.reference_preview import ReferencePreviewPool
from pastport_matched_environment.application.tour_navigation import (
    Scene3DTourNavigator,
    TourDestination,
)


class OwnedPreviews(ReferencePreviewPool):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    async def ensure(self, root: Path) -> int:
        return 18990

    async def close(self) -> None:
        self.closed = True


class TourPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name)
        self.links = (
            NavigationLink(
                binding="source-binding",
                scene_id="one",
                hotspot_id="door",
                target_id="two",
                position=NavigationPoint(yaw=25, pitch=-4),
                arrival=NavigationPoint(yaw=77, pitch=3),
            ),
            NavigationLink(
                binding="source-binding",
                scene_id="two",
                hotspot_id="back",
                target_id="one",
                position=NavigationPoint(yaw=-15, pitch=0),
                arrival=None,
            ),
        )

    def test_bidirectional_destinations_preserve_arrival_and_position(self) -> None:
        nav = Scene3DTourNavigator(
            self.source,
            (
                TourDestination("one", "http://127.0.0.1:18833/views/one/"),
                TourDestination("two", "http://127.0.0.1:18833/views/two/"),
            ),
        )
        with patch(
            "pastport_matched_environment.application.tour_navigation.NavigationStore"
        ) as store:
            store.return_value.current.return_value = self.links
            first, back = nav.current("one"), nav.current("two")
        self.assertEqual(first.transitions[0].yaw, 25)
        self.assertIn("arrival_yaw=77.0", first.transitions[0].target_url)
        self.assertEqual(back.transitions[0].target_scene_id, "one")
        with self.assertRaises(ValueError):
            nav.current("foreign")

    def test_single_registered_view_does_not_invent_a_destination(self) -> None:
        nav = Scene3DTourNavigator(self.source, (TourDestination("one", "http://127.0.0.1:1/"),))
        with patch(
            "pastport_matched_environment.application.tour_navigation.NavigationStore"
        ) as store:
            store.return_value.current.return_value = self.links
            self.assertEqual(nav.current("one").transitions, ())
        with self.assertRaises(ValueError):
            Scene3DTourNavigator(
                self.source, (TourDestination("one", "a"), TourDestination("one", "b"))
            )

    def test_preview_origin_binding_redirect_and_cleanup(self) -> None:
        views = []
        for scene in ["one", "two"]:
            root = self.source / scene
            (root / "scene3d").mkdir(parents=True)
            (root / "scene3d/attachment.json").write_text(json.dumps({"source_scene_id": scene}))
            views.append(TourPreviewView(scene, root))
        database = self.source / "authority.sqlite3"
        database.touch()
        pool = OwnedPreviews()
        with patch(
            "pastport_matched_environment.api.tour_preview.SharedContentAuthority"
        ) as authority:
            authority.return_value.database = database
            app = TourPreviewApplication(self.source, tuple(views), "http://127.0.0.1:18833", pool)
        key = hashlib.sha256(b"one").hexdigest()[:32]
        with patch(
            "pastport_matched_environment.application.tour_navigation.NavigationStore"
        ) as store:
            store.return_value.current.return_value = self.links
            with TestClient(app.app) as client:
                response = client.get(
                    f"/scene3d-results/{key}/?arrival_yaw=77&render=original",
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 307)
                self.assertIn("render=original", response.headers["location"])
                self.assertIn("arrival_yaw=77.0", response.headers["location"])
                sidecar = json.loads((views[0].root / "scene3d/portal-navigation.json").read_text())
                self.assertEqual(
                    sidecar["endpoint"], f"http://127.0.0.1:18833/api/scene3d-navigation/{key}"
                )
                self.assertEqual(
                    client.get(
                        f"/api/scene3d-navigation/{key}", headers={"origin": "https://foreign.test"}
                    ).status_code,
                    403,
                )
                allowed = client.get(
                    f"/api/scene3d-navigation/{key}", headers={"origin": "http://127.0.0.1:18990"}
                )
                self.assertEqual(allowed.status_code, 200)
                self.assertEqual(allowed.json()["transitions"][0]["target_scene_id"], "two")
                self.assertEqual(client.get("/scene3d-results/unknown/").status_code, 404)
                self.assertEqual(
                    client.get(f"/scene3d-results/{key}/?arrival_yaw=nan").status_code, 422
                )
        self.assertTrue(pool.closed)
        with self.assertRaises(ValueError):
            TourPreviewApplication(self.source, tuple(views), "https://foreign.test")
