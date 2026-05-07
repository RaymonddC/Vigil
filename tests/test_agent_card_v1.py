"""Lock the A2A v1 wire shape served by the AgentCardV1 subclass.

The installed ``a2a-sdk`` is on the v0.3 schema; the subclass in
``backend/a2a_agent/agent_card_v1.py`` exists so the v1 nested forms
(``apiKeySecurityScheme.location``, ``supportedInterfaces`` with
``protocolBinding``/``protocolVersion``) round-trip through
``model_validate`` → ``model_dump(by_alias=True, exclude_none=True)``.

If the parent SDK is bumped to a v1-native release and these assertions
break, drop ``agent_card_v1.py`` and revert ``app.py`` to import
``AgentCard`` directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.a2a_agent.agent_card_v1 import AgentCardV1

CARD_PATH = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / "a2a_agent"
    / "agent_card.json"
)
EXPECTED_FHIR_EXT_URI = "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context"
EXPECTED_SKILL_IDS = {
    "vigil.screen_vitals",
    "vigil.score_risk",
    "vigil.check_sepsis",
    "vigil.draft_sbar",
    "vigil.start_watching",
    "vigil.assess_postop_aki",
    "vigil.score_news2",
    "vigil.assess_pph_severity",
    "vigil.flag_treatment_conflicts",
    "vigil.list_recent_alerts",
}


def _served_card() -> dict:
    raw = json.loads(CARD_PATH.read_text())
    card = AgentCardV1.model_validate(raw)
    return card.model_dump(by_alias=True, exclude_none=True)


def test_security_scheme_v1_nested_form_survives_round_trip() -> None:
    served = _served_card()
    inner = served["securitySchemes"]["apiKey"]["apiKeySecurityScheme"]
    assert inner["name"] == "X-API-Key"
    # v1 uses ``location``, not v0.3's ``in``. The subclass override is what
    # keeps the parent's discriminated SecurityScheme union from collapsing
    # this entry into MutualTLSSecurityScheme.
    assert inner["location"] == "header"
    assert "description" in inner


def test_supported_interfaces_v1_keys_survive_round_trip() -> None:
    served = _served_card()
    interfaces = served["supportedInterfaces"]
    assert len(interfaces) == 1, interfaces
    entry = interfaces[0]
    assert entry["url"] == "http://localhost:9000/a2a"
    assert entry["protocolBinding"] == "JSONRPC"
    assert entry["protocolVersion"] == "1.0"


def test_fhir_context_extension_uri_and_scopes_survive_round_trip() -> None:
    served = _served_card()
    ext = served["capabilities"]["extensions"][0]
    assert ext["uri"] == EXPECTED_FHIR_EXT_URI
    # extension-level required is False; per-scope flags live inside params.
    assert ext["required"] is False
    scopes = ext["params"]["scopes"]
    by_name = {s["name"]: s for s in scopes}
    assert by_name["patient/Patient.rs"]["required"] is True
    assert by_name["patient/Observation.rs"]["required"] is True
    assert by_name["patient/Condition.rs"]["required"] is True
    # MedicationRequest is intentionally optional — no `required` key.
    assert "required" not in by_name["patient/MedicationRequest.rs"]


def test_skill_set_matches_post_refactor_catalogue() -> None:
    served = _served_card()
    assert {s["id"] for s in served["skills"]} == EXPECTED_SKILL_IDS
    # Explicit count check guards against accidental drops on edits.
    assert len(served["skills"]) == 10


def test_capabilities_disable_streaming_and_state_history() -> None:
    served = _served_card()
    caps = served["capabilities"]
    assert caps["streaming"] is False
    assert caps["pushNotifications"] is False
    # v1 mandate: stateTransitionHistory MUST be false on the card.
    assert caps["stateTransitionHistory"] is False
