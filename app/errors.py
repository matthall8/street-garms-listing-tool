"""The last word on an unhandled exception: one log line and a fixed 500.

A plain ASGI middleware, not BaseHTTPMiddleware. It doesn't re-raise, so
neither Starlette nor uvicorn logs the traceback, whose message can carry
values (ADR-0009, D3). A catch-all exception handler can't do this:
Starlette re-raises after it (starlette/middleware/errors.py).
"""

import logging

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SERVER_ERROR = "Something went wrong. Try again."

logger = logging.getLogger(__name__)


class LogUnhandledErrors:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception as exc:
            # The matched route's template, never the raw path, which carries
            # the item ID. The router sets scope["route"] in this same dict
            # (fastapi/routing.py; starlette/routing.py, scope.update).
            route = scope.get("route")
            where = scope["method"] + (f" {route.path}" if route is not None else "")
            # The class, never the message.
            logger.error("%s failed: error=%s", where, type(exc).__name__)
            if started:  # too late for a 500
                return
            response = JSONResponse(status_code=500, content={"detail": SERVER_ERROR})
            await response(scope, receive, send)
