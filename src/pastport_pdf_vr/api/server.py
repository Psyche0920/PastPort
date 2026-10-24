"""Project-scoped localhost application; never expose arbitrary source/storage paths."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from pastport_pdf_vr.adapters.editorial import (
    EditConflict,
    EditorialError,
    SQLiteEditorialRepository,
)
from pastport_pdf_vr.domain.build import BuildSummary
from pastport_pdf_vr.domain.editorial import EditResult, PositionEdit, PreviewSnapshot, TextEdit
from pastport_pdf_vr.domain.tour import ImportedTour
from pastport_pdf_vr.ports.assets import AssetStore


class LocalReviewApplication:
    def __init__(
        self,
        project_id: str,
        tour: ImportedTour,
        repository: SQLiteEditorialRepository,
        assets: AssetStore,
        build_summary: BuildSummary | None = None,
    ) -> None:
        if tour.source.project_id != project_id:
            raise ValueError("Tour belongs to another project")
        self._project, self._tour, self._repository, self._assets = (
            project_id,
            tour,
            repository,
            assets,
        )
        self._summary = build_summary
        self.app = self._build()

    def _build(self) -> FastAPI:
        app = FastAPI(
            title="PastPort PDF-to-VR Review", docs_url=None, redoc_url=None, openapi_url=None
        )
        web = Path(str(files("pastport_pdf_vr").joinpath("web")))
        app.mount("/static", StaticFiles(directory=web), name="static")

        @app.middleware("http")
        async def local_boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
            host = request.url.hostname
            if host not in ("127.0.0.1", "localhost", "testserver"):
                return JSONResponse({"detail": "Local preview only"}, status_code=403)
            if request.method not in ("GET", "HEAD"):
                origin = request.headers.get("origin")
                if origin is not None and origin != f"{request.url.scheme}://{request.url.netloc}":
                    return JSONResponse(
                        {"detail": "Cross-origin edits are not allowed"}, status_code=403
                    )
                if request.headers.get("x-pastport-edit") != "1":
                    return JSONResponse({"detail": "Missing edit request marker"}, status_code=403)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'none'"
            )
            return response

        @app.exception_handler(EditConflict)
        async def conflict(request: Request, error: EditConflict) -> JSONResponse:
            return JSONResponse({"detail": str(error)}, status_code=409)

        @app.exception_handler(EditorialError)
        async def unavailable(request: Request, error: EditorialError) -> JSONResponse:
            return JSONResponse(
                {"detail": "Project editorial storage is unavailable"}, status_code=503
            )

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(web / "review.html")

        @app.get("/vr/")
        def vr() -> FileResponse:
            return FileResponse(web / "vr.html")

        @app.get("/api/build-summary")
        def build_summary() -> BuildSummary | None:
            return self._summary

        @app.get("/api/tour")
        def tour() -> ImportedTour:
            return self._tour

        @app.get("/api/snapshot")
        def snapshot() -> PreviewSnapshot:
            return self._repository.snapshot(self._project)

        @app.post("/api/text")
        def text_edit(edit: TextEdit) -> EditResult:
            return self._repository.save_text(self._project, edit)

        @app.post("/api/position")
        def position_edit(edit: PositionEdit) -> EditResult:
            return self._repository.save_position(self._project, edit)

        @app.get("/media/{sha256}")
        def media(sha256: str) -> FileResponse:
            allowed = {view.panorama.asset.sha256: view.panorama for view in self._tour.views}
            for row in self._repository.snapshot(self._project).objects:
                evidence = row.object.replay_evidence
                if evidence:
                    for reference in (evidence.source_image, evidence.page_image):
                        if reference:
                            allowed[reference.asset.sha256] = reference
            reference = allowed.get(sha256)
            if reference is None:
                raise HTTPException(status_code=404, detail="Media is not part of this tour")
            path = self._assets.resolve_path(reference)
            with path.open("rb") as source:
                signature = source.read(12)
            media_type = "image/jpeg"
            if signature.startswith(b"\x89PNG\r\n\x1a\n"):
                media_type = "image/png"
            elif signature.startswith(b"RIFF") and signature[8:12] == b"WEBP":
                media_type = "image/webp"
            return FileResponse(path, media_type=media_type)

        return app
