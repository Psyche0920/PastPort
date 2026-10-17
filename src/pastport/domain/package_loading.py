"""Safe, stable failures for package consumers, independent of HTTP or storage."""

from typing import Literal

PackageLoadErrorCode = Literal[
    "RUNTIME_PACKAGE_UNREADABLE",
    "RUNTIME_PACKAGE_TOO_LARGE",
    "RUNTIME_INVALID_JSON",
    "RUNTIME_PACKAGE_INVALID",
    "RUNTIME_VERSION_UNSUPPORTED",
    "RUNTIME_CAPABILITY_UNSUPPORTED",
    "RUNTIME_IDENTITY_MISMATCH",
    "RUNTIME_HASH_MISMATCH",
]


class PackageLoadError(ValueError):
    def __init__(self, code: PackageLoadErrorCode, message: str, field_path: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.field_path = field_path
