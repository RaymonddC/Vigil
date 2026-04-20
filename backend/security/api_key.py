"""Shared X-API-Key enforcement middleware (SEC-05).

All three FastAPI services (API proxy, MCP server, A2A agent) use this
shared helper so the enforcement logic lives in one place.
"""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import Sequence
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger("vigil.security.api_key")

_DEFAULT_SKIP: tuple[str, ...] = ("/docs", "/openapi.json", "/redoc")


def warn_if_unset() -> None:
    """Log a startup warning if VIGIL_API_KEY is not configured."""
    if not os.environ.get("VIGIL_API_KEY"):
        logger.warning(
            "VIGIL_API_KEY not configured — API key enforcement disabled. "
            "Set VIGIL_API_KEY before opening any tunnel (SEC-05)."
        )


def build_api_key_middleware(
    skip_prefixes: Sequence[str] = _DEFAULT_SKIP,
) -> Any:
    """Return an async HTTP middleware function enforcing X-API-Key.

    Reads VIGIL_API_KEY at request time so tests can monkeypatch os.environ.
    Dev mode: if VIGIL_API_KEY is unset, all requests are allowed through.
    Exempt paths (skip_prefixes) are never checked regardless of key state.
    """

    async def _api_key_middleware(request: Request, call_next: Any) -> Response:
        if any(request.url.path.startswith(p) for p in skip_prefixes):
            return await call_next(request)
        api_key = os.environ.get("VIGIL_API_KEY")
        if api_key:
            provided = request.headers.get("X-API-Key", "")
            if not secrets.compare_digest(provided, api_key):
                return JSONResponse(status_code=401, content={"error": "Unauthorized"})
        return await call_next(request)

    return _api_key_middleware
