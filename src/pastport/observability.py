"""Application-owned JSON diagnostics; never a business audit or payload dump."""

import json
import logging
import re
import sys
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Self, TextIO

EVENT = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
IDENTITY = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}\Z")
TEXT_FIELDS = frozenset(
    {
        "project_id",
        "run_id",
        "operation_id",
        "stage",
        "status",
        "error_code",
        "error_type",
        "package_hash",
        "content_version",
        "contract_version",
        "method",
    }
)
NUMBER_FIELDS = frozenset({"duration_ms", "attempt", "count", "status_code"})


@dataclass(frozen=True, slots=True)
class LogContext:
    request_id: str
    environment: str


request_context: ContextVar[LogContext | None] = ContextVar("pastport_log_context", default=None)


class SafeJsonFormatter(logging.Formatter):
    """Allowlist scalar fields; ignore arbitrary text, arguments and exception bodies."""

    def format(self, record: logging.LogRecord) -> str:
        event = (
            record.msg
            if isinstance(record.msg, str) and EVENT.fullmatch(record.msg)
            else "diagnostic_event"
        )
        payload: dict[str, str | int | float] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": event,
        }
        context = request_context.get()
        if context is not None:
            payload["request_id"] = context.request_id
            payload["environment"] = context.environment
        for name in TEXT_FIELDS:
            value = getattr(record, name, None)
            if isinstance(value, str) and IDENTITY.fullmatch(value):
                payload[name] = value
        for name in NUMBER_FIELDS:
            value = getattr(record, name, None)
            if type(value) is int and value >= 0:
                payload[name] = value
        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class LoggerState:
    logger: logging.Logger
    handlers: tuple[logging.Handler, ...]
    level: int
    propagate: bool


class LoggingConfiguration:
    """Configure only owned namespaces, restore the host state on shutdown."""

    def __init__(self, level: str = "INFO", stream: TextIO | None = None) -> None:
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError("Unsupported log level")
        self.level = level
        self.stream = stream
        self.states: list[LoggerState] = []
        self.handler: logging.StreamHandler[TextIO] | None = None

    def __enter__(self) -> Self:
        if self.handler is not None:
            raise RuntimeError("Logging configuration is already active")
        handler = logging.StreamHandler(self.stream if self.stream is not None else sys.stderr)
        handler.setFormatter(SafeJsonFormatter())
        self.handler = handler
        for name in ("pastport", "uvicorn", "uvicorn.error", "uvicorn.access"):
            logger = logging.getLogger(name)
            self.states.append(
                LoggerState(logger, tuple(logger.handlers), logger.level, logger.propagate)
            )
            logger.handlers = [handler]
            logger.setLevel(self.level)
            logger.propagate = False
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        for state in reversed(self.states):
            state.logger.handlers = list(state.handlers)
            state.logger.setLevel(state.level)
            state.logger.propagate = state.propagate
        self.states.clear()
        if self.handler is not None:
            self.handler.close()
            self.handler = None
