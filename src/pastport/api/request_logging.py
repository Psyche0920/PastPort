"""Request correlation without retaining URLs, bodies, headers or client identities."""

import asyncio
import logging
import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pastport.observability import LogContext, request_context

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp, environment: str) -> None:
        self.app = app
        self.environment = environment

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        identifier = uuid4().hex
        token = request_context.set(LogContext(identifier, self.environment))
        started = time.monotonic()
        status = 500

        async def response(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {
                    **message,
                    "headers": [
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() != b"x-request-id"
                    ]
                    + [(b"x-request-id", identifier.encode("ascii"))],
                }
            await send(message)

        try:
            await self.app(scope, receive, response)
        except BaseException as error:
            logger.log(
                logging.INFO if isinstance(error, asyncio.CancelledError) else logging.ERROR,
                "request_cancelled"
                if isinstance(error, asyncio.CancelledError)
                else "request_failed",
                extra={
                    "method": scope["method"],
                    "error_type": type(error).__name__,
                    "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                },
            )
            raise
        else:
            # Successful polling/static reads are intentionally quiet.
            if scope["method"] not in ("GET", "HEAD", "OPTIONS") or status >= 400:
                logger.log(
                    logging.ERROR
                    if status >= 500
                    else logging.WARNING
                    if status >= 400
                    else logging.INFO,
                    "request_rejected" if status >= 400 else "request_completed",
                    extra={
                        "method": scope["method"],
                        "status_code": status,
                        "error_code": scope.get("pastport.error_code"),
                        "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                    },
                )
        finally:
            request_context.reset(token)
