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

import re
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
    FLAG_TREATMENT_CONFLICTS = "vigil.flag_treatment_conflicts"
    LIST_RECENT_ALERTS = "vigil.list_recent_alerts"
    TICK_NOW = "vigil.tick_now"


# Keyword map, ordered by specificity. First hit wins.
# Tuple form (tokens, skill) so the iteration order is stable and explicit.
#
# Order matters! More-specific tokens must come first, otherwise the
# generic ``score``/``risk`` keywords would steal NEWS2 and PPH prompts.
_KEYWORDS: list[tuple[tuple[str, ...], SkillId]] = [
    # Background-loop alert query — must come BEFORE single-skill keywords
    # so phrases like "show recent alerts" / "list watched patients" don't
    # leak into screen_vitals or check_sepsis. Multi-word phrases only;
    # bare "alert" stays unmatched so "any sepsis alert?" still routes
    # to CHECK_SEPSIS via its own keywords.
    (
        ("recent alerts", "list alerts", "show alerts", "pending alerts",
         "background alerts", "watched patients", "what's been flagged",
         "whats been flagged", "what has been flagged",
         "any patients flagged", "anyone flagged"),
        SkillId.LIST_RECENT_ALERTS,
    ),
    # Demo trigger — invoke the autonomous cycle synchronously so judges
    # don't have to wait POLL_INTERVAL_SEC for the first tick. Multi-word
    # phrases only so bare "tick" / "now" stay unmatched.
    (
        ("tick now", "run a tick", "run the loop", "trigger tick",
         "force tick", "run cycle now", "run a cycle"),
        SkillId.TICK_NOW,
    ),
    (("sbar", "escalate", "handoff", "draft"), SkillId.DRAFT_SBAR),
    # Treatment-conflict skill — must come BEFORE the generic
    # ``risk``/``score`` family, because prompts like "is it safe to
    # give X" or "any drug interaction risk" otherwise leak to
    # SCORE_RISK. Phrases are intentionally specific to the
    # order-writing/safety question — not just any "med" mention.
    # Natural chat phrasings ("Is <drug> safe for <patient>?", "ok for",
    # "any conflict") are added alongside the original imperative forms;
    # paired with the drug+verb fallback below to keep med-safety prompts
    # out of the screen_vitals default.
    (
        ("safe to give", "can i order", "can i give", "ok to order",
         "drug interaction", "med safety", "medication safety",
         "treatment conflict", "treatment conflicts",
         "drug conflict", "drug-vs", "contraindication",
         "contraindicated",
         "safe for", "ok for", "okay for", "appropriate for",
         "any conflict", "any contraindication"),
        SkillId.FLAG_TREATMENT_CONFLICTS,
    ),
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


# Drug-name catch-all: if the prompt names a drug from the rule table AND
# uses a safety-question verb (safe / ok / give / start / order / appropriate
# / administer / prescribe), route to flag_treatment_conflicts. Runs only
# after the primary keyword scan returns no hit, so we never override a
# more-specific skill match. Word boundaries via \b avoid false positives
# (e.g. "ok" inside other tokens). Drug list mirrors backend.criteria.med_rules.
_DRUG_NAMES: tuple[str, ...] = (
    "ibuprofen", "ketorolac", "naproxen", "celecoxib", "diclofenac",
    "meloxicam", "aspirin",
    "metoprolol", "atenolol", "propranolol", "carvedilol", "bisoprolol",
    "esmolol", "labetalol",
    "lisinopril", "enalapril", "ramipril", "losartan", "valsartan",
    "irbesartan", "candesartan", "captopril",
    "morphine", "oxycodone", "hydrocodone", "fentanyl", "hydromorphone",
    "codeine", "tramadol", "buprenorphine",
    "heparin", "enoxaparin", "warfarin", "apixaban", "rivaroxaban",
    "dabigatran", "edoxaban", "fondaparinux",
)

_DRUG_NAME_RE = re.compile(
    r"\b(" + "|".join(_DRUG_NAMES) + r")\b", re.IGNORECASE
)
_SAFETY_VERB_RE = re.compile(
    r"\b(safe|ok|okay|give|start|order|appropriate|administer|prescribe)\b",
    re.IGNORECASE,
)


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


def _drug_verb_fallback(text: str) -> SkillId | None:
    """Catch natural med-safety phrasings the keyword list didn't cover.

    Triggers only when no canonical keyword matched, so it never overrides
    a more-specific skill (sepsis / AKI / NEWS2 / etc.).
    """
    if not _DRUG_NAME_RE.search(text):
        return None
    if not _SAFETY_VERB_RE.search(text):
        return None
    return SkillId.FLAG_TREATMENT_CONFLICTS


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
    return (
        _from_text(text_blob)
        or _drug_verb_fallback(text_blob.lower())
        or DEFAULT_SKILL
    )
