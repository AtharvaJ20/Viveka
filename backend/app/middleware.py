"""Custom ASGI middlewares.

SecurityHeadersMiddleware is implemented as a pure ASGI wrapper (not BaseHTTPMiddleware)
so that FastAPI exception handlers can still intercept exceptions and return a proper
response — BaseHTTPMiddleware.call_next re-raises exceptions before the handler runs.
"""
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Inject SR-AUTH-012 security headers on every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            await send(message)

        await self.app(scope, receive, send_with_headers)
