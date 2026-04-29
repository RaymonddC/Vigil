"""Unit tests for the treatment-conflict rule engine.

Each rule gets positive + negative + boundary coverage. Rules:

  1. NSAID + AKI                     — KDIGO 2012 §4.4.1, AGS Beers 2023.
  2. β-blocker + bradycardia/hypotension — ACC/AHA 2017.
  3. ACE-I/ARB + hyperkalemia        — KDIGO 2024 BP-in-CKD §4.3.
  4. Opioid + respiratory depression — ASPMN 2020 (Jungquist).
  5. Anticoagulant + Hgb drop        — ASH 2018 (Witt).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.criteria.treatment_conflicts import (
    ANTICOAGULANTS,
    BETA_BLOCKERS,
    NSAIDS,
    OPIOIDS,
    evaluate_treatment_conflicts,
)
from backend.fhir.models import (
    CategoryItem,
    CodeableConcept,
    Coding,
    MedicationAdministration,
    MedicationRequest,
    Observation,
    Quantity,
)

NOW = datetime.now(UTC)


def _obs(loinc: str, value: float, ts: datetime, category: str = "vital-signs") -> Observation:
    return Observation(
        resourceType="Observation",
        category=[CategoryItem(coding=[Coding(code=category)])],
        code=CodeableConcept(
            coding=[Coding(system="http://loinc.org", code=loinc)]
        ),
        valueQuantity=Quantity(value=value),
        effectiveDateTime=ts,
    )


def _admin(display: str, ts: datetime, status: str = "completed") -> MedicationAdministration:
    return MedicationAdministration(
        resourceType="MedicationAdministration",
        status=status,
        medicationCodeableConcept=CodeableConcept(
            coding=[Coding(display=display)]
        ),
        effectiveDateTime=ts,
    )


def _request(display: str, status: str = "active") -> MedicationRequest:
    return MedicationRequest(
        resourceType="MedicationRequest",
        status=status,
        intent="order",
        medicationCodeableConcept=CodeableConcept(
            coding=[Coding(display=display)]
        ),
        authoredOn=NOW - timedelta(hours=1),
    )


# ---------------------------------------------------------------------------
# Class-keyword sanity — guard against accidental drops.
# ---------------------------------------------------------------------------


class TestKeywordTables:
    def test_canonical_drugs_present(self) -> None:
        assert "ibuprofen" in NSAIDS
        assert "metoprolol" in BETA_BLOCKERS
        assert "morphine" in OPIOIDS
        assert "enoxaparin" in ANTICOAGULANTS


# ---------------------------------------------------------------------------
# Rule 1: NSAID + AKI
# ---------------------------------------------------------------------------


class TestNsaidAkiRule:
    def test_positive_critical_when_kdigo_stage_1_and_active_nsaid(self) -> None:
        report = evaluate_treatment_conflicts(
            observations=[],
            medication_administrations=[],
            medication_requests=[_request("Ibuprofen 600 mg po")],
            kdigo_stage=1,
            now=NOW,
        )
        assert any(c.rule_id == "nsaid_aki" for c in report.conflicts)
        c = next(c for c in report.conflicts if c.rule_id == "nsaid_aki")
        assert c.severity == "critical"
        assert "KDIGO" in c.citation_anchor
        assert "Beers" in c.citation_anchor
        assert "acetaminophen" in c.mitigation.lower()
        assert "acetaminophen" in c.safe_alternatives

    def test_positive_with_administration_in_window(self) -> None:
        report = evaluate_treatment_conflicts(
            observations=[],
            medication_administrations=[
                _admin("Ketorolac 30 mg IV", NOW - timedelta(hours=2)),
            ],
            medication_requests=[],
            kdigo_stage=2,
            now=NOW,
        )
        assert any(c.rule_id == "nsaid_aki" for c in report.conflicts)

    def test_negative_when_no_aki(self) -> None:
        """KDIGO stage 0 + active NSAID → no conflict."""
        report = evaluate_treatment_conflicts(
            observations=[],
            medication_administrations=[],
            medication_requests=[_request("Ibuprofen 600 mg po")],
            kdigo_stage=0,
            now=NOW,
        )
        assert not any(c.rule_id == "nsaid_aki" for c in report.conflicts)

    def test_boundary_kdigo_stage_1_fires(self) -> None:
        """Stage 1 is the boundary — must fire."""
        report = evaluate_treatment_conflicts(
            observations=[],
            medication_administrations=[],
            medication_requests=[_request("Naproxen 500 mg po")],
            kdigo_stage=1,
            now=NOW,
        )
        assert any(c.rule_id == "nsaid_aki" for c in report.conflicts)

    def test_negative_when_old_administration(self) -> None:
        """An NSAID administered >12h ago is no longer "active" for this rule."""
        report = evaluate_treatment_conflicts(
            observations=[],
            medication_administrations=[
                _admin(
                    "Ketorolac 30 mg IV",
                    NOW - timedelta(hours=20),
                ),
            ],
            medication_requests=[],
            kdigo_stage=2,
            now=NOW,
        )
        assert not any(c.rule_id == "nsaid_aki" for c in report.conflicts)


# ---------------------------------------------------------------------------
# Rule 2: β-blocker + bradycardia/hypotension
# ---------------------------------------------------------------------------


class TestBetaBlockerRule:
    def test_positive_warning_at_hr_54(self) -> None:
        """HR 54 < 55 — fires at warning severity (not <50)."""
        report = evaluate_treatment_conflicts(
            observations=[_obs("8867-4", 54.0, NOW - timedelta(minutes=2))],
            medication_administrations=[],
            medication_requests=[_request("Metoprolol 25 mg po bid")],
            now=NOW,
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "bblocker_brady_hypo"
        )
        assert c.severity == "warning"
        assert "HR 54" in c.physiology_summary

    def test_positive_critical_at_hr_48(self) -> None:
        """HR 48 < 50 — critical."""
        report = evaluate_treatment_conflicts(
            observations=[_obs("8867-4", 48.0, NOW - timedelta(minutes=2))],
            medication_administrations=[],
            medication_requests=[_request("Carvedilol 6.25 mg po bid")],
            now=NOW,
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "bblocker_brady_hypo"
        )
        assert c.severity == "critical"

    def test_positive_critical_at_sbp_84(self) -> None:
        """SBP 84 < 85 — critical even if HR normal."""
        report = evaluate_treatment_conflicts(
            observations=[_obs("8480-6", 84.0, NOW - timedelta(minutes=2))],
            medication_administrations=[],
            medication_requests=[_request("Atenolol 25 mg po qd")],
            now=NOW,
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "bblocker_brady_hypo"
        )
        assert c.severity == "critical"

    def test_negative_when_hr_55_sbp_90(self) -> None:
        """Boundary: HR 55 (NOT <55) and SBP 90 (NOT <90) → no fire."""
        report = evaluate_treatment_conflicts(
            observations=[
                _obs("8867-4", 55.0, NOW - timedelta(minutes=2)),
                _obs("8480-6", 90.0, NOW - timedelta(minutes=2)),
            ],
            medication_administrations=[],
            medication_requests=[_request("Metoprolol 25 mg po bid")],
            now=NOW,
        )
        assert not any(
            c.rule_id == "bblocker_brady_hypo" for c in report.conflicts
        )

    def test_negative_when_no_drug(self) -> None:
        """Bradycardia alone — no β-blocker, no fire."""
        report = evaluate_treatment_conflicts(
            observations=[_obs("8867-4", 40.0, NOW - timedelta(minutes=2))],
            medication_administrations=[],
            medication_requests=[],
            now=NOW,
        )
        assert not any(
            c.rule_id == "bblocker_brady_hypo" for c in report.conflicts
        )


# ---------------------------------------------------------------------------
# Rule 3: ACE-I/ARB + hyperkalemia
# ---------------------------------------------------------------------------


class TestAceArbHyperkalemiaRule:
    def test_positive_warning_at_k_5_5(self) -> None:
        """K+ 5.5 boundary, <6.0 → warning."""
        report = evaluate_treatment_conflicts(
            observations=[
                _obs("2823-3", 5.5, NOW - timedelta(minutes=2),
                     category="laboratory"),
            ],
            medication_administrations=[],
            medication_requests=[_request("Lisinopril 10 mg po qd")],
            now=NOW,
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "ace_arb_hyperk"
        )
        assert c.severity == "warning"
        assert "5.5" in c.physiology_summary

    def test_positive_critical_at_k_6_0(self) -> None:
        """K+ ≥6.0 → critical."""
        report = evaluate_treatment_conflicts(
            observations=[
                _obs("2823-3", 6.1, NOW - timedelta(minutes=2),
                     category="laboratory"),
            ],
            medication_administrations=[],
            medication_requests=[_request("Losartan 50 mg po qd")],
            now=NOW,
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "ace_arb_hyperk"
        )
        assert c.severity == "critical"

    def test_negative_when_k_below_5_5(self) -> None:
        """K+ 5.4 below trigger threshold → no fire."""
        report = evaluate_treatment_conflicts(
            observations=[
                _obs("2823-3", 5.4, NOW - timedelta(minutes=2),
                     category="laboratory"),
            ],
            medication_administrations=[],
            medication_requests=[_request("Enalapril 5 mg po bid")],
            now=NOW,
        )
        assert not any(
            c.rule_id == "ace_arb_hyperk" for c in report.conflicts
        )

    def test_negative_when_no_drug(self) -> None:
        report = evaluate_treatment_conflicts(
            observations=[
                _obs("2823-3", 6.5, NOW - timedelta(minutes=2),
                     category="laboratory"),
            ],
            medication_administrations=[],
            medication_requests=[],
            now=NOW,
        )
        assert not any(
            c.rule_id == "ace_arb_hyperk" for c in report.conflicts
        )


# ---------------------------------------------------------------------------
# Rule 4: Opioid + respiratory depression
# ---------------------------------------------------------------------------


class TestOpioidRespiratoryRule:
    def test_positive_critical_when_spo2_91_within_4h(self) -> None:
        report = evaluate_treatment_conflicts(
            observations=[_obs("59408-5", 91.0, NOW - timedelta(minutes=10))],
            medication_administrations=[
                _admin("Morphine 4 mg IV", NOW - timedelta(hours=1)),
            ],
            medication_requests=[],
            now=NOW,
        )
        c = next(
            c for c in report.conflicts
            if c.rule_id == "opioid_resp_depression"
        )
        assert c.severity == "critical"
        assert "ASPMN" in c.citation_anchor
        assert "naloxone" in c.mitigation.lower()

    def test_positive_when_rr_below_12(self) -> None:
        report = evaluate_treatment_conflicts(
            observations=[_obs("9279-1", 10.0, NOW - timedelta(minutes=10))],
            medication_administrations=[
                _admin("Hydromorphone 1 mg IV", NOW - timedelta(hours=2)),
            ],
            medication_requests=[],
            now=NOW,
        )
        assert any(
            c.rule_id == "opioid_resp_depression" for c in report.conflicts
        )

    def test_negative_when_spo2_92_boundary_not_below(self) -> None:
        """SpO2 92 is NOT <92 — must not fire (boundary case)."""
        report = evaluate_treatment_conflicts(
            observations=[_obs("59408-5", 92.0, NOW - timedelta(minutes=10))],
            medication_administrations=[
                _admin("Fentanyl 50 mcg IV", NOW - timedelta(hours=1)),
            ],
            medication_requests=[],
            now=NOW,
        )
        assert not any(
            c.rule_id == "opioid_resp_depression" for c in report.conflicts
        )

    def test_negative_when_dose_outside_4h_window(self) -> None:
        """Opioid given 6h ago — outside the 4h rule window."""
        report = evaluate_treatment_conflicts(
            observations=[_obs("59408-5", 88.0, NOW - timedelta(minutes=10))],
            medication_administrations=[
                _admin("Morphine 4 mg IV", NOW - timedelta(hours=6)),
            ],
            medication_requests=[],
            now=NOW,
        )
        assert not any(
            c.rule_id == "opioid_resp_depression" for c in report.conflicts
        )

    def test_active_order_alone_fires_when_physio_bad(self) -> None:
        """Even without a recent admin, a queued order + bad physio fires —
        the whole point of this skill is to block the *next* dose."""
        report = evaluate_treatment_conflicts(
            observations=[_obs("9279-1", 10.0, NOW - timedelta(minutes=2))],
            medication_administrations=[],
            medication_requests=[
                _request("Oxycodone 5 mg po q4h prn"),
            ],
            now=NOW,
        )
        assert any(
            c.rule_id == "opioid_resp_depression" for c in report.conflicts
        )


# ---------------------------------------------------------------------------
# Rule 5: Anticoagulant + Hgb drop
# ---------------------------------------------------------------------------


class TestAnticoagHgbRule:
    def test_positive_warning_when_drop_2_g_dl(self) -> None:
        """Drop 2.0 g/dL boundary, current 10 → warning (not critical)."""
        observations = [
            _obs("718-7", 12.0, NOW - timedelta(days=1), category="laboratory"),
            _obs("718-7", 10.0, NOW - timedelta(minutes=10),
                 category="laboratory"),
        ]
        report = evaluate_treatment_conflicts(
            observations=observations,
            medication_administrations=[],
            medication_requests=[_request("Enoxaparin 40 mg subq")],
            now=NOW,
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "anticoag_hgb_drop"
        )
        assert c.severity == "warning"

    def test_positive_critical_when_drop_3_g_dl(self) -> None:
        observations = [
            _obs("718-7", 13.0, NOW - timedelta(days=1), category="laboratory"),
            _obs("718-7", 9.5, NOW - timedelta(minutes=10),
                 category="laboratory"),
        ]
        report = evaluate_treatment_conflicts(
            observations=observations,
            medication_administrations=[],
            medication_requests=[_request("Apixaban 5 mg po bid")],
            now=NOW,
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "anticoag_hgb_drop"
        )
        assert c.severity == "critical"
        assert "ASH 2018" in c.citation_anchor or "Witt" in c.citation_anchor

    def test_positive_critical_when_current_below_8(self) -> None:
        """Even at drop 2.0 (warning by drop), current<8 escalates to critical."""
        observations = [
            _obs("718-7", 9.5, NOW - timedelta(days=1), category="laboratory"),
            _obs("718-7", 7.5, NOW - timedelta(minutes=10),
                 category="laboratory"),
        ]
        report = evaluate_treatment_conflicts(
            observations=observations,
            medication_administrations=[],
            medication_requests=[_request("Warfarin 5 mg po")],
            now=NOW,
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "anticoag_hgb_drop"
        )
        assert c.severity == "critical"

    def test_negative_when_drop_below_2(self) -> None:
        """1.9 g/dL drop — under the 2.0 threshold."""
        observations = [
            _obs("718-7", 12.0, NOW - timedelta(days=1), category="laboratory"),
            _obs("718-7", 10.1, NOW - timedelta(minutes=10),
                 category="laboratory"),
        ]
        report = evaluate_treatment_conflicts(
            observations=observations,
            medication_administrations=[],
            medication_requests=[_request("Heparin 5000 units subq")],
            now=NOW,
        )
        assert not any(
            c.rule_id == "anticoag_hgb_drop" for c in report.conflicts
        )

    def test_negative_when_no_drug(self) -> None:
        observations = [
            _obs("718-7", 12.0, NOW - timedelta(days=1), category="laboratory"),
            _obs("718-7", 9.0, NOW - timedelta(minutes=10),
                 category="laboratory"),
        ]
        report = evaluate_treatment_conflicts(
            observations=observations,
            medication_administrations=[],
            medication_requests=[],
            now=NOW,
        )
        assert not any(
            c.rule_id == "anticoag_hgb_drop" for c in report.conflicts
        )


# ---------------------------------------------------------------------------
# Aggregate behaviour
# ---------------------------------------------------------------------------


class TestAggregate:
    def test_no_conflicts_returns_empty_report(self) -> None:
        report = evaluate_treatment_conflicts(
            observations=[],
            medication_administrations=[],
            medication_requests=[],
            kdigo_stage=0,
            now=NOW,
        )
        assert report.conflicts == []
        assert report.safe_alternatives == []

    def test_safe_alternatives_deduplicated(self) -> None:
        """Two rules naming acetaminophen must surface it once in the
        de-duplicated alternatives list."""
        observations = [
            _obs("718-7", 12.0, NOW - timedelta(days=1), category="laboratory"),
            _obs("718-7", 9.5, NOW - timedelta(minutes=10),
                 category="laboratory"),
        ]
        report = evaluate_treatment_conflicts(
            observations=observations,
            medication_administrations=[],
            medication_requests=[
                _request("Ibuprofen 600 mg po"),
                _request("Enoxaparin 40 mg subq"),
            ],
            kdigo_stage=1,
            now=NOW,
        )
        assert report.safe_alternatives.count("acetaminophen") <= 1

    def test_evidence_block_includes_kdigo_and_lookup_values(self) -> None:
        report = evaluate_treatment_conflicts(
            observations=[_obs("8867-4", 42.0, NOW - timedelta(minutes=2))],
            medication_administrations=[],
            medication_requests=[_request("Metoprolol 25 mg po bid")],
            kdigo_stage=1,
            now=NOW,
        )
        assert report.evidence["kdigo_stage"] == 1
        assert report.evidence["hr"] == 42.0


# ---------------------------------------------------------------------------
# Synthetic-bundle integration — verify that the data fixtures shipped in
# data/patients/PT-XXX.json (loaded via synthetic_fallback) actually trip
# the rules they were designed to demo.  Each test loads the bundle, runs
# the rule engine end-to-end against it, and asserts the rule fires with
# the expected severity / drug / physiology summary.  Regenerating
# bundles via ``python data/seed_hapi.py --generate-only`` must keep all
# of these green.
#
# Cross-references commit 834e520 which introduced the 5-rule engine —
# these tests guarantee the demo coverage that commit promised.
# ---------------------------------------------------------------------------


class TestSyntheticBundleFixtures:
    def _evaluate_bundle(self, patient_id: str):
        """Run the rule engine against the bundled trajectory for ``patient_id``.

        Imports synthetic_fallback lazily so the heavier dependency graph
        only loads when these integration tests run.  Resets the module
        cache to keep tests independent of run order.
        """
        from backend.mcp_server import synthetic_fallback as sf
        from backend.mcp_server.tools.flag_treatment_conflicts import (
            _resolve_kdigo_stage,
        )

        sf.reset_for_tests()
        vitals = sf.get_synthetic_observations(
            category="vital-signs", patient_id=patient_id,
        )
        labs = sf.get_synthetic_observations(
            category="laboratory", patient_id=patient_id,
        )
        observations = vitals + labs
        admins = sf.get_synthetic_medication_administrations(
            patient_id=patient_id,
        )
        requests = sf.get_synthetic_medication_requests(
            patient_id=patient_id,
        )
        kdigo_stage = _resolve_kdigo_stage(observations)
        return evaluate_treatment_conflicts(
            observations=observations,
            medication_administrations=admins,
            medication_requests=requests,
            kdigo_stage=kdigo_stage,
            now=datetime.now(UTC),
        )

    # PT-008 (sepsis trajectory) — should fire BOTH NSAID/AKI and
    # ACE-I/hyperK rules. Demonstrates the multi-rule output shape.
    def test_pt008_fires_nsaid_aki(self) -> None:
        report = self._evaluate_bundle("PT-008")
        rule_ids = [c.rule_id for c in report.conflicts]
        assert "nsaid_aki" in rule_ids, (
            f"NSAID/AKI rule must fire on PT-008; got {rule_ids}"
        )
        c = next(c for c in report.conflicts if c.rule_id == "nsaid_aki")
        assert c.severity == "critical"
        assert "ibuprofen" in c.drug_display.lower()
        assert "KDIGO" in c.citation_anchor

    def test_pt008_fires_ace_arb_hyperkalemia(self) -> None:
        """K+ 5.7 + active lisinopril order → warning conflict."""
        report = self._evaluate_bundle("PT-008")
        rule_ids = [c.rule_id for c in report.conflicts]
        assert "ace_arb_hyperk" in rule_ids, (
            f"ACE-I/hyperK rule must fire on PT-008; got {rule_ids}"
        )
        c = next(c for c in report.conflicts if c.rule_id == "ace_arb_hyperk")
        # 5.7 mmol/L is below the 6.0 critical cutoff → warning.
        assert c.severity == "warning"
        assert "lisinopril" in c.drug_display.lower()
        assert "5.7" in c.physiology_summary
        assert "KDIGO" in c.citation_anchor

    def test_pt008_multi_rule_includes_safe_alternatives(self) -> None:
        report = self._evaluate_bundle("PT-008")
        # At least the two we just asserted plus dedup'd alternatives.
        assert len(report.conflicts) >= 2
        # Both NSAID and ACE-I rules contribute to safe_alternatives.
        # CCB (calcium-channel blocker) comes from the ACE-I rule,
        # acetaminophen from the NSAID rule.
        alts = [a.lower() for a in report.safe_alternatives]
        assert any("acetaminophen" in a for a in alts)
        assert any("calcium" in a for a in alts)

    # PT-007 (deteriorating trajectory) — should fire BOTH opioid and
    # β-blocker rules. The β-blocker ride-along is the new fixture; the
    # opioid rule was already wired by commit 834e520's predecessor.
    def test_pt007_fires_opioid_resp_depression(self) -> None:
        report = self._evaluate_bundle("PT-007")
        rule_ids = [c.rule_id for c in report.conflicts]
        assert "opioid_resp_depression" in rule_ids, (
            f"Opioid rule must fire on PT-007; got {rule_ids}"
        )
        c = next(
            c for c in report.conflicts
            if c.rule_id == "opioid_resp_depression"
        )
        assert c.severity == "critical"
        assert "morphine" in c.drug_display.lower()

    def test_pt007_fires_beta_blocker_hypotension(self) -> None:
        """SBP 88 < 90 + active metoprolol order → warning conflict.

        Severity stays at warning because SBP is ≥85 and HR is normal —
        if either drops further the rule should escalate to critical.
        """
        report = self._evaluate_bundle("PT-007")
        rule_ids = [c.rule_id for c in report.conflicts]
        assert "bblocker_brady_hypo" in rule_ids, (
            f"β-blocker rule must fire on PT-007; got {rule_ids}"
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "bblocker_brady_hypo"
        )
        assert c.severity == "warning"
        assert "metoprolol" in c.drug_display.lower()
        assert "SBP 88" in c.physiology_summary
        assert "ACC/AHA" in c.citation_anchor

    # PT-010 (PPH trajectory) — anchors the anticoag/Hgb-drop rule.
    def test_pt010_fires_anticoag_hgb_drop(self) -> None:
        report = self._evaluate_bundle("PT-010")
        rule_ids = [c.rule_id for c in report.conflicts]
        assert "anticoag_hgb_drop" in rule_ids, (
            f"Anticoag rule must fire on PT-010; got {rule_ids}"
        )
        c = next(
            c for c in report.conflicts if c.rule_id == "anticoag_hgb_drop"
        )
        assert "enoxaparin" in c.drug_display.lower()
        assert "ASH 2018" in c.citation_anchor or "Witt" in c.citation_anchor
