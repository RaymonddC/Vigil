"""Routing tests for the three new A2A skills.

Covers:
  - vigil.assess_postop_aki  (keyword: aki, kidney injury, creatinine)
  - vigil.score_news2        (keyword: news2)
  - vigil.assess_pph_severity (keyword: pph, hemorrhage)

Mirrors the keyword-routing checks in ``test_a2a_skill_dispatch``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.a2a_agent.skill_router import SkillId, resolve_skill


def _msg(text: str, metadata: dict | None = None) -> MagicMock:
    msg = MagicMock()
    part = MagicMock()
    part.text = text
    msg.parts = [part]
    msg.metadata = metadata
    return msg


class TestKeywordRouting:
    def test_aki_keyword_routes_to_aki(self) -> None:
        assert (
            resolve_skill(_msg("assess this patient for AKI"))
            is SkillId.ASSESS_AKI
        )

    def test_kidney_injury_routes_to_aki(self) -> None:
        assert (
            resolve_skill(_msg("Is there any acute kidney injury?"))
            is SkillId.ASSESS_AKI
        )

    def test_creatinine_routes_to_aki(self) -> None:
        assert (
            resolve_skill(_msg("walk me through the creatinine trend"))
            is SkillId.ASSESS_AKI
        )

    def test_news2_routes_to_news2(self) -> None:
        assert resolve_skill(_msg("compute NEWS2")) is SkillId.SCORE_NEWS2

    def test_pph_routes_to_pph(self) -> None:
        assert (
            resolve_skill(_msg("stage this PPH"))
            is SkillId.ASSESS_PPH
        )

    def test_hemorrhage_routes_to_pph(self) -> None:
        assert (
            resolve_skill(_msg("postpartum hemorrhage assessment please"))
            is SkillId.ASSESS_PPH
        )


class TestMetadataRouting:
    def test_metadata_aki_skill_id_overrides_text(self) -> None:
        msg = _msg(
            "screen vitals please",
            metadata={"skill_id": SkillId.ASSESS_AKI.value},
        )
        assert resolve_skill(msg) is SkillId.ASSESS_AKI

    def test_metadata_news2_skill_id_wins(self) -> None:
        msg = _msg(
            "screen vitals",
            metadata={"skill_id": SkillId.SCORE_NEWS2.value},
        )
        assert resolve_skill(msg) is SkillId.SCORE_NEWS2

    def test_metadata_pph_skill_id_wins(self) -> None:
        msg = _msg(
            "anything",
            metadata={"skill_id": SkillId.ASSESS_PPH.value},
        )
        assert resolve_skill(msg) is SkillId.ASSESS_PPH


class TestSpecificityOrdering:
    """The new keywords are placed BEFORE the generic ``risk``/``score``
    family so they win even when both terms appear in the prompt."""

    def test_news2_wins_over_score(self) -> None:
        # Prompt contains both "score" and "news2"; news2 must win.
        assert (
            resolve_skill(_msg("score the news2 for me"))
            is SkillId.SCORE_NEWS2
        )

    def test_aki_wins_over_risk(self) -> None:
        assert (
            resolve_skill(_msg("what's the AKI risk band"))
            is SkillId.ASSESS_AKI
        )
