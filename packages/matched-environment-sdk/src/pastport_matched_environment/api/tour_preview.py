"""Compose existing 3D viewers without requiring Studio job records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from pastport_matched_environment.application.reference_environment import read_json, record, string
from pastport_matched_environment.application.reference_preview import ReferencePreviewPool
from pastport_matched_environment.application.shared_content import SharedContentAuthority
from pastport_matched_environment.application.storage import atomic_write
from pastport_matched_environment.application.tour_navigation import (
    Scene3DTourNavigator,
    TourDestination,
)


@dataclass(frozen=True, slots=True)
class TourPreviewView:
    scene_id: str
    root: Path

    @classmethod
    def from_result(cls, root: Path) -> TourPreviewView:
        attachment = record(read_json(root / "scene3d/attachment.json"))
        return cls(string(attachment["source_scene_id"]), root)


class TourPreviewApplication:
    """Own local viewer processes and reuse the same navigation service as Studio."""

    def __init__(
        self,
        source: Path,
        views: tuple[TourPreviewView, ...],
        base_url: str,
        previews: ReferencePreviewPool | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use a fixed loopback tour origin")
        self.origin = base_url.rstrip("/")
        self.views = {item.scene_id: item.root.resolve(strict=True) for item in views}
        if not views or len(self.views) != len(views):
            raise ValueError("Register distinct viewpoints")
        authority = SharedContentAuthority(source).database.resolve(strict=True)
        for view in views:
            if (
                view.root.is_symlink()
                or not view.scene_id
                or any(
                    char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                    for char in view.scene_id
                )
            ):
                raise ValueError("Invalid viewpoint registration")
            root = self.views[view.scene_id]
            attachment = record(read_json(root / "scene3d/attachment.json"))
            if string(attachment["source_scene_id"]) != view.scene_id:
                raise ValueError("Viewpoint identity does not match its attachment")
            if SharedContentAuthority(root).database.resolve(strict=True) != authority:
                raise ValueError("Tour views must share the registered content authority")
        self.keys = {hashlib.sha256(scene.encode()).hexdigest()[:32]: scene for scene in self.views}
        self.previews = previews or ReferencePreviewPool()
        self.navigator = Scene3DTourNavigator(
            source,
            tuple(
                TourDestination(scene, f"{self.origin}/scene3d-results/{key}/")
                for key, scene in self.keys.items()
            ),
        )

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            try:
                yield
            finally:
                await self.previews.close()

        self.app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

        @self.app.get("/")
        async def home() -> RedirectResponse:
            return RedirectResponse(f"/scene3d-results/{next(iter(self.keys))}/")

        @self.app.get("/api/scene3d-navigation/{run_id}")
        async def navigation(run_id: str, request: Request) -> JSONResponse:
            scene_id = self._scene(run_id)
            root = self._root(scene_id)
            port = await self.previews.ensure(root)
            origin = request.headers.get("origin", "")
            if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                raise HTTPException(403, "Owned result preview required")
            return JSONResponse(
                self.navigator.current(scene_id).model_dump(mode="json"),
                headers={
                    "Access-Control-Allow-Origin": origin or self.origin,
                    "Vary": "Origin",
                    "Cache-Control": "no-store",
                },
            )

        @self.app.get("/scene3d-results/{run_id}/")
        async def viewer(
            run_id: str,
            render: str = "stylized",
            arrival_yaw: Annotated[
                float | None, Query(ge=-180, le=180, allow_inf_nan=False)
            ] = None,
            arrival_pitch: Annotated[
                float | None, Query(ge=-90, le=90, allow_inf_nan=False)
            ] = None,
        ) -> RedirectResponse:
            scene_id = self._scene(run_id)
            root = self._root(scene_id)
            if render not in ("original", "stylized"):
                raise HTTPException(422, "Unknown appearance mode")
            navigation = self.navigator.current(scene_id)
            atomic_write(root / "scene3d/arrow-seed.json", navigation.model_dump_json())
            atomic_write(
                root / "scene3d/portal-navigation.json",
                json.dumps({"endpoint": f"{self.origin}/api/scene3d-navigation/{run_id}"}),
            )
            port = await self.previews.ensure(root)
            query = {"render": render}
            for key, value in (("arrival_yaw", arrival_yaw), ("arrival_pitch", arrival_pitch)):
                if value is not None:
                    query[key] = str(value)
            return RedirectResponse(
                f"http://127.0.0.1:{port}/scene3d/index.html?{urlencode(query)}"
            )

    def _scene(self, run_id: str) -> str:
        scene = self.keys.get(run_id)
        if scene is None:
            raise HTTPException(404, "Viewpoint is not registered")
        return scene

    def _root(self, scene_id: str) -> Path:
        root = self.views.get(scene_id)
        if root is None:
            raise HTTPException(404, "Viewpoint is not registered")
        return root
