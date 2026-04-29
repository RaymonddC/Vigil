"""Routing + dispatch tests for the vigil.flag_treatment_conflicts skill.

Covers:
  - Keyword routing for "safe to give" / "drug interaction" / "med safety"
    / "treatment conflict" prompts.
  - Metadata-routing override.
  - Specificity ordering vs the generic risk/score family.
  - End-to-end dispatch through the executor — assert the right MCP tool
    is invoked and chat text formats the conflict row.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from a2a.types import TaskState

from backend.a2a_agent.sentinel import PostopSentinelExecutor
from backend.a2a_agent.skill_router import SkillId, resolve_skill

PATIENT_ID = "PT-008"
FHIR_URL = "http://localhost:8080/fhir"


def _msg(text: str, metadata: dict | None = None) -> MagicMock:
    msg = MagicMock()
    part = MagicMock()
    part.text = text
    msg.parts = [part]
    msg.metadata = metadata
    return msg


def _make_message(
    text: str = "",
    metadata: dict | None = None,
    fhir_metadata: dict | None = None,
) -> MagicMock:
    msg = MagicMock()
    part = MagicMock()
    part.text = text
    msg.parts = [part]
    combined: dict = {}
    if fhir_metadata is not None:
        combined.update(fhir_metadata)
    if metadata:
        combined.update(metadata)
    msg.metadata = combined or None
    return msg


def _fhir_metadata(patient_id: str = PATIENT_ID) -> dict:
    return {
        "fhir-context": {
            "fhirUrl": FHIR_URL,
            "fhirToken": None,
            "patientId": patient_id,
        }
    }


def _make_context(message: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.task_id = "task-1"
    ctx.context_id = "ctx-1"
    ctx.message = message
    return ctx


def _make_event_queue() -> MagicMock:
    eq = MagicMock()
    eq.enqueue_event = AsyncMock()
    return eq


def _final_text(event_queue: MagicMock) -> str:
    task = event_queue.enqueue_event.call_args_list[-1].args[0]
    return task.status.message.parts[0].root.text


def _mcp_text(payload: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "isError": False,
    }


# ---------------------------------------------------------------------------
# Keyword routing
# ---------------------------------------------------------------------------


class TestKeywordRouting:
    def test_safe_to_give_routes(self) -> None:
        assert (
            resolve_skill(_msg("Is it safe to give ibuprofen here?"))
            is SkillId.FLAG_TREATMENT_CONFLICTS
        )

    def test_can_i_order_routes(self) -> None:
        assert (
            resolve_skill(_msg("Can I order metoprolol for this patient?"))
            is SkillId.FLAG_TREATMENT_CONFLICTS
        )

    def test_drug_interaction_routes(self) -> None:
        assert (
            resolve_skill(_msg("any drug interaction with current meds?"))
            is SkillId.FLAG_TREATMENT_CONFLICTS
        )

    def test_med_safety_routes(self) -> None:
        assert (
            resolve_skill(_msg("run a med safety check"))
            is SkillId.FLAG_TREATMENT_CONFLICTS
        )

    def test_treatment_conflict_routes(self) -> None:
        assert (
            resolve_skill(_msg("any treatment conflict?"))
            is SkillId.FLAG_TREATMENT_CONFLICTS
        )

    def test_contraindication_routes(self) -> None:
        assert (
            resolve_skill(_msg("contraindication concerns?"))
            is SkillId.FLAG_TREATMENT_CONFLICTS
        )


# ---------------------------------------------------------------------------
# Natural chat phrasings — verified live as the dominant pattern other PO
# agents emit. Pre-fix these fell through to screen_vitals; post-fix they
# must land on flag_treatment_conflicts via either the new "safe for"/"ok
# for" keyword extensions or the drug+verb fallback.
# ---------------------------------------------------------------------------


class TestRoutingNaturalPhrasings:
    @pytest.mark.parametrize(
        "prompt",
        [
            "Is lisinopril safe for PT-008?",
            "Is metoprolol safe for PT-007?",
            "Is morphine safe for PT-007?",
            "Is enoxaparin safe for PT-010?",
            "Is ibuprofen ok for PT-008?",
            "Is ketorolac okay for PT-008?",
            "Is celecoxib appropriate for PT-008?",
            "any conflict starting warfarin?",
            "any contraindication for atenolol?",
        ],
    )
    def test_natural_phrasing_routes_to_flag_treatment_conflicts(
        self, prompt: str
    ) -> None:
        assert (
            resolve_skill(_msg(prompt))
            is SkillId.FLAG_TREATMENT_CONFLICTS
        )

    @pytest.mark.parametrize(
        "prompt, expected",
        [
            ("Screen this patient's vitals", SkillId.SCREEN_VITALS),
            ("What's the qSOFA?", SkillId.SCORE_RISK),
        ],
    )
    def test_adjacent_skills_unaffected(
        self, prompt: str, expected: SkillId
    ) -> None:
        # Regression guard: the new keyword list / drug-verb fallback must
        # not bleed into vitals or risk-score routing.
        assert resolve_skill(_msg(prompt)) is expected


# ---------------------------------------------------------------------------
# Specificity ordering — must beat the generic risk/score keyword family.
# ---------------------------------------------------------------------------


class TestSpecificityOrdering:
    def test_safety_wins_over_risk_word(self) -> None:
        # "risk" alone would route to SCORE_RISK; "drug interaction" must win.
        assert (
            resolve_skill(_msg("any drug interaction risk here?"))
            is SkillId.FLAG_TREATMENT_CONFLICTS
        )

    def test_score_alone_still_routes_to_score_risk(self) -> None:
        # Sanity: ensure we didn't accidentally steal the generic
        # "score" keyword.
        assert resolve_skill(_msg("score the risk")) is SkillId.SCORE_RISK


# ---------------------------------------------------------------------------
# Metadata routing
# ---------------------------------------------------------------------------


class TestMetadataRouting:
    def test_metadata_skill_id_wins_over_text(self) -> None:
        msg = _msg(
            "screen vitals please",
            metadata={"skill_id": SkillId.FLAG_TREATMENT_CONFLICTS.value},
        )
        assert resolve_skill(msg) is SkillId.FLAG_TREATMENT_CONFLICTS


# ---------------------------------------------------------------------------
# End-to-end dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_calls_mcp_tool_and_renders_conflict(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "triggered",
                    "patient_id": PATIENT_ID,
                    "conflicts": [
                        {
                            "rule_id": "nsaid_aki",
                            "severity": "critical",
                            "drug_class": "NSAID",
                            "drug_display": "ibuprofen 600 mg po q6h prn",
                            "physiology_summary": (
                                "KDIGO stage 2 AKI present"
                            ),
                            "citation_anchor": (
                                "KDIGO 2012 §4.4.1; AGS Beers 2023"
                            ),
                            "mitigation": (
                                "Consider acetaminophen, gabapentin, "
                                "or regional/local analgesia."
                            ),
                            "safe_alternatives": [
                                "acetaminophen",
                                "gabapentin",
                            ],
                        }
                    ],
                    "safe_alternatives": [
                        "acetaminophen",
                        "gabapentin",
                    ],
                    "evidence": {"kdigo_stage": 2},
                    "data_source": "fhir",
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="is it safe to give ibuprofen here?",
                fhir_metadata=_fhir_metadata(),
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        mcp.call_tool.assert_awaited_once()
        assert (
            mcp.call_tool.await_args.args[0] == "flag_treatment_conflicts"
        )

        text = _final_text(event_queue)
        assert "Treatment safety scan" in text
        assert "NSAID" in text
        assert "critical" in text
        assert "KDIGO" in text
        assert "acetaminophen" in text

        task = event_queue.enqueue_event.call_args_list[-1].args[0]
        assert task.status.state is TaskState.completed

    @pytest.mark.asyncio
    async def test_no_conflicts_renders_friendly_clear_message(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "ok",
                    "patient_id": PATIENT_ID,
                    "conflicts": [],
                    "safe_alternatives": [],
                    "evidence": {"kdigo_stage": 0},
                    "data_source": "fhir",
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="any treatment conflict to worry about?",
                fhir_metadata=_fhir_metadata(),
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        text = _final_text(event_queue)
        assert "no conflicts detected" in text.lower()

    @pytest.mark.asyncio
    async def test_synthetic_disclosure_prefixed(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "triggered",
                    "patient_id": PATIENT_ID,
                    "conflicts": [
                        {
                            "rule_id": "nsaid_aki",
                            "severity": "critical",
                            "drug_class": "NSAID",
                            "drug_display": "ibuprofen",
                            "physiology_summary": "KDIGO stage 2",
                            "citation_anchor": "KDIGO 2012",
                            "mitigation": "switch to acetaminophen",
                            "safe_alternatives": ["acetaminophen"],
                        }
                    ],
                    "safe_alternatives": ["acetaminophen"],
                    "evidence": {"kdigo_stage": 2},
                    "data_source": "synthetic_demo",
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="med safety check please",
                fhir_metadata=_fhir_metadata(),
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        text = _final_text(event_queue)
        assert (
            "demo trajectory" in text.lower() or "synthetic" in text.lower()
        )
        # Result still rendered.
        assert "NSAID" in text
