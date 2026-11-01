"""Bounded data-only archive admission; uploaded programs are never executed."""

import hashlib
import subprocess
import sys
import shutil
import sqlite3
import stat
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

from pastport.application.models import ServiceError


class BoundedNativeArchive:
    ALLOWED = frozenset(
        {
            ".json",
            ".pdf",
            ".sqlite3",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".spz",
            ".glb",
            ".html",
            ".zip",
            ".txt",
        }
    )

    def extract(self, source: Path, output: Path) -> None:
        if output.exists():
            raise ServiceError(
                "ARCHIVE_OUTPUT_EXISTS", "归档输出目录已存在，请使用原恢复流程。", 409
            )
        output.mkdir(parents=True)
        names: set[str] = set()
        total = 0
        try:
            with zipfile.ZipFile(source) as archive:
                entries = archive.infolist()
                if len(entries) > 6000:
                    raise ValueError("Archive file count exceeds its profile")
                for entry in entries:
                    name = PurePosixPath(entry.filename)
                    if (
                        name.is_absolute()
                        or ".." in name.parts
                        or "\\" in entry.filename
                        or stat.S_ISLNK(entry.external_attr >> 16)
                    ):
                        raise ValueError("Unsafe archive path or link")
                    key = name.as_posix().casefold()
                    if key in names:
                        raise ValueError("Duplicate archive path")
                    names.add(key)
                    if entry.is_dir() or name.suffix.lower() not in self.ALLOWED:
                        continue
                    total += entry.file_size
                    if total > 4 * 1024**3 or entry.file_size > 2 * 1024**3:
                        raise ValueError("Expanded archive exceeds its profile")
                    target = output.joinpath(*name.parts)
                    if not target.resolve().is_relative_to(output.resolve()):
                        raise ValueError("Archive path escapes its output")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    written = 0
                    with archive.open(entry) as stream, target.open("xb") as destination:
                        while chunk := stream.read(1024 * 1024):
                            written += len(chunk)
                            if written > entry.file_size:
                                raise ValueError("Archive changed size while expanding")
                            destination.write(chunk)
                    if written != entry.file_size:
                        raise ValueError("Truncated archive member")
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
            shutil.rmtree(output)
            raise ServiceError(
                "NATIVE_ARCHIVE_INVALID", "项目包格式或大小无效，原上传已保留。", 422
            ) from error

    @staticmethod
    def database(path: Path) -> None:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024**2:
            raise ServiceError("NATIVE_DATABASE_INVALID", "项目审核库缺失或超过读取范围。", 422)
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                db.execute("PRAGMA trusted_schema=OFF")
                if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ValueError("Native database integrity failed")
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1"
                ).fetchone():
                    raise ValueError("Active database schemas are not admitted")
                tables = {
                    row[0]
                    for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                if not {"modern_objects", "pairings", "passages", "historical_objects"} <= tables:
                    raise ValueError("Native review tables are missing")
        except (sqlite3.Error, ValueError) as error:
            raise ServiceError(
                "NATIVE_DATABASE_INVALID", "审核库不是受支持的原生项目快照。", 422
            ) from error

    @staticmethod
    def digest(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def json(path: Path, maximum: int = 8 * 1024**2) -> bytes:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            raise ServiceError("NATIVE_METADATA_INVALID", "原生项目元数据缺失或超过读取范围。", 422)
        return path.read_bytes()


class LocalResourceSnapshot:
    """Preserve immutable exports while sharing unchanged APFS data blocks.

    Clone-on-write keeps later edits isolated in both directions. Hard links are
    deliberately excluded because they would couple old and new game inputs.
    Other filesystems retain the portable copy behavior.
    """

    @staticmethod
    def copy(source: str | Path, destination: str | Path) -> str:
        source_path, destination_path = Path(source), Path(destination)
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError("Snapshot source must be a regular file")
        if destination_path.exists():
            raise FileExistsError(destination_path)
        if sys.platform == "darwin" and source_path.stat().st_size >= 1024**2:
            try:
                result = subprocess.run(
                    ["/bin/cp", "-c", str(source_path), str(destination_path)],
                    capture_output=True, check=False, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                destination_path.unlink(missing_ok=True)
                raise ServiceError(
                    "RESOURCE_SNAPSHOT_FAILED", "本机资源快照未完成；审核修改仍已保存。", 503
                ) from error
            if result.returncode == 0:
                return str(destination_path)
            # cp -c is unavailable across filesystems; clean only our new target.
            destination_path.unlink(missing_ok=True)
        return shutil.copy2(source_path, str(destination_path))
