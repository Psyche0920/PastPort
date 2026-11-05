"""Static deliveries use the same owned history and publication contracts as 3D."""

import asyncio
import json
import tarfile
from pathlib import Path

import httpx
import pytest

from pastport.adapters.organizer_delivery import import_delivery, validate_player_game
from pastport.adapters.organizer_map import OrganizerMapPublisher
from pastport.adapters.organizer_previews import OrganizerPreviewPool
from pastport.adapters.organizer_store import OrganizerStore
from pastport.application.models import Actor, ServiceError


def package(root: Path) -> Path:
    game = root / "trial"
    (game / "prototype").mkdir(parents=True)
    (game / "index.html").write_text("Static transport fixture")
    (game / "prototype/adventure.html").write_text("<html>Static adventure fixture</html>")
    (game / "pastport-player.json").write_text(json.dumps({
        "format": "pastport-static-v1", "entrypoint": "prototype/adventure.html",
    }))
    return game


def test_static_import_is_deduplicated_and_can_publish_to_a_selected_site(tmp_path: Path) -> None:
    game = package(tmp_path)
    archive = tmp_path / "trial.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(game, arcname="trial")
    store = OrganizerStore(tmp_path / "organizer")
    job = import_delivery(store, "owner", "trial", archive)
    assert job.status == "completed" and job.result_ready and job.new_model_calls == 0
    assert import_delivery(store, "owner", "trial", archive).job_id == job.job_id
    mounted = store.directory / "jobs" / job.job_id / "game-3d"
    publisher = OrganizerMapPublisher(store.directory)
    actor = Actor(actor_id="owner", roles=("operator",), project_ids=None)
    publication = publisher.publish(actor, job, mounted, "muradiye")
    assert publication.site_id == "muradiye"
    assert (store.directory / "player-map-muradiye.json").is_file()
    with pytest.raises(ServiceError) as error:
        other = Actor(actor_id="other", roles=("operator",), project_ids=None)
        publisher.publish(other, job, mounted, "muradiye")
    assert error.value.code == "MAP_PUBLICATION_FORBIDDEN"


@pytest.mark.parametrize("entry", ["../outside.html", "/outside.html", "prototype/missing.html"])
def test_static_entry_cannot_escape_or_name_a_missing_file(tmp_path: Path, entry: str) -> None:
    game = package(tmp_path)
    (tmp_path / "outside.html").write_text("outside")
    (game / "pastport-player.json").write_text(
        json.dumps({"format": "pastport-static-v1", "entrypoint": entry})
    )
    with pytest.raises(ValueError):
        validate_player_game(game)


def test_static_preview_uses_login_cookie_and_preserves_run_query(tmp_path: Path) -> None:
    game = package(tmp_path)

    async def check() -> None:
        pool = OrganizerPreviewPool()
        try:
            url = await pool.ensure(game)
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url + "&passportRun=protocol-fixture")
                assert response.status_code == 200
                assert "Static adventure fixture" in response.text
                assert response.url.path == "/prototype/adventure.html"
                assert response.url.params["passportRun"] == "protocol-fixture"
                assert "preview_token" not in response.url.params
                origin = str(response.url.copy_with(path="/", query=b""))
                async with httpx.AsyncClient() as anonymous:
                    assert (await anonymous.get(origin)).status_code == 401
        finally:
            await pool.close()

    asyncio.run(check())
