"""Publish an existing, owner-authorized delivery to the local player map."""

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import Field, TypeAdapter

from pastport.adapters.organizer_delivery import validate_player_game
from pastport.adapters.runtime_resources import runtime_root
from pastport.application.models import Actor, ServiceError
from pastport.domain.common import Contract, Identifier, Sha256
from pastport.domain.organizer import OrganizerJob


class MapPublication(Contract):
    site_id: Identifier
    job_id: Identifier
    version: Sha256
    game_directory: Path
    published_at: str | None = None
    actor_id: Identifier | None = None


class MapTarget(Contract):
    site_id: Identifier
    # Compare-and-set: the version the publisher last saw ("none" = unpublished).
    expected_version: Sha256 | Literal["none"] | None = None


class MapUnpublishTarget(Contract):
    site_id: Identifier
    expected_version: Sha256


class MapSiteState(Contract):
    site_id: Identifier
    name: str
    current: MapPublication | None
    history: tuple[MapPublication, ...] = Field(default=())


HISTORY = TypeAdapter(tuple[MapPublication, ...])
HISTORY_LIMIT = 50


class MapSite(Contract):
    id: Identifier
    name: str


class OrganizerMapPublisher:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()
        self.lock = threading.Lock()

    def current(self, site_id: str) -> MapPublication | None:
        path = self.directory / f"player-map-{site_id}.json"
        if not path.is_file():
            return None
        return MapPublication.model_validate_json(path.read_bytes())

    def history(self, site_id: str) -> tuple[MapPublication, ...]:
        path = self.directory / f"player-map-{site_id}.history.json"
        if not path.is_file():
            return ()
        return HISTORY.validate_json(path.read_bytes())

    def states(self) -> tuple[MapSiteState, ...]:
        return tuple(
            MapSiteState(
                site_id=site.id,
                name=site.name,
                current=self.current(site.id),
                history=self.history(site.id),
            )
            for site in self.sites()
        )

    def _write(self, name: str, content: bytes) -> None:
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(dir=self.directory, prefix=".map-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            temporary.replace(self.directory / name)
        except OSError as error:
            raise ServiceError(
                "MAP_PUBLICATION_UNAVAILABLE", "无法保存玩家地图发布记录。", 503
            ) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def sites(self) -> tuple[MapSite, ...]:
        values = json.loads((runtime_root() / "frontend/player/sites.json").read_text())
        return tuple(MapSite(id=value["id"], name=value["name"]) for value in values)

    def publish(
        self,
        actor: Actor,
        job: OrganizerJob,
        game: Path,
        site_id: str = "42heilbronn",
        expected_version: str | None = None,
    ) -> MapPublication:
        if (
            not {"operator", "publisher"}.intersection(actor.roles)
            or job.owner_id != actor.actor_id
            or (actor.project_ids is not None and job.project_id not in actor.project_ids)
        ):
            raise ServiceError("MAP_PUBLICATION_FORBIDDEN", "没有发布此交付包的权限。", 403)
        if site_id not in {site.id for site in self.sites()}:
            raise ServiceError("MAP_SITE_UNKNOWN", "请选择地图中已有的站点。", 422)
        if job.status != "completed" or not job.result_ready:
            raise ServiceError(
                "MAP_DELIVERY_UNAVAILABLE", "需要可打开独立玩家预览的已完成交付包。", 409
            )
        root = game.resolve()
        job_root = (self.directory / "jobs" / job.job_id).resolve()
        if (
            not job_root.is_relative_to(self.directory / "jobs")
            or not root.is_relative_to(job_root)
            or not (root / "index.html").is_file()
        ):
            raise ServiceError("MAP_DELIVERY_UNAVAILABLE", "交付包的试玩文件不可用。", 409)
        try:
            validate_player_game(root)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ServiceError(
                "MAP_DELIVERY_UNAVAILABLE", "交付包的试玩文件不可用。", 409
            ) from error
        digest = hashlib.sha256()
        for file in sorted(root.rglob("*")):
            if file.is_file():
                resolved = file.resolve()
                if not resolved.is_relative_to(root):
                    raise ServiceError("MAP_DELIVERY_UNAVAILABLE", "游戏文件超出交付目录。", 409)
                digest.update(file.relative_to(root).as_posix().encode())
                digest.update(b"\0")
                with file.open("rb") as stream:
                    digest.update(hashlib.file_digest(stream, "sha256").digest())
        publication = MapPublication(
            site_id=site_id,
            job_id=job.job_id,
            version=digest.hexdigest(),
            game_directory=root.relative_to(self.directory),
            published_at=datetime.now(UTC).isoformat(timespec="seconds"),
            actor_id=actor.actor_id,
        )
        with self.lock:
            current = self.current(site_id)
            seen = current.version if current else "none"
            if expected_version is not None and expected_version != seen:
                raise ServiceError(
                    "MAP_PUBLICATION_CONFLICT",
                    "此站点刚被他人发布了其他版本；请查看最新发布状态后再决定。",
                    409,
                )
            # History first: the pointer switch is the single atomic step players observe.
            history = (*self.history(site_id), publication)[-HISTORY_LIMIT:]
            self._write(f"player-map-{site_id}.history.json", HISTORY.dump_json(history))
            self._write(f"player-map-{site_id}.json", publication.model_dump_json().encode())
        return publication

    def unpublish(
        self, actor: Actor, job: OrganizerJob, site_id: str, expected_version: str
    ) -> MapSiteState:
        """Remove only the current pointer; retain the package and publication history."""
        if (
            not {"operator", "publisher"}.intersection(actor.roles)
            or job.owner_id != actor.actor_id
            or (actor.project_ids is not None and job.project_id not in actor.project_ids)
        ):
            raise ServiceError("MAP_PUBLICATION_FORBIDDEN", "没有解除此发布的权限。", 403)
        site = next((value for value in self.sites() if value.id == site_id), None)
        if site is None:
            raise ServiceError("MAP_SITE_UNKNOWN", "请选择地图中已有的站点。", 422)
        with self.lock:
            current = self.current(site_id)
            if current is not None:
                if current.job_id != job.job_id or current.version != expected_version:
                    raise ServiceError(
                        "MAP_PUBLICATION_CONFLICT",
                        "此站点的发布已改变，请刷新后再解除。",
                        409,
                    )
                history = self.history(site_id)
                if current not in history:
                    history = (*history, current)[-HISTORY_LIMIT:]
                    self._write(f"player-map-{site_id}.history.json", HISTORY.dump_json(history))
                try:
                    (self.directory / f"player-map-{site_id}.json").unlink(missing_ok=True)
                except OSError as error:
                    raise ServiceError(
                        "MAP_PUBLICATION_UNAVAILABLE", "无法解除玩家地图发布。", 503
                    ) from error
            return MapSiteState(
                site_id=site.id, name=site.name, current=None, history=self.history(site_id)
            )
