"""Publish an existing, owner-authorized delivery to the local player map."""

import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

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


class MapTarget(Contract):
    site_id: Identifier


class MapSite(Contract):
    id: Identifier
    name: str


class OrganizerMapPublisher:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def sites(self) -> tuple[MapSite, ...]:
        values = json.loads((runtime_root() / "frontend/player/sites.json").read_text())
        return tuple(MapSite(id=value["id"], name=value["name"]) for value in values)

    def publish(
        self, actor: Actor, job: OrganizerJob, game: Path, site_id: str = "42heilbronn"
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
        )
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(dir=self.directory, prefix=".map-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(publication.model_dump_json().encode())
            temporary.replace(self.directory / f"player-map-{site_id}.json")
        except OSError as error:
            raise ServiceError(
                "MAP_PUBLICATION_UNAVAILABLE", "无法保存玩家地图发布记录。", 503
            ) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return publication
