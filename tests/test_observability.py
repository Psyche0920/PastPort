"""Safe structured logs preserve correlation, cancellation and host configuration."""

import asyncio
import io
import json
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send
from test_service import create_run, headers, settings, wait_for

from pastport.api.app import create_app
from pastport.api.request_logging import RequestLoggingMiddleware
from pastport.observability import LoggingConfiguration, SafeJsonFormatter, request_context


def records(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_busy_worker_reports_safe_error_code_without_private_paths(tmp_path: Path) -> None:
    import fcntl
    from typing import cast

    from pastport.application.models import ServiceError
    from pastport.workflow.stages import StageRunner
    from pastport.workflow.worker import EditorialWorker

    stream = io.StringIO()
    worker = EditorialWorker(cast(StageRunner, object()), tmp_path / "checkpoints.sqlite3")
    with (tmp_path / "instance.lock").open("a") as owner, LoggingConfiguration(stream=stream):
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with pytest.raises(ServiceError) as failure:
                worker.run()
            assert failure.value.code == "INSTANCE_BUSY"
        finally:
            fcntl.flock(owner, fcntl.LOCK_UN)
    diagnostic = next(row for row in records(stream) if row["event"] == "worker_stopped")
    assert diagnostic["error_code"] == "INSTANCE_BUSY"
    assert diagnostic["error_type"] == "ServiceError"
    assert str(tmp_path) not in stream.getvalue()
    assert worker.ready.is_set() and worker.failure is failure.value


def test_formatter_excludes_raw_values_arguments_exceptions_and_unapproved_fields() -> None:
    stream = io.StringIO()
    with LoggingConfiguration(stream=stream):
        logger = logging.getLogger("pastport.test")
        try:
            raise ValueError("PRIVATE_PROVIDER_BODY /private/secret")
        except ValueError:
            logger.exception(
                "provider_failed",
                extra={"error_code": "OUTCOME_UNKNOWN", "token": "TOKEN_SENTINEL"},
            )
        logger.warning(
            "SECRET %s", "RAW_PROMPT", extra={"run_id": "unsafe\nsource", "duration_ms": -1}
        )
        logger.info("request_completed", extra={"run_id": "run-1", "duration_ms": 12})
    text = stream.getvalue()
    assert all(
        value not in text
        for value in (
            "PRIVATE_PROVIDER_BODY",
            "/private/secret",
            "TOKEN_SENTINEL",
            "RAW_PROMPT",
            "SECRET",
            "unsafe",
        )
    )
    parsed = records(stream)
    assert parsed[0]["event"] == "provider_failed" and parsed[0]["error_type"] == "ValueError"
    assert parsed[1]["event"] == "diagnostic_event" and "duration_ms" not in parsed[1]
    assert parsed[2]["run_id"] == "run-1" and parsed[2]["duration_ms"] == 12
    assert "+00:00" in str(parsed[0]["timestamp"])


def test_configuration_does_not_duplicate_or_change_root_and_restores_on_exit() -> None:
    root = logging.getLogger()
    before = (tuple(root.handlers), root.level)
    logger = logging.getLogger("pastport")
    original = (tuple(logger.handlers), logger.level, logger.propagate)
    stream = io.StringIO()
    configuration = LoggingConfiguration(stream=stream)
    with configuration:
        with pytest.raises(RuntimeError):
            configuration.__enter__()
        logging.getLogger("pastport.test").info("module_completed")
        logging.getLogger("uvicorn.error").error("Private server exception text")
    assert len(records(stream)) == 2
    assert (tuple(root.handlers), root.level) == before
    assert (tuple(logger.handlers), logger.level, logger.propagate) == original
    assert not stream.closed
    assert isinstance(configuration.handler, type(None))


def test_actual_http_and_worker_logs_are_safe_and_correlated(tmp_path: Path) -> None:
    stream = io.StringIO()
    with LoggingConfiguration(stream=stream), TestClient(create_app(settings(tmp_path))) as client:
        rejected = client.post(
            "/api/v1/projects?secret=QUERY_SENTINEL",
            headers={"Authorization": "Bearer TOKEN_SENTINEL"},
            content=b"PRIVATE_SOURCE_BODY",
        )
        assert rejected.status_code == 401
        run_id = create_run(client)
        wait_for(client, run_id, "needs_review")
        first = client.get("/api/v1/runs/" + run_id, headers=headers())
        second = client.get("/api/v1/runs/" + run_id, headers=headers())
        assert first.headers["x-request-id"] != second.headers["x-request-id"]
        assert "request_id" not in first.json()
    parsed = records(stream)
    requests = [
        item for item in parsed if item["event"] in ("request_completed", "request_rejected")
    ]
    assert requests and all(
        item["environment"] == "test" and item["request_id"] for item in requests
    )
    denied = next(item for item in requests if item["status_code"] == 401)
    assert rejected.headers["x-request-id"] == denied["request_id"]
    assert len([item for item in requests if item["method"] == "GET"]) == 0
    assert not any(
        value in stream.getvalue()
        for value in ("TOKEN_SENTINEL", "QUERY_SENTINEL", "PRIVATE_SOURCE_BODY")
    )
    assert request_context.get() is None


def test_concurrent_requests_keep_separate_contexts_and_cancellation_propagates() -> None:
    async def scenario() -> None:
        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: Message) -> None:
            pass

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            context = request_context.get()
            assert context is not None
            await asyncio.sleep(0)
            assert request_context.get() == context
            if scope.get("cancel"):
                raise asyncio.CancelledError
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = RequestLoggingMiddleware(app, "test")
        first: Scope = {"type": "http", "method": "POST"}
        second: Scope = {"type": "http", "method": "POST"}
        await asyncio.gather(middleware(first, receive, send), middleware(second, receive, send))
        with pytest.raises(asyncio.CancelledError):
            await middleware({"type": "http", "method": "POST", "cancel": True}, receive, send)
        assert request_context.get() is None

    stream = io.StringIO()
    with LoggingConfiguration(stream=stream):
        asyncio.run(scenario())
    parsed = records(stream)
    assert len({item["request_id"] for item in parsed}) == 3
    assert parsed[-1]["event"] == "request_cancelled"
    assert parsed[-1]["error_type"] == "CancelledError"


def test_formatter_rejects_unknown_levels_and_arbitrary_record_payloads() -> None:
    with pytest.raises(ValueError):
        LoggingConfiguration("arbitrary")
    record = logging.LogRecord(
        "pastport.test", logging.ERROR, "private.py", 1, {"secret": "body"}, (), None
    )
    assert json.loads(SafeJsonFormatter().format(record))["event"] == "diagnostic_event"


def test_supported_cli_configures_json_and_disables_raw_access_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pastport.__main__ import main
    from pastport.api.settings import Accounts

    accounts = tmp_path / "accounts.json"
    accounts.write_text(Accounts(accounts=settings(tmp_path).accounts).model_dump_json())
    stream = io.StringIO()
    called = []

    def server(
        app: FastAPI, *, host: str, port: int, workers: int, log_config: object, access_log: bool
    ) -> None:
        called.append(True)
        assert host == "127.0.0.1" and workers == 1
        assert log_config is None and access_log is False
        with TestClient(app) as client:
            assert client.post("/api/v1/projects").status_code == 401

    monkeypatch.setattr("pastport.__main__.uvicorn.run", server)
    monkeypatch.setattr("sys.stderr", stream)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pastport",
            "--accounts",
            str(accounts),
            "--data-directory",
            str(tmp_path / "data"),
            "--test-fixture-directory",
            str(Path(__file__).parent / "fixtures/reference"),
        ],
    )
    main()
    assert called == [True]
    denied = next(item for item in records(stream) if item["event"] == "request_rejected")
    assert denied["error_code"] == "AUTHENTICATION_REQUIRED"


def test_unexpected_boundary_failure_is_logged_once_and_reraised_without_body() -> None:
    async def scenario() -> None:
        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            raise RuntimeError("PRIVATE_FAILURE_BODY")

        async def receive() -> Message:
            return {"type": "http.request", "body": b""}

        async def send(message: Message) -> None:
            pass

        with pytest.raises(RuntimeError, match="PRIVATE_FAILURE_BODY"):
            await RequestLoggingMiddleware(app, "test")(
                {"type": "http", "method": "POST"}, receive, send
            )
        assert request_context.get() is None

    stream = io.StringIO()
    with LoggingConfiguration(stream=stream):
        asyncio.run(scenario())
    parsed = records(stream)
    assert len(parsed) == 1 and parsed[0]["event"] == "request_failed"
    assert parsed[0]["error_type"] == "RuntimeError"
    assert "PRIVATE_FAILURE_BODY" not in stream.getvalue()
