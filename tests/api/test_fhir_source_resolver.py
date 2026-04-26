"""Unit tests for backend.api.main.resolve_fhir_source.

The resolver reads three optional headers off the inbound request and returns
``(effective_url, token, source_id)``. It must fall back to the env default
on any validation failure (unknown source, regex mismatch) and never log a
token value. See cosmic-marinating-wozniak.md → Backend section.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.api import main as api_main
from backend.api.main import resolve_fhir_source


def _mk_request(headers: dict[str, str] | None = None) -> Any:
    """Lightweight stand-in for fastapi.Request — only ``.headers.get`` is used."""
    return SimpleNamespace(headers=headers or {})


_VALID_PO_URL = "https://app.promptopinion.ai/api/workspaces/abc12345-6789-4def-9012-3456789abcde/fhir"


# ---------------------------------------------------------------------------
# Default fallback paths
# ---------------------------------------------------------------------------


class TestDefaultFallback:
    def test_no_headers_returns_hapi_default(self):
        url, token, source = resolve_fhir_source(_mk_request())
        assert source == "hapi"
        assert url == api_main.FHIR_BASE_URL
        assert token is None

    def test_empty_source_header_returns_hapi(self):
        url, token, source = resolve_fhir_source(
            _mk_request({"X-Vigil-Fhir-Source": ""})
        )
        assert source == "hapi"
        assert url == api_main.FHIR_BASE_URL
        assert token is None

    def test_explicit_hapi_source_returns_hapi(self):
        url, token, source = resolve_fhir_source(
            _mk_request({"X-Vigil-Fhir-Source": "hapi"})
        )
        assert source == "hapi"
        assert url == api_main.FHIR_BASE_URL
        assert token is None

    def test_hapi_source_ignores_url_and_token(self):
        """Override fields are silently ignored when source is hapi."""
        url, token, source = resolve_fhir_source(
            _mk_request(
                {
                    "X-Vigil-Fhir-Source": "hapi",
                    "X-Vigil-Fhir-Url": _VALID_PO_URL,
                    "X-Vigil-Fhir-Token": "should-be-ignored",
                }
            )
        )
        assert source == "hapi"
        assert url == api_main.FHIR_BASE_URL
        assert token is None


# ---------------------------------------------------------------------------
# PO override — happy path
# ---------------------------------------------------------------------------


class TestPoOverride:
    def test_valid_po_source_url_and_token(self):
        url, token, source = resolve_fhir_source(
            _mk_request(
                {
                    "X-Vigil-Fhir-Source": "po",
                    "X-Vigil-Fhir-Url": _VALID_PO_URL,
                    "X-Vigil-Fhir-Token": "tok-xyz",
                }
            )
        )
        assert source == "po"
        assert url == _VALID_PO_URL
        assert token == "tok-xyz"

    def test_valid_po_url_with_trailing_slash(self):
        url, token, source = resolve_fhir_source(
            _mk_request(
                {
                    "X-Vigil-Fhir-Source": "po",
                    "X-Vigil-Fhir-Url": _VALID_PO_URL + "/",
                    "X-Vigil-Fhir-Token": "tok-xyz",
                }
            )
        )
        assert source == "po"
        # Trailing slash stripped so ``f"{url}/Patient"`` doesn't double-slash.
        assert url == _VALID_PO_URL
        assert token == "tok-xyz"

    def test_po_source_uppercase_normalises_to_lowercase(self):
        url, token, source = resolve_fhir_source(
            _mk_request(
                {
                    "X-Vigil-Fhir-Source": "PO",
                    "X-Vigil-Fhir-Url": _VALID_PO_URL,
                    "X-Vigil-Fhir-Token": "tok-xyz",
                }
            )
        )
        assert source == "po"
        assert url == _VALID_PO_URL
        assert token == "tok-xyz"

    def test_po_source_missing_token_still_resolves(self):
        """Token is optional at resolver level; the FhirClient simply omits
        the Authorization header. PO will 403 read calls without it but
        that's surfaced as a downstream error, not a resolver failure."""
        url, token, source = resolve_fhir_source(
            _mk_request(
                {
                    "X-Vigil-Fhir-Source": "po",
                    "X-Vigil-Fhir-Url": _VALID_PO_URL,
                }
            )
        )
        assert source == "po"
        assert url == _VALID_PO_URL
        assert token is None


# ---------------------------------------------------------------------------
# Validation failures fall back silently to HAPI
# ---------------------------------------------------------------------------


class TestValidationFailures:
    def test_garbage_source_falls_back_to_hapi(self, caplog):
        with caplog.at_level("WARNING"):
            url, token, source = resolve_fhir_source(
                _mk_request(
                    {
                        "X-Vigil-Fhir-Source": "evil",
                        "X-Vigil-Fhir-Url": _VALID_PO_URL,
                        "X-Vigil-Fhir-Token": "tok-xyz",
                    }
                )
            )
        assert source == "hapi"
        assert url == api_main.FHIR_BASE_URL
        assert token is None
        assert any("unknown source" in r.message for r in caplog.records)

    def test_po_url_fails_regex_falls_back_to_hapi(self, caplog):
        with caplog.at_level("WARNING"):
            url, token, source = resolve_fhir_source(
                _mk_request(
                    {
                        "X-Vigil-Fhir-Source": "po",
                        "X-Vigil-Fhir-Url": "https://evil.example.com/fhir",
                        "X-Vigil-Fhir-Token": "tok-xyz",
                    }
                )
            )
        assert source == "hapi"
        assert url == api_main.FHIR_BASE_URL
        assert token is None
        assert any("URL failed regex" in r.message for r in caplog.records)

    def test_po_url_missing_falls_back(self, caplog):
        with caplog.at_level("WARNING"):
            url, token, source = resolve_fhir_source(
                _mk_request(
                    {
                        "X-Vigil-Fhir-Source": "po",
                        "X-Vigil-Fhir-Token": "tok-xyz",
                    }
                )
            )
        assert source == "hapi"
        assert url == api_main.FHIR_BASE_URL
        assert token is None

    def test_po_url_with_query_string_rejected(self):
        url, token, source = resolve_fhir_source(
            _mk_request(
                {
                    "X-Vigil-Fhir-Source": "po",
                    "X-Vigil-Fhir-Url": _VALID_PO_URL + "?evil=1",
                    "X-Vigil-Fhir-Token": "tok-xyz",
                }
            )
        )
        assert source == "hapi"
        assert url == api_main.FHIR_BASE_URL
        assert token is None


# ---------------------------------------------------------------------------
# Token never logged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Vigil-Fhir-Source": "evil", "X-Vigil-Fhir-Token": "tok-secret-123"},
        {
            "X-Vigil-Fhir-Source": "po",
            "X-Vigil-Fhir-Url": "https://evil.example.com/fhir",
            "X-Vigil-Fhir-Token": "tok-secret-123",
        },
    ],
)
def test_token_value_never_appears_in_warn_logs(caplog, headers):
    with caplog.at_level("WARNING"):
        resolve_fhir_source(_mk_request(headers))
    for record in caplog.records:
        assert "tok-secret-123" not in record.getMessage()
        assert "tok-secret-123" not in str(record.__dict__)
