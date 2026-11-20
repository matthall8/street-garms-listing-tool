"""app/errors.py on its own, around toy ASGI apps: the cases a real route
can't reach. The real-route case is in tests/test_routes.py."""

import asyncio
import logging

import pytest
from fastapi.testclient import TestClient

from app.errors import SERVER_ERROR, LogUnhandledErrors, logger

RAW = "raw-error-text-that-must-not-leave"


async def raises_before_responding(scope, receive, send):
    raise KeyError(RAW)


async def raises_after_starting(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    raise KeyError(RAW)


def test_no_matched_route_logs_the_method_only(caplog):
    client = TestClient(LogUnhandledErrors(raises_before_responding), raise_server_exceptions=False)
    with caplog.at_level(logging.WARNING):
        response = client.get(f"/{RAW}")

    assert (response.status_code, response.json()) == (500, {"detail": SERVER_ERROR})
    (record,) = caplog.records
    assert record.name == logger.name
    assert record.getMessage() == "GET failed: error=KeyError"
    assert record.exc_info is None
    assert RAW not in caplog.text


def test_a_started_response_is_logged_and_left_alone(caplog):
    """Too late for a 500: the middleware logs and stops, sending nothing."""
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    app = LogUnhandledErrors(raises_after_starting)
    scope = {"type": "http", "method": "POST", "path": f"/{RAW}", "headers": []}
    with caplog.at_level(logging.WARNING):
        asyncio.run(app(scope, receive, send))  # doesn't raise

    assert sent == [{"type": "http.response.start", "status": 200, "headers": []}]
    (record,) = caplog.records
    assert record.getMessage() == "POST failed: error=KeyError"
    assert RAW not in caplog.text


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
def test_other_scopes_pass_through(scope_type):
    app = LogUnhandledErrors(raises_before_responding)
    with pytest.raises(KeyError):
        asyncio.run(app({"type": scope_type}, None, None))  # pyright: ignore[reportArgumentType]
