"""FHIR context extraction from A2A message metadata.

Translates the A2A message.metadata FHIR context into the 3 SHARP headers
that downstream MCP tool calls require. Adapted from
po-adk-python/shared/fhir_hook.py.

Reference: API_CONTRACTS.md §4, PROMPT_OPINION_INTEGRATION.md §3.2
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("vigil.a2a.fhir_hook")

FHIR_CONTEXT_KEY = "fhir-context"


def _coerce(value: Any) -> dict | None:
    """Coerce a metadata value into a dict, parsing JSON strings."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def extract_fhir_from_metadata(
    metadata: dict[str, Any] | None,
) -> tuple[str | None, dict | None]:
    """Extract FHIR context from A2A message metadata.

    Returns (metadata_key, fhir_dict) or (None, None).
    The fhir_dict has keys: fhirUrl, fhirToken, patientId.
    """
    if not isinstance(metadata, dict):
        return None, None
    for key, value in metadata.items():
        if FHIR_CONTEXT_KEY in str(key):
            return key, _coerce(value)
    return None, None


def fhir_metadata_to_sharp_headers(
    fhir_dict: dict,
) -> dict[str, str]:
    """Convert A2A FHIR metadata dict into 3 SHARP HTTP headers.

    Input keys (from PO wire format): fhirUrl, fhirToken, patientId.
    Output keys: x-fhir-server-url, x-fhir-access-token, x-patient-id.
    """
    headers: dict[str, str] = {}
    url = fhir_dict.get("fhirUrl")
    if url:
        headers["x-fhir-server-url"] = str(url)
    token = fhir_dict.get("fhirToken")
    if token:
        headers["x-fhir-access-token"] = str(token)
    patient_id = fhir_dict.get("patientId")
    if patient_id:
        headers["x-patient-id"] = str(patient_id)
    return headers
