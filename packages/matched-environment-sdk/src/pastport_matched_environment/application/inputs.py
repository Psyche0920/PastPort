"""Bounded source PDF validation before asset registration."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from pastport_matched_environment.domain.models import ProcessingLimits

PDF_SIGNATURE: Final[bytes] = b"%PDF-"


class InputValidationError(ValueError):
    """Raised for unsupported, unsafe or oversized user-supplied inputs."""


class ValidatedFile(BaseModel):
    """Preflight evidence for a file that can be registered as an immutable asset."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    path: Path
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


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


def _require_regular_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise InputValidationError(f"{label} input must be an existing regular file")


def _file_metadata(path: Path, size_bytes: int) -> ValidatedFile:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return ValidatedFile(path=path.resolve(), size_bytes=size_bytes, sha256=digest.hexdigest())
