"""SHARP header enforcement middleware for the Vigil MCP server.

Validates the 3 canonical SHARP headers on every incoming request
(except /health). Rejects if x-fhir-server-url is missing. Applies
SEC-01 SSRF allowlist. Redacts bearer tokens in all log paths.

Reference: API_CONTRACTS.md §2, BUILD_PLAN.md B8
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.mcp_server.context import (
    FHIR_ACCESS_TOKEN_HEADER,
    FHIR_SERVER_URL_HEADER,
    PATIENT_ID_HEADER,
    _redact_token,
    _validate_fhir_url,
)

logger = logging.getLogger("vigil.mcp.middleware")

# Paths that bypass SHARP validation
_EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json"})


class SharpHeaderMiddleware(BaseHTTPMiddleware):
    """Starlette middleware enforcing SHARP headers on MCP requests.

    - Rejects requests missing x-fhir-server-url with 400.
    - Applies SSRF allowlist (SEC-01) on the FHIR URL.
    - Tolerates empty x-fhir-access-token (dev HAPI has no auth).
    - Redacts bearer tokens in all logged output.
    - Assigns a request_id for tracing.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip validation for exempt paths
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # Assign request ID for tracing
        request_id = request.headers.get("x-request-id", str(uuid4()))

        # --- Validate x-fhir-server-url (required) ---
        fhir_url = request.headers.get(FHIR_SERVER_URL_HEADER)
        if not fhir_url:
            logger.warning(
                "Missing SHARP header",
                extra={
                    "request_id": request_id,
                    "header": FHIR_SERVER_URL_HEADER,
                    "path": request.url.path,
                },
            )
            return JSONResponse(
                status_code=400,
                content={
                    "error": "missing_sharp_header",
                    "message": (
                        f"Required SHARP header '{FHIR_SERVER_URL_HEADER}' "
                        "is missing. The Prompt Opinion runtime must inject "
                        "FHIR context headers."
                    ),
                    "request_id": request_id,
                },
            )

        # --- SEC-01: SSRF allowlist check ---
        try:
            _validate_fhir_url(fhir_url)
        except ValueError as e:
            logger.warning(
                "SSRF blocked",
                extra={
                    "request_id": request_id,
                    "fhir_url": fhir_url,
                    "error": str(e),
                },
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "ssrf_blocked",
                    "message": str(e),
                    "request_id": request_id,
                },
            )

        # --- Log context (with token redaction) ---
        token = request.headers.get(FHIR_ACCESS_TOKEN_HEADER)
        patient_id = request.headers.get(PATIENT_ID_HEADER)

        logger.info(
            "SHARP headers validated",
            extra={
                "request_id": request_id,
                "fhir_server_url": fhir_url,
                "fhir_access_token": _redact_token(token),
                "patient_id": patient_id or "<not set>",
                "method": request.method,
                "path": request.url.path,
            },
        )

        # --- Proceed with request, tracking duration ---
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "duration_ms": duration_ms,
                "status_code": response.status_code,
                "path": request.url.path,
            },
        )

        # Propagate request_id in response
        response.headers["x-request-id"] = request_id
        return response
