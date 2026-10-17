"""Bounded strict JSON request parsing shared by authenticated routes."""

from fastapi import Request

from pastport.application.models import ServiceError
from pastport.domain.common import Contract

MAX_REQUEST_BYTES = 1024 * 1024


async def read_body[Payload: Contract](request: Request, model: type[Payload]) -> Payload:
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > MAX_REQUEST_BYTES:
            raise ServiceError("REQUEST_TOO_LARGE", "Request body exceeds 1 MiB", 413)
    return model.model_validate_json(bytes(chunks))
