from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import get_settings


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Simple API key auth for internal endpoints."""

    async def dispatch(self, request: Request, call_next):

        # Skip auth for health checks and telegram webhook
        if (
            request.url.path in ("/health", "/")
            or request.url.path.startswith("/telegram/webhook")
        ):
            return await call_next(request)

        settings = get_settings()
        api_key = request.headers.get("X-API-Key")

        if api_key != settings.app_secret_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
            )

        return await call_next(request)