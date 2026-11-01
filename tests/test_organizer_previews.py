"""Owned 3D preview transport: inherited listener, login gate and deterministic close."""

import asyncio
import json
import shutil
from pathlib import Path

import httpx
import pytest

from pastport.adapters.organizer_previews import OrganizerPreviewPool


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for player preview")
def test_preview_is_authenticated_reused_and_closed(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data/scene3d-input.json").write_text(json.dumps({"worlds": []}))
    (tmp_path / "index.html").write_text("<html><body>Transport fixture only</body></html>")

    async def check() -> None:
        pool = OrganizerPreviewPool()
        try:
            url = await pool.ensure(tmp_path)
            assert await pool.ensure(tmp_path) == url
            origin = str(httpx.URL(url).copy_with(path="/", query=b""))
            async with httpx.AsyncClient(follow_redirects=True) as client:
                assert (await client.get(origin)).status_code == 401
                response = await client.get(url)
                assert response.status_code == 200
                assert "Transport fixture only" in response.text
                assert "preview_token" not in str(response.url)
                assert (await client.get(origin, headers={"Host": "untrusted.example"})).status_code == 403
        finally:
            await pool.close()
        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.ConnectError):
                await client.get(origin)

    asyncio.run(check())
