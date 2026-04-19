"""Tests for backend.schemas — validates every pydantic model against
the example payloads from docs/API_CONTRACTS.md.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.schemas import (
    SBAR,
    AgentState,
    ApproveRequest,
    ApproveResponse,
    EscalationInput,
    EscalationOutput,
    FhirContext,
    FlagSepsisInput,
    RiskScoreOutput,
    ScoreRiskInput,
    ScreenVitalsInput,
    ScreenVitalsOutput,
    SepsisFlagOutput,
    ToolError,
    ToolStatus,
    VitalBreach,
)

# ---------------------------------------------------------------------------
# ToolStatus enum
# ---------------------------------------------------------------------------


class TestToolStatus:
    def test_values(self):
        assert ToolStatus.OK == "ok"
        assert ToolStatus.TRIGGERED == "triggered"
        assert ToolStatus.BAD_INPUT == "bad_input"
        assert ToolStatus.FHIR_UNAVAILABLE == "fhir_error"
        assert ToolStatus.FHIR_NOT_FOUND == "fhir_not_found"
        assert ToolStatus.LLM_UNAVAILABLE == "llm_error"

    def test_count(self):
        assert len(ToolStatus) == 6

    def test_is_str(self):
        assert isinstance(ToolStatus.OK, str)


# ---------------------------------------------------------------------------
# AgentState enum
# ---------------------------------------------------------------------------


class TestAgentState:
    def test_values(self):
        expected = [
            "IDLE", "POLLING", "SCREENING", "RISK_SCORING",
            "SEPSIS_CHECK", "ESCALATING", "AWAITING_REVIEW",
        ]
        assert [s.value for s in AgentState] == expected

    def test_count(self):
        assert len(AgentState) == 7


# ---------------------------------------------------------------------------
# ToolError
# ---------------------------------------------------------------------------


class TestToolError:
    def test_api_contracts_example(self):
        err = ToolError(
            status="fhir_error",
            message="HAPI FHIR server unreachable",
            detail={"http_status": 503},
        )
        assert err.status == ToolStatus.FHIR_UNAVAILABLE
        assert err.detail == {"http_status": 503}

    def test_detail_optional(self):
        err = ToolError(status="bad_input", message="missing field")
        assert err.detail is None

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ToolError(status="ok", message="ok", bogus="x")


# ---------------------------------------------------------------------------
# FhirContext dataclass
# ---------------------------------------------------------------------------


class TestFhirContext:
    def test_full(self):
        ctx = FhirContext(
            url="http://localhost:8080/fhir",
            token="Bearer xyz",
            patient_id="patient-42",
        )
        assert ctx.url == "http://localhost:8080/fhir"
        assert ctx.token == "Bearer xyz"
        assert ctx.patient_id == "patient-42"

    def test_defaults(self):
        ctx = FhirContext(url="http://localhost:8080/fhir")
        assert ctx.token is None
        assert ctx.patient_id is None


# ---------------------------------------------------------------------------
# 1.1 screen_vital_thresholds
# ---------------------------------------------------------------------------


class TestScreenVitalsInput:
    def test_defaults(self):
        inp = ScreenVitalsInput()
        assert inp.patient_id is None
        assert inp.lookback_minutes == 240
        assert inp.trajectory == "postop"

    def test_api_contracts_example(self):
        inp = ScreenVitalsInput(
            patient_id="patient-42",
            lookback_minutes=240,
            trajectory="postop",
        )
        assert inp.patient_id == "patient-42"

    def test_postpartum_trajectory(self):
        inp = ScreenVitalsInput(trajectory="postpartum")
        assert inp.trajectory == "postpartum"

    def test_rejects_invalid_trajectory(self):
        with pytest.raises(ValidationError):
            ScreenVitalsInput(trajectory="invalid")

    def test_lookback_min_boundary(self):
        with pytest.raises(ValidationError):
            ScreenVitalsInput(lookback_minutes=14)

    def test_lookback_max_boundary(self):
        with pytest.raises(ValidationError):
            ScreenVitalsInput(lookback_minutes=1441)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ScreenVitalsInput(extra="nope")


class TestVitalBreach:
    def test_api_contracts_example(self):
        breach = VitalBreach(
            loinc="8480-6",
            label="SBP",
            value=86.0,
            unit="mm[Hg]",
            threshold="<90",
            severity="red",
            observed_at="2026-04-15T11:48:00Z",
        )
        assert breach.loinc == "8480-6"
        assert breach.severity == "red"
        assert isinstance(breach.observed_at, datetime)

    def test_rejects_invalid_severity(self):
        with pytest.raises(ValidationError):
            VitalBreach(
                loinc="8480-6", label="SBP", value=86.0,
                unit="mm[Hg]", threshold="<90", severity="green",
                observed_at="2026-04-15T11:48:00Z",
            )


class TestScreenVitalsOutput:
    def test_happy_path(self):
        out = ScreenVitalsOutput.model_validate({
            "status": "ok",
            "patient_id": "patient-42",
            "trajectory": "postop",
            "breaches": [],
            "scanned_count": 18,
            "window_start": "2026-04-15T08:00:00Z",
            "window_end": "2026-04-15T12:00:00Z",
        })
        assert out.status == ToolStatus.OK
        assert out.breaches == []
        assert out.scanned_count == 18

    def test_triggered_path(self):
        out = ScreenVitalsOutput.model_validate({
            "status": "triggered",
            "patient_id": "patient-42",
            "trajectory": "postop",
            "breaches": [
                {
                    "loinc": "8480-6", "label": "SBP",
                    "value": 86.0, "unit": "mm[Hg]",
                    "threshold": "<90", "severity": "red",
                    "observed_at": "2026-04-15T11:48:00Z",
                },
                {
                    "loinc": "8867-4", "label": "HR",
                    "value": 126.0, "unit": "/min",
                    "threshold": ">=120", "severity": "yellow",
                    "observed_at": "2026-04-15T11:48:00Z",
                },
            ],
            "scanned_count": 18,
            "window_start": "2026-04-15T08:00:00Z",
            "window_end": "2026-04-15T12:00:00Z",
        })
        assert out.status == ToolStatus.TRIGGERED
        assert len(out.breaches) == 2
        assert out.breaches[0].label == "SBP"
        assert out.breaches[1].severity == "yellow"

    def test_json_round_trip(self):
        out = ScreenVitalsOutput(
            status=ToolStatus.OK,
            patient_id="patient-42",
            trajectory="postop",
            breaches=[],
            scanned_count=0,
            window_start=datetime(2026, 4, 15, 8, tzinfo=UTC),
            window_end=datetime(2026, 4, 15, 12, tzinfo=UTC),
        )
        data = out.model_dump(mode="json")
        rebuilt = ScreenVitalsOutput.model_validate(data)
        assert rebuilt == out

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ScreenVitalsOutput(
                status="ok", patient_id="p", trajectory="postop",
                breaches=[], scanned_count=0,
                window_start="2026-04-15T08:00:00Z",
                window_end="2026-04-15T12:00:00Z",
                bonus="bad",
            )


# ---------------------------------------------------------------------------
# 1.2 score_deterioration_risk
# ---------------------------------------------------------------------------


class TestScoreRiskInput:
    def test_defaults(self):
        inp = ScoreRiskInput()
        assert inp.window_hours == 6
        assert inp.trajectory == "postop"

    def test_api_contracts_example(self):
        inp = ScoreRiskInput(
            patient_id="patient-42",
            window_hours=6,
            trajectory="postop",
        )
        assert inp.patient_id == "patient-42"

    def test_window_hours_boundaries(self):
        with pytest.raises(ValidationError):
            ScoreRiskInput(window_hours=0)
        with pytest.raises(ValidationError):
            ScoreRiskInput(window_hours=49)


class TestRiskScoreOutput:
    def test_happy_path(self):
        out = RiskScoreOutput.model_validate({
            "status": "ok",
            "patient_id": "patient-42",
            "qsofa_score": 0,
            "qsofa_components": {
                "rr_ge_22": False,
                "sbp_le_100": False,
                "altered_mental": False,
            },
            "composite_risk": 0.12,
            "risk_band": "low",
            "rationale": "qSOFA=0; SBP stable; HR stable; no trend breach.",
            "contributing_conditions": [],
        })
        assert out.status == ToolStatus.OK
        assert out.qsofa_score == 0
        assert out.risk_band == "low"

    def test_triggered_path(self):
        out = RiskScoreOutput.model_validate({
            "status": "triggered",
            "patient_id": "patient-42",
            "qsofa_score": 2,
            "qsofa_components": {
                "rr_ge_22": True,
                "sbp_le_100": True,
                "altered_mental": False,
            },
            "composite_risk": 0.71,
            "risk_band": "high",
            "rationale": (
                "qSOFA=2 meets sepsis screen;"
                " SBP trending down 18 mmHg over 4h."
            ),
            "contributing_conditions": [
                "44054006 Type 2 diabetes",
            ],
        })
        assert out.status == ToolStatus.TRIGGERED
        assert out.qsofa_score == 2
        assert out.risk_band == "high"
        assert len(out.contributing_conditions) == 1

    def test_rejects_qsofa_out_of_range(self):
        base = {
            "status": "ok", "patient_id": "p",
            "qsofa_components": {}, "composite_risk": 0.1,
            "risk_band": "low", "rationale": "x",
            "contributing_conditions": [],
        }
        with pytest.raises(ValidationError):
            RiskScoreOutput.model_validate({**base, "qsofa_score": -1})
        with pytest.raises(ValidationError):
            RiskScoreOutput.model_validate({**base, "qsofa_score": 4})

    def test_rejects_composite_risk_out_of_range(self):
        base = {
            "status": "ok", "patient_id": "p", "qsofa_score": 0,
            "qsofa_components": {}, "risk_band": "low",
            "rationale": "x", "contributing_conditions": [],
        }
        with pytest.raises(ValidationError):
            RiskScoreOutput.model_validate({**base, "composite_risk": -0.1})
        with pytest.raises(ValidationError):
            RiskScoreOutput.model_validate({**base, "composite_risk": 1.1})

    def test_rejects_invalid_risk_band(self):
        with pytest.raises(ValidationError):
            RiskScoreOutput.model_validate({
                "status": "ok", "patient_id": "p", "qsofa_score": 0,
                "qsofa_components": {}, "composite_risk": 0.1,
                "risk_band": "extreme", "rationale": "x",
                "contributing_conditions": [],
            })


# ---------------------------------------------------------------------------
# 1.3 flag_sepsis_onset
# ---------------------------------------------------------------------------


class TestFlagSepsisInput:
    def test_defaults(self):
        inp = FlagSepsisInput()
        assert inp.evaluation_window_hours == 24

    def test_api_contracts_example(self):
        inp = FlagSepsisInput(
            patient_id="patient-42",
            evaluation_window_hours=24,
        )
        assert inp.patient_id == "patient-42"

    def test_window_boundaries(self):
        with pytest.raises(ValidationError):
            FlagSepsisInput(evaluation_window_hours=0)
        with pytest.raises(ValidationError):
            FlagSepsisInput(evaluation_window_hours=73)


class TestSepsisFlagOutput:
    def test_happy_path(self):
        out = SepsisFlagOutput.model_validate({
            "status": "ok",
            "patient_id": "patient-42",
            "sepsis_suspected": False,
            "mode": "cdc_ase",
            "criteria_met": [],
            "onset_estimate": None,
            "evidence": {"lactate_value": 1.1, "abx_code": None},
        })
        assert out.status == ToolStatus.OK
        assert out.sepsis_suspected is False
        assert out.onset_estimate is None

    def test_triggered_path(self):
        out = SepsisFlagOutput.model_validate({
            "status": "triggered",
            "patient_id": "patient-42",
            "sepsis_suspected": True,
            "mode": "cdc_ase",
            "criteria_met": [
                "presumed infection (antibiotic started)",
                "organ dysfunction: lactate 2.4 mmol/L",
                "organ dysfunction: SBP 86 mmHg",
            ],
            "onset_estimate": "2026-04-15T10:30:00Z",
            "evidence": {
                "lactate_loinc": "2524-7",
                "lactate_value": 2.4,
                "abx_code": "J01DD04",
                "sbp": 86,
            },
        })
        assert out.status == ToolStatus.TRIGGERED
        assert out.sepsis_suspected is True
        assert len(out.criteria_met) == 3
        assert isinstance(out.onset_estimate, datetime)

    def test_sirs_fallback_mode(self):
        out = SepsisFlagOutput(
            status=ToolStatus.TRIGGERED,
            patient_id="patient-42",
            sepsis_suspected=True,
            mode="sirs_fallback",
            criteria_met=["temp > 38.3"],
            onset_estimate=None,
            evidence={"temp": 38.5},
        )
        assert out.mode == "sirs_fallback"

    def test_rejects_invalid_mode(self):
        with pytest.raises(ValidationError):
            SepsisFlagOutput(
                status="ok", patient_id="p",
                sepsis_suspected=False, mode="unknown",
                criteria_met=[], onset_estimate=None, evidence={},
            )


# ---------------------------------------------------------------------------
# 1.4 generate_escalation_note
# ---------------------------------------------------------------------------


class TestSBAR:
    def test_api_contracts_example(self):
        sbar = SBAR(
            situation=(
                "Post-op day 1 patient with SBP 86"
                " and qSOFA 2; sepsis suspected."
            ),
            background=(
                "42yo s/p laparoscopic cholecystectomy"
                " 18h ago; Hx T2DM."
            ),
            assessment=(
                "Meets CDC ASE: lactate 2.4, SBP 86,"
                " abx started. High deterioration risk."
            ),
            recommendation=(
                "Activate rapid response, draw repeat"
                " lactate, bolus 500ml NS, notify attending."
            ),
        )
        assert "SBP 86" in sbar.situation
        assert "T2DM" in sbar.background

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            SBAR(
                situation="S", background="B",
                assessment="A", recommendation="R",
                extra="no",
            )


class TestEscalationInput:
    def test_api_contracts_example(self):
        inp = EscalationInput(
            patient_id="patient-42",
            vitals_result={
                "status": "triggered",
                "breaches": [{"label": "SBP", "value": 86.0}],
            },
            risk_result={
                "status": "ok",
                "qsofa_score": 2,
                "risk_band": "high",
            },
            sepsis_result={
                "status": "triggered",
                "sepsis_suspected": True,
                "mode": "cdc_ase",
            },
            recipient_role="rapid_response",
        )
        assert inp.recipient_role == "rapid_response"
        assert inp.vitals_result["status"] == "triggered"

    def test_recipient_role_default(self):
        inp = EscalationInput(
            vitals_result={}, risk_result={}, sepsis_result={},
        )
        assert inp.recipient_role == "charge_nurse"

    def test_rejects_invalid_recipient_role(self):
        with pytest.raises(ValidationError):
            EscalationInput(
                vitals_result={}, risk_result={},
                sepsis_result={}, recipient_role="janitor",
            )


class TestEscalationOutput:
    def test_api_contracts_example(self):
        out = EscalationOutput.model_validate({
            "status": "ok",
            "patient_id": "patient-42",
            "sbar": {
                "situation": (
                    "Post-op day 1 patient with SBP 86"
                    " and qSOFA 2; sepsis suspected."
                ),
                "background": (
                    "42yo s/p laparoscopic"
                    " cholecystectomy 18h ago; Hx T2DM."
                ),
                "assessment": (
                    "Meets CDC ASE: lactate 2.4, SBP 86,"
                    " abx started. High deterioration risk."
                ),
                "recommendation": (
                    "Activate rapid response, draw repeat"
                    " lactate, bolus 500ml NS,"
                    " notify attending."
                ),
            },
            "narrative": "S: ... B: ... A: ... R: ...",
            "severity": "critical",
            "recipient_role": "rapid_response",
            "communication_draft": {
                "resourceType": "Communication",
                "status": "in-progress",
                "category": [{
                    "coding": [{
                        "system": (
                            "http://terminology.hl7.org"
                            "/CodeSystem/communication-category"
                        ),
                        "code": "alert",
                    }]
                }],
                "priority": "urgent",
                "subject": {"reference": "Patient/patient-42"},
                "encounter": {"reference": "Encounter/enc-77"},
                "sender": {
                    "reference": "Device/vigil-postop-sentinel",
                    "display": "Vigil Postop Sentinel",
                },
                "recipient": [{
                    "reference": "PractitionerRole/rapid-response",
                    "display": "Rapid Response Team",
                }],
                "payload": [{
                    "contentString": "S: ... B: ... A: ... R: ...",
                }],
            },
            "generated_at": "2026-04-15T12:01:10Z",
            "model_used": "ollama/llama3.1",
        })
        assert out.status == ToolStatus.OK
        assert out.severity == "critical"
        assert out.sbar.situation.startswith("Post-op")
        assert out.communication_draft["resourceType"] == "Communication"
        assert out.model_used == "ollama/llama3.1"

    def test_rejects_invalid_severity(self):
        with pytest.raises(ValidationError):
            EscalationOutput(
                status="ok", patient_id="p",
                sbar=SBAR(
                    situation="S", background="B",
                    assessment="A", recommendation="R",
                ),
                narrative="n", severity="warning",
                recipient_role="r",
                communication_draft={},
                generated_at="2026-04-15T12:01:10Z",
                model_used="m",
            )

    def test_json_round_trip(self):
        out = EscalationOutput(
            status=ToolStatus.OK,
            patient_id="patient-42",
            sbar=SBAR(
                situation="S", background="B",
                assessment="A", recommendation="R",
            ),
            narrative="narrative",
            severity="info",
            recipient_role="charge_nurse",
            communication_draft={"resourceType": "Communication"},
            generated_at=datetime(2026, 4, 15, 12, 1, 10, tzinfo=UTC),
            model_used="ollama/llama3.1",
        )
        data = out.model_dump(mode="json")
        rebuilt = EscalationOutput.model_validate(data)
        assert rebuilt == out


# ---------------------------------------------------------------------------
# 6.4 Approve endpoint
# ---------------------------------------------------------------------------


class TestApproveRequest:
    def test_api_contracts_example(self):
        req = ApproveRequest(
            clinician_id="prac-nurse-17",
            note="Acknowledged, RRT dispatched.",
        )
        assert req.clinician_id == "prac-nurse-17"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ApproveRequest(
                clinician_id="p", note="n", extra="x",
            )


class TestApproveResponse:
    def test_api_contracts_example(self):
        resp = ApproveResponse(
            alert_id="comm-884",
            status="completed",
            acknowledged_at="2026-04-15T12:03:44Z",
            audit_id="audit-56",
        )
        assert resp.alert_id == "comm-884"
        assert resp.status == "completed"
        assert isinstance(resp.acknowledged_at, datetime)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ApproveResponse(
                alert_id="a", status="s",
                acknowledged_at="2026-04-15T12:00:00Z",
                audit_id="x", bonus="no",
            )
