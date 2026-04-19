"""SHARP header parsing and FHIR context extraction for FastMCP tools.

Reads the three canonical SHARP headers from the Starlette request
underlying each FastMCP tool invocation and constructs a FhirContext.

Reference: po-community-mcp/python/fhir_utilities.py, mcp_constants.py
           API_CONTRACTS.md §2
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from mcp.server.fastmcp import Context

from backend.schemas import FhirContext

logger = logging.getLogger("vigil.mcp.context")

# ---------------------------------------------------------------------------
# SHARP header constants (verbatim from po-community-mcp/python/mcp_constants.py)
# ---------------------------------------------------------------------------

FHIR_SERVER_URL_HEADER = "x-fhir-server-url"
FHIR_ACCESS_TOKEN_HEADER = "x-fhir-access-token"
PATIENT_ID_HEADER = "x-patient-id"

# ---------------------------------------------------------------------------
# SEC-01 SSRF allowlist
# ---------------------------------------------------------------------------

DEFAULT_ALLOWED_FHIR_HOSTS = "http://localhost:8080/fhir,http://hapi:8080/fhir"


def _get_allowed_fhir_hosts() -> set[str]:
    """Parse ALLOWED_FHIR_HOSTS env var into a normalized set of origins."""
    raw = os.environ.get("ALLOWED_FHIR_HOSTS", DEFAULT_ALLOWED_FHIR_HOSTS)
    hosts: set[str] = set()
    for entry in raw.split(","):
        entry = entry.strip().rstrip("/")
        if entry:
            hosts.add(entry)
    return hosts


def _validate_fhir_url(url: str) -> None:
    """SEC-01: Validate x-fhir-server-url against SSRF allowlist.

    Raises ValueError if the URL is not in ALLOWED_FHIR_HOSTS.
    """
    normalized = url.rstrip("/")
    allowed = _get_allowed_fhir_hosts()

    # Check if the URL starts with any allowed host
    for allowed_host in allowed:
        if normalized == allowed_host or normalized.startswith(allowed_host + "/"):
            return

    parsed = urlparse(normalized)
    raise ValueError(
        f"SSRF blocked: FHIR server URL '{parsed.scheme}://{parsed.netloc}' "
        f"is not in ALLOWED_FHIR_HOSTS. Allowed: {sorted(allowed)}"
    )


def _redact_token(token: str | None) -> str:
    """Redact bearer token for logging — show first 4 chars only."""
    if not token:
        return "<empty>"
    if len(token) <= 4:
        return "****"
    return token[:4] + "****"


# ---------------------------------------------------------------------------
# Public helpers — called from every tool
# ---------------------------------------------------------------------------


def get_sharp_context(ctx: Context) -> FhirContext:
    """Extract and validate SHARP headers from a FastMCP tool context.

    Raises ValueError if x-fhir-server-url is missing or fails SSRF check.
    """
    request = ctx.request_context.request  # Starlette Request
    url = request.headers.get(FHIR_SERVER_URL_HEADER)
    if not url:
        raise ValueError(
            f"Missing required SHARP header: {FHIR_SERVER_URL_HEADER}. "
            "Prompt Opinion must inject FHIR context."
        )

    # SEC-01: SSRF allowlist check
    _validate_fhir_url(url)

    token = request.headers.get(FHIR_ACCESS_TOKEN_HEADER)
    patient_id = request.headers.get(PATIENT_ID_HEADER)

    logger.info(
        "SHARP context parsed",
        extra={
            "fhir_server_url": url,
            "fhir_access_token": _redact_token(token),
            "patient_id": patient_id or "<not set>",
        },
    )

    return FhirContext(url=url, token=token or None, patient_id=patient_id or None)


def resolve_patient_id(
    explicit_id: str | None, sharp_ctx: FhirContext
) -> str:
    """Resolve patient ID: explicit arg wins, else SHARP header.

    Raises ValueError if neither is available.
    """
    pid = explicit_id or sharp_ctx.patient_id
    if not pid:
        raise ValueError(
            "No patient_id provided in tool input and no x-patient-id SHARP header set."
        )
    return pid
