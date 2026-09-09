import json
import logging
import secrets
import time

from fastapi import FastAPI, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import Settings

logger = logging.getLogger("tenantfiles")


def install_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = secrets.token_hex(16)
        start = time.monotonic()
        response = await call_next(request)
        response.headers.update(
            {
                "X-Request-ID": request.state.request_id,
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            }
        )
        if settings.secure_cookie:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Query string, header'lar ve body loglanmaz. Yalnızca route şablonu yazılır.
        route = request.scope.get("route")
        logger.info(
            json.dumps(
                {
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "route": getattr(route, "path", "unmatched"),
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - start) * 1000),
                }
            )
        )
        return response
