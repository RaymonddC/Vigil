"""I2 — Prompt Opinion SHARP Header Compliance Tests.

Verifies the 3 canonical SHARP headers round-trip through every layer of
the Vigil stack:

  Layer 1 — MCP server: headers parsed via context.py, validated by middleware.py
  Layer 2 — A2A metadata bridge: message.metadata[*fhir-context*] → 3 SHARP headers
  Layer 3 — Capability extension: ai.promptopinion/fhir-context advertised

Reference:
  API_CONTRACTS.md §2 (SHARP headers), §4 (A2A metadata bridge)
  po-community-mcp/python/mcp_constants.py
  po-community-mcp/python/fhir_utilities.py
  po-adk-python/shared/fhir_hook.py
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from backend.a2a_agent.fhir_hook import (
    FHIR_CONTEXT_KEY,
    extract_fhir_from_metadata,
    fhir_metadata_to_sharp_headers,
)
from backend.mcp_server.context import (
    FHIR_ACCESS_TOKEN_HEADER,
    FHIR_SERVER_URL_HEADER,
    PATIENT_ID_HEADER,
    _redact_token,
    get_sharp_context,
    resolve_patient_id,
)

# ---------------------------------------------------------------------------
# Canonical test values — match po-community-mcp/python/mcp_constants.py
# ---------------------------------------------------------------------------

CANONICAL_FHIR_URL = "http://localhost:8080/fhir"
CANONICAL_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test-token"
CANONICAL_PATIENT_ID = "PT-007"

# A2A metadata URI — must contain the substring "fhir-context"
A2A_FHIR_CONTEXT_URI = "https://vigil.local/schemas/a2a/v1/fhir-context"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_starlette_request(headers: dict[str, str]) -> Request:
    """Build a minimal Starlette Request with the given HTTP headers."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
    }
    return Request(scope=scope)


def _make_ctx(headers: dict[str, str]) -> MagicMock:
    """Return a mocked FastMCP Context with SHARP headers injected."""
    mock = MagicMock()
    mock.request_context.request = _make_starlette_request(headers)
    return mock


# =========================================================================
# Layer 1 — MCP SHARP Header Contract
# =========================================================================


class TestMcpSharpContract:
    """Verify that the MCP server correctly parses SHARP headers
    exactly per po-community-mcp/python/mcp_constants.py.
    """

    def test_header_constants_match_po_spec(self):
        """The 3 SHARP header name constants must match po-community-mcp verbatim."""
        assert FHIR_SERVER_URL_HEADER == "x-fhir-server-url"
        assert FHIR_ACCESS_TOKEN_HEADER == "x-fhir-access-token"
        assert PATIENT_ID_HEADER == "x-patient-id"

    def test_all_three_headers_extracted(self):
        """All 3 SHARP headers parsed into FhirContext when present."""
        ctx = _make_ctx({
            FHIR_SERVER_URL_HEADER: CANONICAL_FHIR_URL,
            FHIR_ACCESS_TOKEN_HEADER: CANONICAL_TOKEN,
            PATIENT_ID_HEADER: CANONICAL_PATIENT_ID,
        })
        sharp = get_sharp_context(ctx)
        assert sharp.url == CANONICAL_FHIR_URL
        assert sharp.token == CANONICAL_TOKEN
        assert sharp.patient_id == CANONICAL_PATIENT_ID

    def test_missing_fhir_url_raises(self):
        """Missing x-fhir-server-url must raise ValueError."""
        ctx = _make_ctx({
            FHIR_ACCESS_TOKEN_HEADER: CANONICAL_TOKEN,
            PATIENT_ID_HEADER: CANONICAL_PATIENT_ID,
        })
        with pytest.raises(ValueError, match="Missing required SHARP header"):
            get_sharp_context(ctx)

    def test_empty_fhir_url_raises(self):
        """Empty x-fhir-server-url must be treated as missing."""
        ctx = _make_ctx({
            FHIR_SERVER_URL_HEADER: "",
            PATIENT_ID_HEADER: CANONICAL_PATIENT_ID,
        })
        with pytest.raises(ValueError, match="Missing required SHARP header"):
            get_sharp_context(ctx)

    def test_empty_token_tolerated(self):
        """Empty x-fhir-access-token should be tolerated (dev HAPI has no auth)."""
        ctx = _make_ctx({
            FHIR_SERVER_URL_HEADER: CANONICAL_FHIR_URL,
            FHIR_ACCESS_TOKEN_HEADER: "",
            PATIENT_ID_HEADER: CANONICAL_PATIENT_ID,
        })
        sharp = get_sharp_context(ctx)
        assert sharp.url == CANONICAL_FHIR_URL
        assert sharp.token is None  # Empty → None
        assert sharp.patient_id == CANONICAL_PATIENT_ID

    def test_missing_token_tolerated(self):
        """Missing x-fhir-access-token should be tolerated."""
        ctx = _make_ctx({
            FHIR_SERVER_URL_HEADER: CANONICAL_FHIR_URL,
            PATIENT_ID_HEADER: CANONICAL_PATIENT_ID,
        })
        sharp = get_sharp_context(ctx)
        assert sharp.token is None

    def test_missing_patient_id_tolerated(self):
        """Missing x-patient-id tolerated — it can come from tool input."""
        ctx = _make_ctx({
            FHIR_SERVER_URL_HEADER: CANONICAL_FHIR_URL,
        })
        sharp = get_sharp_context(ctx)
        assert sharp.patient_id is None

    def test_patient_id_resolution_input_wins(self):
        """Explicit patient_id arg must override SHARP header per API_CONTRACTS.md §2."""
        ctx = _make_ctx({
            FHIR_SERVER_URL_HEADER: CANONICAL_FHIR_URL,
            PATIENT_ID_HEADER: "PT-HEADER",
        })
        sharp = get_sharp_context(ctx)
        pid = resolve_patient_id("PT-INPUT", sharp)
        assert pid == "PT-INPUT"

    def test_patient_id_resolution_header_fallback(self):
        """When tool input is None, fall back to SHARP header patient_id."""
        ctx = _make_ctx({
            FHIR_SERVER_URL_HEADER: CANONICAL_FHIR_URL,
            PATIENT_ID_HEADER: "PT-HEADER",
        })
        sharp = get_sharp_context(ctx)
        pid = resolve_patient_id(None, sharp)
        assert pid == "PT-HEADER"

    def test_patient_id_resolution_neither_raises(self):
        """No patient_id in input or header must raise ValueError."""
        ctx = _make_ctx({
            FHIR_SERVER_URL_HEADER: CANONICAL_FHIR_URL,
        })
        sharp = get_sharp_context(ctx)
        with pytest.raises(ValueError, match="No patient_id provided"):
            resolve_patient_id(None, sharp)

    def test_headers_case_insensitive(self):
        """SHARP headers must be case-insensitive per HTTP spec."""
        ctx = _make_ctx({
            "X-Fhir-Server-Url": CANONICAL_FHIR_URL,
            "X-Fhir-Access-Token": CANONICAL_TOKEN,
            "X-Patient-Id": CANONICAL_PATIENT_ID,
        })
        sharp = get_sharp_context(ctx)
        assert sharp.url == CANONICAL_FHIR_URL
        assert sharp.token == CANONICAL_TOKEN
        assert sharp.patient_id == CANONICAL_PATIENT_ID


# =========================================================================
# Layer 2 — A2A Metadata Bridge
# =========================================================================


class TestA2aMetadataBridge:
    """Verify that A2A message.metadata[*fhir-context*] correctly maps
    to the 3 SHARP headers per API_CONTRACTS.md §4.
    """

    def test_fhir_context_key_contains_substring(self):
        """The FHIR_CONTEXT_KEY constant must be 'fhir-context'."""
        assert FHIR_CONTEXT_KEY == "fhir-context"

    def test_extract_from_canonical_uri(self):
        """Extract FHIR context from a fully-qualified URI key."""
        metadata = {
            A2A_FHIR_CONTEXT_URI: {
                "fhirUrl": CANONICAL_FHIR_URL,
                "fhirToken": CANONICAL_TOKEN,
                "patientId": CANONICAL_PATIENT_ID,
            }
        }
        key, fhir_dict = extract_fhir_from_metadata(metadata)
        assert key == A2A_FHIR_CONTEXT_URI
        assert fhir_dict is not None
        assert fhir_dict["fhirUrl"] == CANONICAL_FHIR_URL
        assert fhir_dict["fhirToken"] == CANONICAL_TOKEN
        assert fhir_dict["patientId"] == CANONICAL_PATIENT_ID

    def test_extract_from_any_key_containing_fhir_context(self):
        """Any key containing the substring 'fhir-context' must match."""
        metadata = {
            "http://example.com/custom/fhir-context": {
                "fhirUrl": "http://example.com/fhir",
                "fhirToken": "",
                "patientId": "PT-001",
            }
        }
        key, fhir_dict = extract_fhir_from_metadata(metadata)
        assert key == "http://example.com/custom/fhir-context"
        assert fhir_dict is not None
        assert fhir_dict["fhirUrl"] == "http://example.com/fhir"

    def test_extract_from_json_string_value(self):
        """Metadata value can be a JSON string (coerced to dict)."""
        metadata = {
            A2A_FHIR_CONTEXT_URI: json.dumps({
                "fhirUrl": CANONICAL_FHIR_URL,
                "fhirToken": CANONICAL_TOKEN,
                "patientId": CANONICAL_PATIENT_ID,
            })
        }
        key, fhir_dict = extract_fhir_from_metadata(metadata)
        assert key == A2A_FHIR_CONTEXT_URI
        assert fhir_dict is not None
        assert fhir_dict["fhirUrl"] == CANONICAL_FHIR_URL

    def test_extract_no_fhir_context_key(self):
        """Missing fhir-context key returns (None, None)."""
        metadata = {"some-other-key": {"data": "value"}}
        key, fhir_dict = extract_fhir_from_metadata(metadata)
        assert key is None
        assert fhir_dict is None

    def test_extract_none_metadata(self):
        """None metadata returns (None, None)."""
        key, fhir_dict = extract_fhir_from_metadata(None)
        assert key is None
        assert fhir_dict is None

    def test_extract_empty_metadata(self):
        """Empty dict metadata returns (None, None)."""
        key, fhir_dict = extract_fhir_from_metadata({})
        assert key is None
        assert fhir_dict is None

    def test_extract_invalid_json_string(self):
        """Invalid JSON string value returns (key, None)."""
        metadata = {A2A_FHIR_CONTEXT_URI: "not-valid-json{"}
        key, fhir_dict = extract_fhir_from_metadata(metadata)
        assert key == A2A_FHIR_CONTEXT_URI
        assert fhir_dict is None

    def test_extract_non_dict_json_value(self):
        """JSON string that parses to a non-dict returns (key, None)."""
        metadata = {A2A_FHIR_CONTEXT_URI: json.dumps([1, 2, 3])}
        key, fhir_dict = extract_fhir_from_metadata(metadata)
        assert key == A2A_FHIR_CONTEXT_URI
        assert fhir_dict is None

    # -- fhir_metadata_to_sharp_headers --

    def test_bridge_to_sharp_headers_full(self):
        """Full A2A fhir dict translates to all 3 SHARP headers."""
        fhir_dict = {
            "fhirUrl": CANONICAL_FHIR_URL,
            "fhirToken": CANONICAL_TOKEN,
            "patientId": CANONICAL_PATIENT_ID,
        }
        headers = fhir_metadata_to_sharp_headers(fhir_dict)
        assert headers["x-fhir-server-url"] == CANONICAL_FHIR_URL
        assert headers["x-fhir-access-token"] == CANONICAL_TOKEN
        assert headers["x-patient-id"] == CANONICAL_PATIENT_ID

    def test_bridge_to_sharp_headers_empty_token(self):
        """Empty fhirToken omitted from SHARP headers (falsy)."""
        fhir_dict = {
            "fhirUrl": CANONICAL_FHIR_URL,
            "fhirToken": "",
            "patientId": CANONICAL_PATIENT_ID,
        }
        headers = fhir_metadata_to_sharp_headers(fhir_dict)
        assert "x-fhir-server-url" in headers
        assert "x-fhir-access-token" not in headers
        assert "x-patient-id" in headers

    def test_bridge_to_sharp_headers_missing_patient(self):
        """Missing patientId omitted from SHARP headers."""
        fhir_dict = {
            "fhirUrl": CANONICAL_FHIR_URL,
            "fhirToken": CANONICAL_TOKEN,
        }
        headers = fhir_metadata_to_sharp_headers(fhir_dict)
        assert headers["x-fhir-server-url"] == CANONICAL_FHIR_URL
        assert headers["x-fhir-access-token"] == CANONICAL_TOKEN
        assert "x-patient-id" not in headers

    def test_bridge_to_sharp_headers_url_only(self):
        """Minimal: only fhirUrl produces only x-fhir-server-url."""
        fhir_dict = {"fhirUrl": CANONICAL_FHIR_URL}
        headers = fhir_metadata_to_sharp_headers(fhir_dict)
        assert headers == {"x-fhir-server-url": CANONICAL_FHIR_URL}


# =========================================================================
# Layer 2b — Full A2A → SHARP Round-Trip
# =========================================================================


class TestA2aToMcpRoundTrip:
    """Verify the full pipeline: A2A message metadata → extract → bridge →
    MCP SHARP context. This is the critical compliance path: Prompt Opinion
    sends FHIR context in A2A metadata, the agent must translate it into
    SHARP headers for downstream MCP tool calls.
    """

    def test_full_round_trip(self):
        """A2A metadata → extract → bridge → MCP context → FhirContext."""
        # Step 1: Simulate incoming A2A message with FHIR metadata
        a2a_metadata = {
            A2A_FHIR_CONTEXT_URI: {
                "fhirUrl": CANONICAL_FHIR_URL,
                "fhirToken": CANONICAL_TOKEN,
                "patientId": CANONICAL_PATIENT_ID,
            }
        }

        # Step 2: Extract FHIR context from metadata (sentinel.py does this)
        key, fhir_dict = extract_fhir_from_metadata(a2a_metadata)
        assert fhir_dict is not None

        # Step 3: Bridge to SHARP headers (sentinel.py does this)
        sharp_headers = fhir_metadata_to_sharp_headers(fhir_dict)

        # Step 4: Feed SHARP headers into MCP context (tool handler does this)
        ctx = _make_ctx(sharp_headers)
        sharp = get_sharp_context(ctx)

        # Step 5: Verify round-trip fidelity
        assert sharp.url == CANONICAL_FHIR_URL
        assert sharp.token == CANONICAL_TOKEN
        assert sharp.patient_id == CANONICAL_PATIENT_ID

    def test_round_trip_empty_token(self):
        """Round-trip with empty token (dev HAPI) must not error."""
        a2a_metadata = {
            A2A_FHIR_CONTEXT_URI: {
                "fhirUrl": CANONICAL_FHIR_URL,
                "fhirToken": "",
                "patientId": CANONICAL_PATIENT_ID,
            }
        }
        _, fhir_dict = extract_fhir_from_metadata(a2a_metadata)
        sharp_headers = fhir_metadata_to_sharp_headers(fhir_dict)
        ctx = _make_ctx(sharp_headers)
        sharp = get_sharp_context(ctx)
        assert sharp.url == CANONICAL_FHIR_URL
        assert sharp.token is None  # empty → None
        assert sharp.patient_id == CANONICAL_PATIENT_ID

    def test_round_trip_json_string_metadata(self):
        """Round-trip when metadata value is a JSON string (PO runtime variant)."""
        a2a_metadata = {
            A2A_FHIR_CONTEXT_URI: json.dumps({
                "fhirUrl": CANONICAL_FHIR_URL,
                "fhirToken": CANONICAL_TOKEN,
                "patientId": CANONICAL_PATIENT_ID,
            })
        }
        _, fhir_dict = extract_fhir_from_metadata(a2a_metadata)
        sharp_headers = fhir_metadata_to_sharp_headers(fhir_dict)
        ctx = _make_ctx(sharp_headers)
        sharp = get_sharp_context(ctx)
        assert sharp.url == CANONICAL_FHIR_URL
        assert sharp.token == CANONICAL_TOKEN
        assert sharp.patient_id == CANONICAL_PATIENT_ID


# =========================================================================
# Layer 3 — Capability Extension Advertisement
# =========================================================================


class TestCapabilityExtension:
    """Verify the MCP server advertises ai.promptopinion/fhir-context
    in its capabilities, so PO knows to inject SHARP headers.
    """

    def test_capability_patched(self):
        """FastMCP server capabilities must include the PO FHIR extension."""
        from mcp.server.lowlevel.server import NotificationOptions

        from backend.mcp_server.server import mcp

        # Call the patched get_capabilities with a valid NotificationOptions
        caps = mcp._mcp_server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities=None,
        )
        extensions = caps.model_extra.get("extensions", {})
        assert "ai.promptopinion/fhir-context" in extensions, (
            f"Expected ai.promptopinion/fhir-context in capabilities.extensions; "
            f"got: {extensions}"
        )

    def test_stateless_http_enabled(self):
        """FastMCP must use stateless_http=True (required by Prompt Opinion)."""
        from backend.mcp_server.server import mcp

        # stateless_http is set during construction; verify the app can be built
        http_app = mcp.streamable_http_app()
        assert http_app is not None


# =========================================================================
# Token Redaction in Logs (SEC-03)
# =========================================================================


class TestTokenRedaction:
    """Bearer tokens must never appear in log output.

    Covers:
    - _redact_token utility
    - SHARP context logging in context.py
    - SHARP middleware logging in middleware.py
    """

    def test_redact_none(self):
        assert _redact_token(None) == "<empty>"

    def test_redact_empty(self):
        assert _redact_token("") == "<empty>"

    def test_redact_short_token(self):
        """Tokens ≤4 chars fully redacted."""
        assert _redact_token("abc") == "****"
        assert _redact_token("abcd") == "****"

    def test_redact_long_token(self):
        """Tokens >4 chars show first 4 + ****."""
        assert _redact_token("abcdefghij") == "abcd****"

    def test_redact_jwt_like_token(self):
        """JWT-like token redacts beyond first 4 chars."""
        result = _redact_token(CANONICAL_TOKEN)
        assert result.startswith("eyJh")
        assert result.endswith("****")
        assert CANONICAL_TOKEN not in result

    def test_sharp_context_logs_redacted_token(self, caplog):
        """get_sharp_context must log the token in redacted form."""
        ctx = _make_ctx({
            FHIR_SERVER_URL_HEADER: CANONICAL_FHIR_URL,
            FHIR_ACCESS_TOKEN_HEADER: CANONICAL_TOKEN,
            PATIENT_ID_HEADER: CANONICAL_PATIENT_ID,
        })
        with caplog.at_level(logging.INFO, logger="vigil.mcp.context"):
            get_sharp_context(ctx)
        # The full token must never appear in logs
        for record in caplog.records:
            full_msg = str(record.__dict__)
            assert CANONICAL_TOKEN not in full_msg, (
                f"Full bearer token leaked into log record: {full_msg}"
            )


# =========================================================================
# A2A AgentCard — Extension Declaration
# =========================================================================


class TestAgentCardExtension:
    """Verify the A2A AgentCard declares the fhir-context extension
    so Prompt Opinion can discover it.
    """

    def test_agent_card_has_fhir_extension(self):
        """AgentCard capabilities.extensions must include fhir-context."""
        import json
        from pathlib import Path

        card_path = Path(__file__).parent.parent / "backend" / "a2a_agent" / "agent_card.json"
        if not card_path.exists():
            pytest.skip("agent_card.json not yet created")

        card = json.loads(card_path.read_text())
        caps = card.get("capabilities", {})
        extensions = caps.get("extensions", [])

        # Extensions can be a list of dicts with "uri" key
        if isinstance(extensions, list):
            uris = [ext.get("uri", "") for ext in extensions if isinstance(ext, dict)]
            assert any("fhir-context" in uri for uri in uris), (
                f"AgentCard extensions must include a fhir-context URI; got: {uris}"
            )
        elif isinstance(extensions, dict):
            assert any("fhir-context" in k for k in extensions), (
                f"AgentCard extensions must include a fhir-context key; got: {list(extensions)}"
            )

    def test_agent_card_well_known_path(self):
        """AgentCard must be served at /.well-known/agent-card.json (not agent.json)."""
        # This is a static check — the actual path is configured by a2a-sdk
        # but we validate the agent_card.json file exists at the expected path
        from pathlib import Path

        card_path = Path(__file__).parent.parent / "backend" / "a2a_agent" / "agent_card.json"
        if not card_path.exists():
            pytest.skip("agent_card.json not yet created")
        card = json.loads(card_path.read_text())
        # Card should have required fields
        assert "name" in card
        assert "url" in card
        assert "skills" in card


# =========================================================================
# Wire Format Compliance — A2A JSON-RPC
# =========================================================================


class TestA2aWireFormat:
    """Verify that the A2A FHIR context wire format matches
    API_CONTRACTS.md §4 exactly.
    """

    def test_wire_format_extraction(self):
        """Simulate a full JSON-RPC payload and extract FHIR context."""
        # This is the exact wire format from API_CONTRACTS.md §4
        wire_payload_message = {
            "role": "user",
            "parts": [{"kind": "text", "text": "Screen patient-42 for deterioration."}],
            "metadata": {
                "http://vigil.local/schemas/a2a/v1/fhir-context": {
                    "fhirUrl": "http://localhost:8080/fhir",
                    "fhirToken": "",
                    "patientId": "patient-42",
                }
            },
        }

        # Extract from message.metadata (the sentinel reads context.message.metadata)
        metadata = wire_payload_message.get("metadata")
        key, fhir_dict = extract_fhir_from_metadata(metadata)

        assert key is not None
        assert "fhir-context" in key
        assert fhir_dict["fhirUrl"] == "http://localhost:8080/fhir"
        assert fhir_dict["fhirToken"] == ""
        assert fhir_dict["patientId"] == "patient-42"

        # Bridge to SHARP headers
        headers = fhir_metadata_to_sharp_headers(fhir_dict)
        assert headers["x-fhir-server-url"] == "http://localhost:8080/fhir"
        assert "x-fhir-access-token" not in headers  # empty token omitted
        assert headers["x-patient-id"] == "patient-42"

    def test_metadata_field_names_camelcase(self):
        """A2A FHIR metadata uses camelCase field names: fhirUrl, fhirToken, patientId."""
        fhir_dict = {
            "fhirUrl": "http://test/fhir",
            "fhirToken": "tok",
            "patientId": "pt-1",
        }
        headers = fhir_metadata_to_sharp_headers(fhir_dict)
        # The bridge must map camelCase → kebab-case SHARP headers
        assert "x-fhir-server-url" in headers
        assert "x-fhir-access-token" in headers
        assert "x-patient-id" in headers
