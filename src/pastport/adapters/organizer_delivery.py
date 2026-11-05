"""Import a player snapshot without running anything from its archive."""

import hashlib
import json
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from pastport.application.models import ServiceError
from pastport.domain.common import Contract
from pastport.domain.organizer import OrganizerJob
from pastport.ports.organizer import OrganizerRepository

MAX_BYTES = 2 * 1024**3


def delivery_name(filename: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}\.tar\.gz", filename):
        raise ServiceError("DELIVERY_NAME_INVALID", "请选择有效的 .tar.gz 交付包。", 422)
    return filename.removesuffix(".tar.gz")


def import_delivery(
    store: OrganizerRepository, owner_id: str, name: str, archive: Path
) -> OrganizerJob:
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    key = hashlib.sha256(f"{owner_id}\0{name}\0{digest}".encode()).hexdigest()[:32]
    for job in store.list("job", OrganizerJob):
        if job.job_id == key:
            return job
    jobs = store.directory / "jobs"
    jobs.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix=".delivery-", dir=jobs) as staging:
        root = Path(staging)
        try:
            _extract(archive, root)
            game = root / name
            validate_player_game(game)
        except (OSError, ValueError, tarfile.TarError, EOFError, KeyError, TypeError) as error:
            raise ServiceError(
                "DELIVERY_INVALID", "交付包损坏或缺少有效的试玩文件。", 422
            ) from error
        destination = jobs / key
        job = OrganizerJob(
            job_id=key, owner_id=owner_id, project_id=name, source_id=key,
            mode="reuse", status="completed", message="已导入独立试玩交付包。",
            input_sha256=digest, payload_sha256=digest, request_key=uuid4().hex,
            result_ready=True, new_model_calls=0,
        )
        destination.mkdir()
        try:
            game.rename(destination / "game-3d")
            store.save("job", key, job)
        except BaseException:
            shutil.rmtree(destination)
            raise
        return job


def _extract(archive: Path, root: Path) -> None:
    total = 0
    with tarfile.open(archive, "r|gz") as package:
        for count, member in enumerate(package, 1):
            path = PurePosixPath(member.name)
            total += member.size
            if (
                count > 10_000 or total > MAX_BYTES or member.size < 0
                or path.is_absolute() or ".." in path.parts or not path.parts
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("Unsafe archive member")
            if path.name.startswith("._") or path.name == ".DS_Store":
                continue
            package.extract(member, root, filter="data")


class StaticPlayerManifest(Contract):
    format: Literal["pastport-static-v1"]
    entrypoint: str


def validate_player_game(game: Path) -> None:
    """Validate the declared player transport without running imported code."""
    manifest = game / "pastport-player.json"
    if manifest.is_file():
        if manifest.stat().st_size > 16384 or not (game / "index.html").is_file():
            raise ValueError("Invalid static player manifest")
        specification = StaticPlayerManifest.model_validate_json(manifest.read_bytes())
        entry = PurePosixPath(specification.entrypoint)
        if (
            not re.fullmatch(r"[a-zA-Z0-9_./-]+\.html", specification.entrypoint)
            or entry.is_absolute() or ".." in entry.parts
            or not (game / entry).resolve().is_relative_to(game.resolve())
            or not (game / entry).is_file()
        ):
            raise ValueError("Invalid static player entrypoint")
        return
    if not all((game / name).is_file() for name in ("index.html", "scene3d-runtime.js")):
        raise ValueError("Missing player entry")
    config = game / "data/scene3d-input.json"
    if config.stat().st_size > 32 * 1024**2:
        raise ValueError("Scene configuration too large")
    worlds = json.loads(config.read_bytes())["worlds"]
    if not isinstance(worlds, list) or not 1 <= len(worlds) <= 2:
        raise ValueError("Invalid world count")
    for world in worlds:
        path = (game / world["root"]).resolve()
        if not path.is_relative_to(game.resolve()) or not isinstance(world["snapshot"], dict):
            raise ValueError("Invalid world")
        if not all((path / "scene3d" / asset).is_file() for asset in ("index.html", "viewer.js")):
            raise ValueError("Missing world files")
