"""Resolve which skill an inbound A2A message is asking for.

Two strategies, in order:
  1. Metadata-first: ``message.metadata`` may carry an explicit skill hint
     under one of ``skill_id`` / ``skillId`` / ``skill``. Empirically only
     verified locally — Prompt Opinion may inject this in v2.
  2. Keyword-on-text: scan ``message.parts[*].text`` (case-insensitive)
     for clinical keywords, falling back to ``vigil.screen_vitals``.

Reference: docs/A2A_REFACTOR_AUDIT.md §"Proposed skill surface".
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class SkillId(StrEnum):
    """Public skill IDs declared on the agent card.

    Dot-separated, vendor-prefixed. Slice B owns the agent card text;
    these constants are the source of truth that both halves dispatch on.
    """

    SCREEN_VITALS = "vigil.screen_vitals"
    SCORE_RISK = "vigil.score_risk"
    CHECK_SEPSIS = "vigil.check_sepsis"
    DRAFT_SBAR = "vigil.draft_sbar"
    START_WATCHING = "vigil.start_watching"
    ASSESS_AKI = "vigil.assess_postop_aki"
    SCORE_NEWS2 = "vigil.score_news2"
    ASSESS_PPH = "vigil.assess_pph_severity"


# Keyword map, ordered by specificity. First hit wins.
# Tuple form (tokens, skill) so the iteration order is stable and explicit.
#
# Order matters! More-specific tokens must come first, otherwise the
# generic ``score``/``risk`` keywords would steal NEWS2 and PPH prompts.
_KEYWORDS: list[tuple[tuple[str, ...], SkillId]] = [
    (("sbar", "escalate", "handoff", "draft"), SkillId.DRAFT_SBAR),
    (
        ("pph", "postpartum hemorrhage", "postpartum hemmorhage",
         "blood loss", "hemorrhage", "haemorrhage", "cmqcc"),
        SkillId.ASSESS_PPH,
    ),
    (
        ("aki", "kidney injury", "creatinine", "kdigo", "renal injury"),
        SkillId.ASSESS_AKI,
    ),
    (("news2", "news 2", "early warning"), SkillId.SCORE_NEWS2),
    (("sepsis", "septic", "infection"), SkillId.CHECK_SEPSIS),
    (("risk", "qsofa", "score"), SkillId.SCORE_RISK),
    (("watch", "monitor", "polling"), SkillId.START_WATCHING),
    (("vital", "screen", "mewt"), SkillId.SCREEN_VITALS),
]

DEFAULT_SKILL = SkillId.SCREEN_VITALS


def _from_metadata(metadata: dict[str, Any] | None) -> SkillId | None:
    """Look for an explicit skill hint. Tolerate skill / skill_id / skillId.

    Returns ``None`` if metadata is missing, not a dict, or the value is
    not a recognised SkillId.
    """
    if not isinstance(metadata, dict):
        return None
    for key in ("skill_id", "skillId", "skill"):
        value = metadata.get(key)
        if isinstance(value, str):
            try:
                return SkillId(value)
            except ValueError:
                continue
    return None


def _from_text(text: str) -> SkillId | None:
    """First keyword match wins, case-insensitive substring match."""
    t = text.lower()
    for tokens, skill in _KEYWORDS:
        if any(tok in t for tok in tokens):
            return skill
    return None


def _part_text(part: Any) -> str:
    """Pull the ``.text`` field out of a Part, tolerating two SDK shapes.

    The a2a-sdk ``Part`` is a RootModel wrapping ``TextPart | FilePart |
    DataPart`` — text lives at ``part.root.text``. But test fixtures and
    some ad-hoc constructions hand us a ``TextPart`` directly, in which
    case ``.text`` is on the object itself. Try both.
    """
    direct = getattr(part, "text", None)
    if isinstance(direct, str):
        return direct
    root = getattr(part, "root", None)
    nested = getattr(root, "text", None)
    if isinstance(nested, str):
        return nested
    return ""


def resolve_skill(message: Any) -> SkillId:
    """Resolve the skill from an a2a-sdk ``Message`` object.

    Defensive against shape variation:
      - ``message.metadata``: ``dict | None``
      - ``message.parts``: list of TextPart-like objects with ``.text``
        (or ``.root.text`` on the wire-parsed RootModel form).
    """
    if message is None:
        return DEFAULT_SKILL
    md_hit = _from_metadata(getattr(message, "metadata", None))
    if md_hit is not None:
        return md_hit
    parts = getattr(message, "parts", None) or []
    text_blob = " ".join(_part_text(p) for p in parts)
    return _from_text(text_blob) or DEFAULT_SKILL
