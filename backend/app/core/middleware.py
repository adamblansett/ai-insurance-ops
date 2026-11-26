import json
import math
import time
import uuid
from collections import defaultdict, deque

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

logger = structlog.get_logger(__name__)

_HEALTH_PATHS = frozenset({"/api/v1/health", "/api/v1/health/live", "/api/v1/health/ready"})


class SecurityHeadersMiddleware:
    """Pure ASGI middleware injecting X-Request-ID, CSP, security headers, and access logs."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id: str | None = None
        for key, value in scope.get("headers") or []:
            if key.decode("latin-1").lower() == "x-request-id":
                candidate = value.decode("latin-1", errors="ignore").strip()[:128]
                if candidate:
                    request_id = candidate
                    break
        resolved_id = request_id or str(uuid.uuid4())
        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET"))
        started = time.monotonic()
        status_code = 500

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=resolved_id)

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 200))
                headers = list(message.get("headers") or [])
                existing = {k.lower() for k, _ in headers}

                def _set_header(name: bytes, val: bytes) -> None:
                    if name.lower() not in existing:
                        headers.append((name, val))
                        existing.add(name.lower())

                _set_header(b"x-request-id", resolved_id.encode("latin-1"))
                _set_header(b"x-content-type-options", b"nosniff")
                _set_header(b"x-frame-options", b"DENY")
                _set_header(b"referrer-policy", b"strict-origin-when-cross-origin")
                _set_header(
                    b"permissions-policy",
                    b"camera=(), microphone=(), geolocation=()",
                )
                if path.startswith(("/docs", "/redoc")):
                    csp = (
                        "default-src 'self'; img-src 'self' data:; "
                        "style-src 'self' 'unsafe-inline'; "
                        "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'self'"
                    )
                else:
                    csp = "default-src 'self'; frame-ancestors 'none'; base-uri 'self'"
                _set_header(b"content-security-policy", csp.encode("latin-1"))

                if self.settings.app_env.strip().lower() == "production":
                    _set_header(
                        b"strict-transport-security",
                        b"max-age=31536000; includeSubDomains",
                    )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.monotonic() - started) * 1000.0, 2)
            logger.info(
                "http_request_completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()


class RateLimitMiddleware:
    """Pure ASGI sliding-window per-client-IP rate limiter for API routes."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self._windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def _resolve_client_ip(self, scope: Scope) -> str:
        for key, value in scope.get("headers") or []:
            if key.decode("latin-1").lower() == "x-forwarded-for":
                forwarded = value.decode("latin-1", errors="ignore").split(",")[0].strip()
                if forwarded:
                    return forwarded
        client = scope.get("client")
        if isinstance(client, tuple | list) and client:
            return str(client[0])
        return "unknown"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.settings.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        if path in _HEALTH_PATHS:
            await self.app(scope, receive, send)
            return

        is_auth = path.startswith(f"{self.settings.api_v1_prefix}/auth")
        bucket = "auth" if is_auth else "api"
        limit = (
            self.settings.rate_limit_auth_per_minute
            if is_auth
            else self.settings.rate_limit_requests_per_minute
        )
        client_ip = self._resolve_client_ip(scope)
        key = (client_ip, bucket)
        now = time.monotonic()
        cutoff = now - 60.0

        window = self._windows[key]
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= limit:
            retry_after = max(1, math.ceil(60.0 - (now - window[0])))
            body = json.dumps(
                {
                    "detail": (
                        f"Rate limit exceeded ({limit} req/min for {bucket}). "
                        f"Retry in {retry_after}s."
                    )
                }
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", str(retry_after).encode("ascii")),
                        (b"x-ratelimit-limit", str(limit).encode("ascii")),
                        (b"x-ratelimit-remaining", b"0"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        window.append(now)
        remaining = max(0, limit - len(window))

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-ratelimit-limit", str(limit).encode("ascii")))
                headers.append((b"x-ratelimit-remaining", str(remaining).encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
