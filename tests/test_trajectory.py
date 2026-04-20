"""Tests for `_derive_trajectory` (FIX 3 / C3).

Seed spec: PT-009 (chorioamnionitis + gestational DM) and PT-010
(placenta accreta + prior c-section + pre-eclampsia) must report
``postpartum``.  Everyone else falls through to ``postop``.
"""

from __future__ import annotations

from backend.api.routes.patients import _derive_trajectory
from backend.fhir.models import CodeableConcept, Coding, Condition


def _cond(code: str) -> Condition:
    return Condition(code=CodeableConcept(coding=[Coding(code=code)]))


class TestDeriveTrajectory:
    def test_cesarean_section_is_postpartum(self) -> None:
        assert _derive_trajectory([_cond("11466000")]) == "postpartum"

    def test_normal_delivery_is_postpartum(self) -> None:
        assert _derive_trajectory([_cond("3950001")]) == "postpartum"

    def test_chorioamnionitis_is_postpartum(self) -> None:
        # PT-009 signal — sepsis hero case
        assert _derive_trajectory([_cond("11612004")]) == "postpartum"

    def test_placenta_accreta_is_postpartum(self) -> None:
        # PT-010 signal — pph hero case
        assert _derive_trajectory([_cond("58532003")]) == "postpartum"

    def test_pt010_mixed_codes(self) -> None:
        # Placenta accreta + prior c-section + pre-eclampsia all match
        conds = [_cond("58532003"), _cond("200737006"), _cond("398254007")]
        assert _derive_trajectory(conds) == "postpartum"

    def test_non_obstetric_is_postop(self) -> None:
        # PT-001 — essential hypertension
        assert _derive_trajectory([_cond("59621000")]) == "postop"

    def test_empty_conditions_is_postop(self) -> None:
        # PT-003 ships no conditions
        assert _derive_trajectory([]) == "postop"

    def test_condition_without_code_ignored(self) -> None:
        cond = Condition(code=None)
        assert _derive_trajectory([cond]) == "postop"
