"""Enforce identity, size and raw-byte hashes for all injected resource readers."""

import hashlib

from pastport.application.models import ServiceError
from pastport.domain.resources import ResourceData, ResourceReference
from pastport.ports.resources import ResourceReader

MEDIA_EXTENSIONS = {
    "image/svg+xml": "svg",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
RESOURCE_LIMIT = 20 * 1024 * 1024


class VerifiedResourceReader:
    def __init__(self, reader: ResourceReader, maximum_bytes: int = 20 * 1024 * 1024) -> None:
        if maximum_bytes <= 0:
            raise ValueError("Resource limit must be positive")
        self.reader = reader
        self.maximum_bytes = maximum_bytes

    def read(self, reference: ResourceReference, maximum_bytes: int) -> ResourceData:
        if maximum_bytes <= 0:
            raise ServiceError("RESOURCE_LIMIT_INVALID", "Resource byte limit must be positive")
        limit = min(maximum_bytes, self.maximum_bytes)
        try:
            result = self.reader.read(reference, limit)
        except OSError as error:
            raise ServiceError(
                "RESOURCE_UNAVAILABLE", "Registered resource cannot be read", 503
            ) from error
        if result.reference != reference:
            raise ServiceError(
                "RESOURCE_IDENTITY_MISMATCH",
                "Resource reader returned a different project or identity",
            )
        if len(result.content) > limit:
            raise ServiceError("RESOURCE_TOO_LARGE", "Resource exceeds its byte limit")
        if hashlib.sha256(result.content).hexdigest() != reference.sha256:
            raise ServiceError("MEDIA_CHANGED", "Resource bytes do not match their registered hash")
        return result
