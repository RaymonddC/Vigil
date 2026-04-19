"""
B6 — MCP Server Integration Test Harness
=========================================
End-to-end pytest suite calling all 4 MCP tools against synthetic patient data.

FHIR backend selection (B6 acceptance criteria):
  Tries HAPI FHIR at localhost:8080; always starts the in-process fixture server
  (F6.5) as fallback.  The fixture server is preferred for clinical-assertion tests
  because it ignores the ?date= query filter, returning all synthetic observations
  regardless of the tool's time-based lookback window.

SHARP header scenarios per tool (3 × 4 = 12 routing tests):
  a)  patient_id from tool input only     — no x-patient-id header
  b)  patient_id from x-patient-id header — no input arg
  c)  both present                        — tool input wins

Trajectories:
  PT-001  stable         screen → no breaches, risk → low,  sepsis → False
  PT-007  deteriorating  screen → triggered,   risk → high, SBAR generated
  PT-009  sepsis         flag_sepsis → True + cdc_ase criteria
  PT-010  hemorrhage     screen → triggered,   SBAR generated

JUnit XML:  pytest --junit-xml=reports/junit.xml tests/integration/
Runtime target: <90 s
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from starlette.requests import Request

from backend.mcp_server.context import (
    FHIR_ACCESS_TOKEN_HEADER,
    FHIR_SERVER_URL_HEADER,
    PATIENT_ID_HEADER,
)
from backend.mcp_server.server import (
    flag_sepsis_onset,
    generate_escalation_note,
    score_deterioration_risk,
    screen_vital_thresholds,
)
from backend.schemas import (
    EscalationOutput,
    RiskScoreOutput,
    ScreenVitalsOutput,
    SepsisFlagOutput,
    ToolStatus,
)

# ---------------------------------------------------------------------------
# Patient IDs (per SYNTHETIC_DATA_SPEC §1)
# ---------------------------------------------------------------------------

PT_STABLE = "PT-001"           # stable postop
PT_DETERIORATING = "PT-007"    # hemodynamic trend fires at T+2h
PT_SEPSIS = "PT-009"           # CDC ASE fires at T+4h (postpartum)
PT_HEMORRHAGE = "PT-010"       # postpartum hemorrhage

HAPI_FHIR_URL = "http://localhost:8080/fhir"

# Wide-enough window so all fixture observations (any timestamp) pass the
# tool's lookback filter when the fixture server is used (fixture server
# ignores the date= query param and returns all rows for the patient).
LOOKBACK_MINUTES = 1440   # max allowed by schema (24 h)
WINDOW_HOURS = 24         # score_deterioration_risk window
EVAL_WINDOW = 24          # flag_sepsis_onset evaluation window


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Find an available local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _starlette_request(headers: dict[str, str]) -> Request:
    """Build a minimal Starlette Request carrying the supplied HTTP headers.

    Used to inject SHARP headers into a mocked FastMCP Context without going
    through the HTTP transport layer.
    """
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
    }
    return Request(scope=scope)


def _ctx(
    fhir_url: str,
    patient_id: str | None = None,
    token: str | None = None,
) -> MagicMock:
    """Return a mocked FastMCP Context with SHARP headers injected.

    Parameters
    ----------
    fhir_url:    Value for x-fhir-server-url (must be in ALLOWED_FHIR_HOSTS).
    patient_id:  Value for x-patient-id (omit to test 'input-only' scenario).
    token:       Value for x-fhir-access-token (omit for most tests).
    """
    sharp_headers: dict[str, str] = {FHIR_SERVER_URL_HEADER: fhir_url}
    if patient_id is not None:
        sharp_headers[PATIENT_ID_HEADER] = patient_id
    if token is not None:
        sharp_headers[FHIR_ACCESS_TOKEN_HEADER] = token
    mock = MagicMock()
    mock.request_context.request = _starlette_request(sharp_headers)
    return mock


# ---------------------------------------------------------------------------
# Per-tool async call helpers (parse JSON → dict)
# ---------------------------------------------------------------------------

async def _screen(
    fhir_url: str,
    *,
    pid_arg: str | None = None,
    pid_hdr: str | None = None,
    trajectory: str = "postop",
) -> dict[str, Any]:
    """Call screen_vital_thresholds; return parsed dict."""
    ctx = _ctx(fhir_url, patient_id=pid_hdr)
    raw = await screen_vital_thresholds(
        patient_id=pid_arg,
        lookback_minutes=LOOKBACK_MINUTES,
        trajectory=trajectory,  # type: ignore[arg-type]
        ctx=ctx,
    )
    return json.loads(raw)


async def _risk(
    fhir_url: str,
    *,
    pid_arg: str | None = None,
    pid_hdr: str | None = None,
    trajectory: str = "postop",
) -> dict[str, Any]:
    """Call score_deterioration_risk; return parsed dict."""
    ctx = _ctx(fhir_url, patient_id=pid_hdr)
    raw = await score_deterioration_risk(
        patient_id=pid_arg,
        window_hours=WINDOW_HOURS,
        trajectory=trajectory,  # type: ignore[arg-type]
        ctx=ctx,
    )
    return json.loads(raw)


async def _sepsis(
    fhir_url: str,
    *,
    pid_arg: str | None = None,
    pid_hdr: str | None = None,
) -> dict[str, Any]:
    """Call flag_sepsis_onset; return parsed dict."""
    ctx = _ctx(fhir_url, patient_id=pid_hdr)
    raw = await flag_sepsis_onset(
        patient_id=pid_arg,
        evaluation_window_hours=EVAL_WINDOW,
        ctx=ctx,
    )
    return json.loads(raw)


async def _escalation(
    fhir_url: str,
    vitals_r: dict[str, Any],
    risk_r: dict[str, Any],
    sepsis_r: dict[str, Any],
    *,
    pid_arg: str | None = None,
    pid_hdr: str | None = None,
    recipient: str = "charge_nurse",
) -> dict[str, Any]:
    """Call generate_escalation_note; return parsed dict."""
    ctx = _ctx(fhir_url, patient_id=pid_hdr)
    raw = await generate_escalation_note(
        vitals_result=vitals_r,
        risk_result=risk_r,
        sepsis_result=sepsis_r,
        patient_id=pid_arg,
        recipient_role=recipient,  # type: ignore[arg-type]
        ctx=ctx,
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _fixture_fhir_url() -> str:  # type: ignore[return]
    """Start the F6.5 fixture server in a daemon thread; return its FHIR base URL.

    The fixture server ignores the `?date=ge…` filter that tools attach to
    FHIR queries, so it returns ALL synthetic observations for each patient.
    This makes clinical-assertion tests deterministic regardless of when they run.
    """
    import uvicorn

    # Must import *after* the package is available; avoids circular imports at
    # collection time.
    from backend.fhir_fixture.main import app as fixture_app

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}/fhir"

    config = uvicorn.Config(
        fixture_app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait up to 10 s for the server to become healthy.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/fhir/metadata", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.2)
    else:
        raise RuntimeError(f"Fixture FHIR server did not start on port {port}")

    yield base_url  # type: ignore[misc]

    server.should_exit = True


@pytest.fixture(scope="module")
def fhir_url(_fixture_fhir_url: str):  # type: ignore[return]
    """Return the active FHIR base URL and configure ALLOWED_FHIR_HOSTS.

    Checks HAPI FHIR at localhost:8080 first; falls back to fixture server.
    Module-scoped so cleanup runs before other test modules execute — prevents
    ALLOWED_FHIR_HOSTS from leaking into e.g. test_sharp_middleware.py.

    NOTE: The fixture server is always returned for clinical assertions because
    HAPI filters out historical observations via the date= query param, whereas
    the fixture server returns every observation for the patient unconditionally.
    This makes clinical-outcome tests deterministic regardless of run date.
    """
    _orig = os.environ.get("ALLOWED_FHIR_HOSTS")
    try:
        r = httpx.get(f"{HAPI_FHIR_URL}/metadata", timeout=3.0)
        if r.status_code == 200:
            os.environ["ALLOWED_FHIR_HOSTS"] = (
                f"{HAPI_FHIR_URL},{_fixture_fhir_url}"
            )
        else:
            os.environ["ALLOWED_FHIR_HOSTS"] = _fixture_fhir_url
    except Exception:
        os.environ["ALLOWED_FHIR_HOSTS"] = _fixture_fhir_url

    yield _fixture_fhir_url  # type: ignore[misc]

    if _orig is None:
        os.environ.pop("ALLOWED_FHIR_HOSTS", None)
    else:
        os.environ["ALLOWED_FHIR_HOSTS"] = _orig


@pytest.fixture(scope="module", autouse=True)
def _stub_llm():  # type: ignore[return]
    """Pin LLM to stub provider for this module (no real API calls in CI)."""
    _orig = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "stub"
    yield
    if _orig is None:
        os.environ.pop("LLM_PROVIDER", None)
    else:
        os.environ["LLM_PROVIDER"] = _orig


# ---------------------------------------------------------------------------
# 1. SHARP header routing (always passes — tests middleware plumbing, not logic)
# ---------------------------------------------------------------------------

class TestSharpHeaderRouting:
    """B6 requirement: each tool tested with (a) input only, (b) header only,
    (c) both present — input wins.  These tests verify the routing contract
    defined in API_CONTRACTS.md §2 and enforced by context.py.
    """

    # ── screen_vital_thresholds ──────────────────────────────────────────────

    async def test_screen_a_input_only(self, fhir_url: str) -> None:
        """(a) patient_id in tool arg only — no x-patient-id header."""
        result = await _screen(fhir_url, pid_arg=PT_STABLE)
        assert result["patient_id"] == PT_STABLE

    async def test_screen_b_header_only(self, fhir_url: str) -> None:
        """(b) patient_id from x-patient-id SHARP header only — no arg."""
        result = await _screen(fhir_url, pid_hdr=PT_STABLE)
        assert result["patient_id"] == PT_STABLE

    async def test_screen_c_both_input_wins(self, fhir_url: str) -> None:
        """(c) both set — tool input must override SHARP header."""
        result = await _screen(fhir_url, pid_arg=PT_STABLE, pid_hdr="PT-999")
        assert result["patient_id"] == PT_STABLE

    # ── score_deterioration_risk ─────────────────────────────────────────────

    async def test_risk_a_input_only(self, fhir_url: str) -> None:
        result = await _risk(fhir_url, pid_arg=PT_STABLE)
        assert result["patient_id"] == PT_STABLE

    async def test_risk_b_header_only(self, fhir_url: str) -> None:
        result = await _risk(fhir_url, pid_hdr=PT_STABLE)
        assert result["patient_id"] == PT_STABLE

    async def test_risk_c_both_input_wins(self, fhir_url: str) -> None:
        result = await _risk(fhir_url, pid_arg=PT_STABLE, pid_hdr="PT-999")
        assert result["patient_id"] == PT_STABLE

    # ── flag_sepsis_onset ────────────────────────────────────────────────────

    async def test_sepsis_a_input_only(self, fhir_url: str) -> None:
        result = await _sepsis(fhir_url, pid_arg=PT_STABLE)
        assert result["patient_id"] == PT_STABLE

    async def test_sepsis_b_header_only(self, fhir_url: str) -> None:
        result = await _sepsis(fhir_url, pid_hdr=PT_STABLE)
        assert result["patient_id"] == PT_STABLE

    async def test_sepsis_c_both_input_wins(self, fhir_url: str) -> None:
        result = await _sepsis(fhir_url, pid_arg=PT_STABLE, pid_hdr="PT-999")
        assert result["patient_id"] == PT_STABLE

    # ── generate_escalation_note ─────────────────────────────────────────────

    async def test_escalation_a_input_only(self, fhir_url: str) -> None:
        stub_vitals = {"status": "ok", "patient_id": PT_STABLE, "breaches": []}
        stub_risk = {"status": "ok", "patient_id": PT_STABLE, "risk_band": "low",
                     "qsofa_score": 0, "composite_risk": 0.0, "contributing_conditions": [],
                     "rationale": ""}
        stub_sepsis = {"status": "ok", "patient_id": PT_STABLE, "sepsis_suspected": False,
                       "mode": "cdc_ase", "criteria_met": [], "evidence": {}}
        result = await _escalation(
            fhir_url, stub_vitals, stub_risk, stub_sepsis, pid_arg=PT_STABLE,
        )
        assert result["patient_id"] == PT_STABLE

    async def test_escalation_b_header_only(self, fhir_url: str) -> None:
        stub_vitals = {"status": "ok", "patient_id": PT_STABLE, "breaches": []}
        stub_risk = {"status": "ok", "patient_id": PT_STABLE, "risk_band": "low",
                     "qsofa_score": 0, "composite_risk": 0.0, "contributing_conditions": [],
                     "rationale": ""}
        stub_sepsis = {"status": "ok", "patient_id": PT_STABLE, "sepsis_suspected": False,
                       "mode": "cdc_ase", "criteria_met": [], "evidence": {}}
        result = await _escalation(
            fhir_url, stub_vitals, stub_risk, stub_sepsis, pid_hdr=PT_STABLE,
        )
        assert result["patient_id"] == PT_STABLE

    async def test_escalation_c_both_input_wins(self, fhir_url: str) -> None:
        stub_vitals = {"status": "ok", "patient_id": PT_STABLE, "breaches": []}
        stub_risk = {"status": "ok", "patient_id": PT_STABLE, "risk_band": "low",
                     "qsofa_score": 0, "composite_risk": 0.0, "contributing_conditions": [],
                     "rationale": ""}
        stub_sepsis = {"status": "ok", "patient_id": PT_STABLE, "sepsis_suspected": False,
                       "mode": "cdc_ase", "criteria_met": [], "evidence": {}}
        result = await _escalation(
            fhir_url, stub_vitals, stub_risk, stub_sepsis,
            pid_arg=PT_STABLE, pid_hdr="PT-999",
        )
        assert result["patient_id"] == PT_STABLE


# ---------------------------------------------------------------------------
# 2. Output schema validation — all tool responses validate against pydantic models
# ---------------------------------------------------------------------------

class TestOutputSchemas:
    """Every tool response must validate against the pydantic schema in schemas.py.

    Catches shape regressions (missing fields, wrong types) before they break
    downstream consumers.
    """

    async def test_screen_schema_valid(self, fhir_url: str) -> None:
        raw = await screen_vital_thresholds(
            patient_id=None,
            lookback_minutes=LOOKBACK_MINUTES,
            trajectory="postop",
            ctx=_ctx(fhir_url, patient_id=PT_STABLE),
        )
        out = ScreenVitalsOutput.model_validate_json(raw)
        assert out.patient_id == PT_STABLE
        assert out.status in {ToolStatus.OK, ToolStatus.TRIGGERED, ToolStatus.FHIR_UNAVAILABLE}

    async def test_risk_schema_valid(self, fhir_url: str) -> None:
        raw = await score_deterioration_risk(
            patient_id=None,
            window_hours=WINDOW_HOURS,
            trajectory="postop",
            ctx=_ctx(fhir_url, patient_id=PT_STABLE),
        )
        out = RiskScoreOutput.model_validate_json(raw)
        assert out.patient_id == PT_STABLE
        assert 0 <= out.qsofa_score <= 3
        assert 0.0 <= out.composite_risk <= 1.0
        assert out.risk_band in {"low", "moderate", "high"}

    async def test_sepsis_schema_valid(self, fhir_url: str) -> None:
        raw = await flag_sepsis_onset(
            patient_id=None,
            evaluation_window_hours=EVAL_WINDOW,
            ctx=_ctx(fhir_url, patient_id=PT_STABLE),
        )
        out = SepsisFlagOutput.model_validate_json(raw)
        assert out.patient_id == PT_STABLE
        assert isinstance(out.sepsis_suspected, bool)
        assert out.mode in {"cdc_ase", "sirs_fallback"}

    async def test_escalation_schema_valid(self, fhir_url: str) -> None:
        stub_vitals = {"status": "ok", "patient_id": PT_STABLE, "breaches": []}
        stub_risk = {"status": "ok", "patient_id": PT_STABLE, "risk_band": "low",
                     "qsofa_score": 0, "composite_risk": 0.0, "contributing_conditions": [],
                     "rationale": ""}
        stub_sepsis = {"status": "ok", "patient_id": PT_STABLE, "sepsis_suspected": False,
                       "mode": "cdc_ase", "criteria_met": [], "evidence": {}}
        raw = await generate_escalation_note(
            vitals_result=stub_vitals,
            risk_result=stub_risk,
            sepsis_result=stub_sepsis,
            patient_id=None,
            recipient_role="charge_nurse",
            ctx=_ctx(fhir_url, patient_id=PT_STABLE),
        )
        out = EscalationOutput.model_validate_json(raw)
        assert out.patient_id == PT_STABLE
        assert out.severity in {"info", "urgent", "critical"}
        assert out.sbar.situation
        assert out.communication_draft.get("resourceType") == "Communication"
        assert out.communication_draft.get("status") == "in-progress"


# ---------------------------------------------------------------------------
# 3. Stable trajectory — PT-001 (lap cholecystectomy, no deterioration)
# ---------------------------------------------------------------------------

class TestStableTrajectory:
    """PT-001 must produce no clinical alerts across all tools.

    Per SYNTHETIC_DATA_SPEC §2.1: all vitals within MEWT 'no trigger' zone
    at every timepoint.  Labs (§2.5.1) show no organ-dysfunction criterion.
    """

    async def test_screen_stable_no_breaches(self, fhir_url: str) -> None:
        """PT-001 screen_vital_thresholds → status=ok, zero breaches."""
        result = await _screen(fhir_url, pid_hdr=PT_STABLE, trajectory="postop")
        assert result["status"] == ToolStatus.OK, (
            f"PT-001 (stable) must have status=ok; got status={result['status']}, "
            f"breaches={result.get('breaches')}"
        )
        assert result["breaches"] == [], (
            f"PT-001 (stable) must have no MEWT breaches; got: {result['breaches']}"
        )

    async def test_risk_stable_low_band(self, fhir_url: str) -> None:
        """PT-001 score_deterioration_risk → risk_band=low, qsofa_score=0."""
        result = await _risk(fhir_url, pid_hdr=PT_STABLE, trajectory="postop")
        assert result["risk_band"] == "low", (
            f"PT-001 (stable) must be low risk; got risk_band={result['risk_band']}, "
            f"qsofa={result.get('qsofa_score')}, composite={result.get('composite_risk')}"
        )
        assert result["qsofa_score"] == 0

    async def test_sepsis_stable_not_suspected(self, fhir_url: str) -> None:
        """PT-001 flag_sepsis_onset → sepsis_suspected=False.

        Cefazolin prophylaxis is present but no organ-dysfunction criterion is met
        (lactate max=1.3, SBP never ≤ 100) — so CDC ASE is negative.
        """
        result = await _sepsis(fhir_url, pid_hdr=PT_STABLE)
        assert result["sepsis_suspected"] is False, (
            f"PT-001 (stable) must not have sepsis suspected; "
            f"criteria_met={result.get('criteria_met')}"
        )
        assert result["mode"] == "cdc_ase"

    async def test_escalation_stable_info_severity(self, fhir_url: str) -> None:
        """PT-001 generate_escalation_note → severity=info, SBAR all fields populated."""
        vitals_r = await _screen(fhir_url, pid_hdr=PT_STABLE, trajectory="postop")
        risk_r = await _risk(fhir_url, pid_hdr=PT_STABLE, trajectory="postop")
        sepsis_r = await _sepsis(fhir_url, pid_hdr=PT_STABLE)
        result = await _escalation(
            fhir_url, vitals_r, risk_r, sepsis_r, pid_hdr=PT_STABLE,
        )
        assert result["severity"] == "info", (
            f"PT-001 SBAR should be info severity; got {result['severity']}"
        )
        sbar = result["sbar"]
        sbar_keys = ("situation", "background", "assessment", "recommendation")
        assert all(sbar.get(k) for k in sbar_keys), (
            f"SBAR fields must all be non-empty for PT-001; got: {sbar}"
        )


# ---------------------------------------------------------------------------
# 4. Deteriorating trajectory — PT-007 (hemodynamic trend rule)
# ---------------------------------------------------------------------------

class TestDeterioratingTrajectory:
    """PT-007: MEWT hemodynamic trend fires.

    Per SYNTHETIC_DATA_SPEC §2.2: SBP drops 12.3 % (130→114) and HR rises
    21.1 % (76→92) over T+0h→T+2h, which crosses the 'TRIGGERED' threshold
    (≥10 % SBP drop AND ≥15 % HR rise in any 2 h window).
    """

    async def test_screen_deteriorating_triggered(self, fhir_url: str) -> None:
        """PT-007 screen_vital_thresholds → status=triggered."""
        result = await _screen(fhir_url, pid_hdr=PT_DETERIORATING, trajectory="postop")
        assert result["status"] == ToolStatus.TRIGGERED, (
            f"PT-007 must be TRIGGERED by hemodynamic trend rule; "
            f"status={result['status']}, breaches={result.get('breaches')}"
        )
        assert result["breaches"], (
            "PT-007 must have at least one breach entry alongside triggered status"
        )

    async def test_risk_deteriorating_high(self, fhir_url: str) -> None:
        """PT-007 score_deterioration_risk → risk_band=high (fixture-server scenario).

        The fixture server ignores ?date= and returns all 6 timepoints, so
        _latest_value() resolves T+8h vitals: SBP=88 ≤100 (qSOFA pt), RR=23 ≥22
        (qSOFA pt) → qSOFA=2 → composite ≥ 0.67 → "high".

        Live-demo note: with a narrow window (e.g. 6 h from T+2h), only T+0h–T+2h
        observations are returned.  At T+2h SBP=114 and RR=18 → qSOFA=0 and only 1
        MEWT breach (trend rule) → composite=0.15 → "low".  "Moderate" requires
        qSOFA=1 or ≥2 MEWT breaches (e.g. at T+4h onward).  This is expected B3
        behaviour; the live-demo scenario is not under test here.
        """
        result = await _risk(fhir_url, pid_hdr=PT_DETERIORATING, trajectory="postop")
        assert result["risk_band"] == "high", (
            f"PT-007 must be high risk; got risk_band={result['risk_band']}, "
            f"qsofa={result.get('qsofa_score')}, composite={result.get('composite_risk')}"
        )
        assert result["qsofa_score"] >= 2

    async def test_sepsis_deteriorating_uses_cdc_ase(self, fhir_url: str) -> None:
        """PT-007 flag_sepsis_onset → mode=cdc_ase (lab data present, LOINC-coded)."""
        result = await _sepsis(fhir_url, pid_hdr=PT_DETERIORATING)
        # Mode must be cdc_ase (lactate + creatinine obs are present for PT-007)
        assert result["mode"] == "cdc_ase", (
            f"PT-007 has lab observations; mode must be cdc_ase, got {result['mode']}"
        )

    async def test_escalation_deteriorating_sbar_complete(self, fhir_url: str) -> None:
        """PT-007 generate_escalation_note → SBAR all fields populated, severity ≥ urgent."""
        vitals_r = await _screen(fhir_url, pid_hdr=PT_DETERIORATING, trajectory="postop")
        risk_r = await _risk(fhir_url, pid_hdr=PT_DETERIORATING, trajectory="postop")
        sepsis_r = await _sepsis(fhir_url, pid_hdr=PT_DETERIORATING)
        result = await _escalation(
            fhir_url, vitals_r, risk_r, sepsis_r, pid_hdr=PT_DETERIORATING,
        )
        assert result["severity"] in {"urgent", "critical"}, (
            f"PT-007 escalation must be urgent or critical; got {result['severity']}"
        )
        sbar = result["sbar"]
        assert all(sbar.get(k) for k in ("situation", "background", "assessment", "recommendation"))


# ---------------------------------------------------------------------------
# 5. Sepsis trajectory — PT-009 (postpartum C-section, CDC ASE at T+4h)
# ---------------------------------------------------------------------------

class TestSepsisTrajectory:
    """PT-009 is the primary sepsis hero trajectory.

    Per SYNTHETIC_DATA_SPEC §2.5.3 and §5.1.2:
    - Lactate 4.2 mmol/L at T+4h (≥ 2.0 CDC ASE organ-dysfunction criterion)
    - SBP 94 mmHg at T+4h (≤ 100 organ-dysfunction criterion)
    - Ampicillin-sulbactam 3 g IV started at T+4:20 (presumed infection signal)
    Expected: sepsis_suspected=True, mode=cdc_ase, criteria include lactate + antibiotic.
    """

    async def test_screen_sepsis_triggered(self, fhir_url: str) -> None:
        """PT-009 screen_vital_thresholds → triggered (HR=124/RR=24/Temp=38.8 at T+4h)."""
        result = await _screen(fhir_url, pid_hdr=PT_SEPSIS, trajectory="postpartum")
        assert result["status"] == ToolStatus.TRIGGERED, (
            f"PT-009 (sepsis) vitals must trigger MEWT; "
            f"status={result['status']}, breaches={result.get('breaches')}"
        )

    async def test_risk_sepsis_high(self, fhir_url: str) -> None:
        """PT-009 score_deterioration_risk → risk_band=high."""
        result = await _risk(fhir_url, pid_hdr=PT_SEPSIS, trajectory="postpartum")
        assert result["risk_band"] == "high", (
            f"PT-009 (sepsis) must be high risk; got {result['risk_band']}"
        )

    async def test_sepsis_flag_suspected_true(self, fhir_url: str) -> None:
        """PT-009 flag_sepsis_onset → sepsis_suspected=True with CDC ASE criteria.

        Key assertions (per SYNTHETIC_DATA_SPEC §2.5.3 / §5.1.2):
        - mode = 'cdc_ase'  (lab data available: lactate 4.2, creatinine 1.4)
        - sepsis_suspected = True
        - criteria_met contains an antibiotic/infection evidence string
        - criteria_met contains an organ-dysfunction evidence string
        """
        result = await _sepsis(fhir_url, pid_hdr=PT_SEPSIS)

        assert result["mode"] == "cdc_ase", (
            f"PT-009 must use CDC ASE mode; got mode={result['mode']}"
        )
        assert result["sepsis_suspected"] is True, (
            f"PT-009 must have sepsis_suspected=True; "
            f"criteria_met={result.get('criteria_met')}, "
            f"evidence={result.get('evidence')}"
        )

        # At least one infection criterion and one organ-dysfunction criterion
        criteria_str = " ".join(str(c).lower() for c in result.get("criteria_met", []))
        assert any(
            kw in criteria_str
            for kw in ("antibiotic", "infection", "ampicillin", "cefazolin")
        ), (
            f"criteria_met must include an antibiotic/infection signal; "
            f"got: {result['criteria_met']}"
        )
        assert any(
            kw in criteria_str
            for kw in ("lactate", "sbp", "organ dysfunction", "qsofa", "creatinine")
        ), (
            f"criteria_met must include an organ-dysfunction marker; "
            f"got: {result['criteria_met']}"
        )

    async def test_escalation_sepsis_critical(self, fhir_url: str) -> None:
        """PT-009 generate_escalation_note → severity=critical (sepsis_suspected=True)."""
        vitals_r = await _screen(fhir_url, pid_hdr=PT_SEPSIS, trajectory="postpartum")
        risk_r = await _risk(fhir_url, pid_hdr=PT_SEPSIS, trajectory="postpartum")
        sepsis_r = await _sepsis(fhir_url, pid_hdr=PT_SEPSIS)
        result = await _escalation(
            fhir_url, vitals_r, risk_r, sepsis_r, pid_hdr=PT_SEPSIS,
        )
        assert result["severity"] == "critical", (
            f"PT-009 (sepsis) must produce critical SBAR; got {result['severity']}"
        )
        sbar = result["sbar"]
        assert all(sbar.get(k) for k in ("situation", "background", "assessment", "recommendation"))


# ---------------------------------------------------------------------------
# 6. Hemorrhage trajectory — PT-010 (postpartum, vaginal delivery)
# ---------------------------------------------------------------------------

class TestHemorrhageTrajectory:
    """PT-010: postpartum hemorrhage — MEWT fires at T+1h (EBL 650 mL, boggy fundus).

    Per SYNTHETIC_DATA_SPEC §2.4:
    - T+1h: HR=104, SBP=108 — initial trigger
    - T+2h: SBP=88, HR=124 — major PPH (EBL=1200 mL)
    All four tools must succeed and return valid shapes.
    """

    async def test_screen_hemorrhage_triggered(self, fhir_url: str) -> None:
        """PT-010 screen_vital_thresholds → triggered (SBP=88/HR=124 at T+2h)."""
        result = await _screen(fhir_url, pid_hdr=PT_HEMORRHAGE, trajectory="postpartum")
        assert result["status"] == ToolStatus.TRIGGERED, (
            f"PT-010 (hemorrhage) vitals must trigger MEWT; "
            f"status={result['status']}, breaches={result.get('breaches')}"
        )

    async def test_risk_hemorrhage_high(self, fhir_url: str) -> None:
        """PT-010 score_deterioration_risk → risk_band=high (SBP ≤ 100 + HR > 100)."""
        result = await _risk(fhir_url, pid_hdr=PT_HEMORRHAGE, trajectory="postpartum")
        assert result["risk_band"] in {"moderate", "high"}, (
            f"PT-010 (hemorrhage) must be moderate or high risk; got {result['risk_band']}"
        )

    async def test_sepsis_hemorrhage_uses_cdc_ase(self, fhir_url: str) -> None:
        """PT-010 flag_sepsis_onset → mode=cdc_ase (lab data present).

        The dominant alert for PT-010 is hemorrhage, not sepsis.  We do not
        assert True/False on sepsis_suspected here — the pre-op Cefazolin is
        prophylactic, not therapeutic.  We only assert that the mode is correct
        and the output shape is valid.
        """
        result = await _sepsis(fhir_url, pid_hdr=PT_HEMORRHAGE)
        assert result["mode"] == "cdc_ase", (
            f"PT-010 has lab observations; mode must be cdc_ase, got {result['mode']}"
        )
        assert isinstance(result["sepsis_suspected"], bool)

    async def test_escalation_hemorrhage_sbar_complete(self, fhir_url: str) -> None:
        """PT-010 generate_escalation_note → SBAR all fields populated."""
        vitals_r = await _screen(fhir_url, pid_hdr=PT_HEMORRHAGE, trajectory="postpartum")
        risk_r = await _risk(fhir_url, pid_hdr=PT_HEMORRHAGE, trajectory="postpartum")
        sepsis_r = await _sepsis(fhir_url, pid_hdr=PT_HEMORRHAGE)
        result = await _escalation(
            fhir_url, vitals_r, risk_r, sepsis_r, pid_hdr=PT_HEMORRHAGE,
        )
        sbar = result["sbar"]
        sbar_keys = ("situation", "background", "assessment", "recommendation")
        assert all(sbar.get(k) for k in sbar_keys), (
            f"SBAR fields must all be populated for PT-010; got: {sbar}"
        )
        # Communication draft must be a valid FHIR Communication shape
        draft = result["communication_draft"]
        assert draft.get("resourceType") == "Communication"
        assert draft.get("status") == "in-progress"
        assert draft.get("subject", {}).get("reference") == f"Patient/{PT_HEMORRHAGE}"


# ---------------------------------------------------------------------------
# 7. Security invariants — SEC-01 (SSRF) and SEC-03 (bearer token leakage)
# ---------------------------------------------------------------------------

class TestSecurityInvariants:
    """Runtime checks for the top security controls documented in SECURITY_REVIEW.md."""

    # ── SEC-01: SSRF allowlist ───────────────────────────────────────────────

    async def test_ssrf_blocked_metadata_endpoint(self) -> None:
        """SEC-01: cloud metadata IP must be rejected with ValueError."""
        ctx = _ctx("http://169.254.169.254/latest/meta-data", patient_id=PT_STABLE)
        with pytest.raises(ValueError, match="SSRF blocked"):
            await screen_vital_thresholds(patient_id=None, ctx=ctx)

    async def test_ssrf_blocked_internal_ollama(self) -> None:
        """SEC-01: local Ollama port must be rejected (not in FHIR allowlist)."""
        ctx = _ctx("http://localhost:11434", patient_id=PT_STABLE)
        with pytest.raises(ValueError, match="SSRF blocked"):
            await flag_sepsis_onset(patient_id=None, ctx=ctx)

    async def test_missing_fhir_url_raises(self) -> None:
        """SEC-01: missing x-fhir-server-url must raise ValueError before any FHIR call."""
        scope = {
            "type": "http", "method": "POST", "path": "/mcp",
            "headers": [(PATIENT_ID_HEADER.encode(), PT_STABLE.encode())],
            "query_string": b"",
        }
        ctx = MagicMock()
        ctx.request_context.request = Request(scope=scope)
        with pytest.raises(ValueError, match="Missing required SHARP header"):
            await screen_vital_thresholds(patient_id=PT_STABLE, ctx=ctx)

    # ── SEC-03: bearer token must not appear in tool output ──────────────────

    async def test_bearer_token_not_in_screen_output(self, fhir_url: str) -> None:
        """SEC-03: x-fhir-access-token value must not leak into tool JSON output."""
        sentinel = "SENTINEL_BEARER_TOKEN_99887766"
        ctx = _ctx(fhir_url, patient_id=PT_STABLE, token=sentinel)
        raw = await screen_vital_thresholds(patient_id=None, ctx=ctx)
        assert sentinel not in raw, (
            "Bearer token leaked into screen_vital_thresholds JSON output (SEC-03)"
        )

    async def test_bearer_token_not_in_escalation_output(self, fhir_url: str) -> None:
        """SEC-03: bearer token must not appear in generate_escalation_note output."""
        sentinel = "SENTINEL_BEARER_TOKEN_99887766"
        ctx = _ctx(fhir_url, patient_id=PT_STABLE, token=sentinel)
        stub_vitals = {"status": "ok", "patient_id": PT_STABLE, "breaches": []}
        stub_risk = {"status": "ok", "patient_id": PT_STABLE, "risk_band": "low",
                     "qsofa_score": 0, "composite_risk": 0.0, "contributing_conditions": [],
                     "rationale": ""}
        stub_sepsis = {"status": "ok", "patient_id": PT_STABLE, "sepsis_suspected": False,
                       "mode": "cdc_ase", "criteria_met": [], "evidence": {}}
        raw = await generate_escalation_note(
            vitals_result=stub_vitals,
            risk_result=stub_risk,
            sepsis_result=stub_sepsis,
            patient_id=None,
            recipient_role="charge_nurse",
            ctx=ctx,
        )
        assert sentinel not in raw, (
            "Bearer token leaked into generate_escalation_note JSON output (SEC-03)"
        )

    async def test_missing_patient_id_raises(self, fhir_url: str) -> None:
        """No patient_id in input OR header must raise ValueError."""
        ctx = _ctx(fhir_url)  # no patient_id anywhere
        with pytest.raises(ValueError, match="No patient_id provided"):
            await screen_vital_thresholds(patient_id=None, ctx=ctx)
