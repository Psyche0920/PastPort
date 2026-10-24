"""Validate local PDF and tour files before registration or model execution."""

from __future__ import annotations

import hashlib
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from pastport_pdf_vr.domain.models import ProcessingLimits, ProjectId

PDF_SIGNATURE: Final[bytes] = b"%PDF-"
TOUR_ENTRY_NAMES: Final[frozenset[str]] = frozenset({"index.html", "tour.html"})


class InputValidationError(ValueError):
    """Raised for unsupported, unsafe or oversized user-supplied inputs."""


class LocalInputFiles(BaseModel):
    """Filesystem-only request accepted at the CLI boundary, not stored in domain records."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    project_id: ProjectId
    pdf_path: Path
    tour_path: Path


class ValidatedFile(BaseModel):
    """Preflight evidence for a file that can be registered as an immutable asset."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    path: Path
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ValidatedInputs(BaseModel):
    """Validated PDF and tour bundle metadata, before expensive extraction begins."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    project_id: ProjectId
    pdf: ValidatedFile
    tour: ValidatedFile
    tour_format: str
    tour_member_count: int = Field(ge=1)
    tour_expanded_bytes: int = Field(ge=1)


def validate_input_files(
    files: LocalInputFiles,
    limits: ProcessingLimits,
) -> ValidatedInputs:
    """Check file types, signatures, configured byte ceilings and safe tour contents."""
    pdf = _validate_pdf(files.pdf_path, limits)
    tour, tour_format, member_count, expanded_bytes = _validate_tour(files.tour_path, limits)
    return ValidatedInputs(
        project_id=files.project_id,
        pdf=pdf,
        tour=tour,
        tour_format=tour_format,
        tour_member_count=member_count,
        tour_expanded_bytes=expanded_bytes,
    )


def _validate_pdf(path: Path, limits: ProcessingLimits) -> ValidatedFile:
    if path.suffix.lower() != ".pdf":
        raise InputValidationError("PDF input must have a .pdf extension")
    _require_regular_file(path, "PDF")
    size = path.stat().st_size
    if size < len(PDF_SIGNATURE) or size > limits.pdf_max_bytes:
        raise InputValidationError("PDF size is empty or exceeds the configured byte limit")
    with path.open("rb") as pdf_file:
        if not pdf_file.read(len(PDF_SIGNATURE)).startswith(PDF_SIGNATURE):
            raise InputValidationError("PDF signature is missing")
    return _file_metadata(path, size)


def validate_pdf_file(path: Path, limits: ProcessingLimits) -> ValidatedFile:
    """Validate and fingerprint one source PDF before registering its bytes."""
    return _validate_pdf(path, limits)


def _validate_tour(
    path: Path,
    limits: ProcessingLimits,
) -> tuple[ValidatedFile, str, int, int]:
    if path.is_dir():
        member_count, expanded_bytes = _inspect_tour_directory(path, limits)
        metadata = _directory_metadata(path, expanded_bytes)
        return metadata, "directory", member_count, expanded_bytes
    if path.suffix.lower() != ".zip":
        raise InputValidationError(
            "Tour input must be a ZIP bundle or a directory with tour HTML/assets"
        )
    _require_regular_file(path, "Tour ZIP")
    compressed_bytes = path.stat().st_size
    if compressed_bytes < 1 or compressed_bytes > limits.tour_max_compressed_bytes:
        raise InputValidationError(
            "Tour ZIP is empty or exceeds the configured compressed-size limit"
        )
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if not members or len(members) > limits.tour_max_members:
                raise InputValidationError(
                    "Tour ZIP member count is empty or exceeds the configured limit"
                )
            expanded_bytes = 0
            has_tour_html = False
            names: set[str] = set()
            for member in members:
                _validate_archive_member(member)
                normalized_name = PurePosixPath(member.filename).as_posix()
                if normalized_name in names:
                    raise InputValidationError("Tour ZIP contains duplicate member paths")
                names.add(normalized_name)
                if member.flag_bits & 0x1:
                    raise InputValidationError("Encrypted tour ZIP members are not supported")
                file_type = stat.S_IFMT(member.external_attr >> 16)
                if file_type not in (0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
                    raise InputValidationError("Tour ZIP contains an unsupported special file")
                if member.is_dir():
                    continue
                expanded_bytes += member.file_size
                has_tour_html = (
                    has_tour_html or PurePosixPath(member.filename).name.lower() in TOUR_ENTRY_NAMES
                )
            if expanded_bytes < 1 or expanded_bytes > limits.tour_max_expanded_bytes:
                raise InputValidationError("Tour ZIP exceeds the configured expanded-size limit")
            if not has_tour_html:
                raise InputValidationError("Tour ZIP must contain index.html or tour.html")
    except zipfile.BadZipFile as error:
        raise InputValidationError("Tour ZIP is invalid or truncated") from error
    return _file_metadata(path, compressed_bytes), "zip", len(members), expanded_bytes


def _inspect_tour_directory(path: Path, limits: ProcessingLimits) -> tuple[int, int]:
    member_count = 0
    expanded_bytes = 0
    has_tour_html = False
    for child in path.rglob("*"):
        if child.is_symlink():
            raise InputValidationError("Tour directory cannot contain symbolic links")
        if not child.is_file():
            continue
        member_count += 1
        if member_count > limits.tour_max_members:
            raise InputValidationError("Tour directory member count exceeds the configured limit")
        expanded_bytes += child.stat().st_size
        if expanded_bytes > limits.tour_max_expanded_bytes:
            raise InputValidationError("Tour directory exceeds the configured expanded-size limit")
        has_tour_html = has_tour_html or child.name.lower() in TOUR_ENTRY_NAMES
    if not has_tour_html:
        raise InputValidationError("Tour directory must contain index.html or tour.html")
    if member_count == 0 or expanded_bytes == 0:
        raise InputValidationError("Tour directory contains no readable content")
    return member_count, expanded_bytes


def _validate_archive_member(member: zipfile.ZipInfo) -> None:
    member_path = PurePosixPath(member.filename)
    unix_mode = member.external_attr >> 16
    if member_path.is_absolute() or ".." in member_path.parts or "\\" in member.filename:
        raise InputValidationError("Tour ZIP contains an unsafe path")
    if stat.S_ISLNK(unix_mode):
        raise InputValidationError("Tour ZIP cannot contain symbolic links")


def _require_regular_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise InputValidationError(f"{label} input must be an existing regular file")


def _file_metadata(path: Path, size_bytes: int) -> ValidatedFile:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return ValidatedFile(path=path.resolve(), size_bytes=size_bytes, sha256=digest.hexdigest())


def _directory_metadata(path: Path, size_bytes: int) -> ValidatedFile:
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        relative_name = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative_name).to_bytes(4, "big"))
        digest.update(relative_name)
        digest.update(child.stat().st_size.to_bytes(8, "big"))
        with child.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return ValidatedFile(path=path.resolve(), size_bytes=size_bytes, sha256=digest.hexdigest())
