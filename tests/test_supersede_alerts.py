"""Tests: enqueue_alert supersedes prior open alerts, keeping the queue clean.

After each agent tick, the sentinel calls enqueue_alert for every triggered
patient.  Without supersede logic, the review queue accumulates N near-identical
alerts after N ticks on the same patient.  These tests verify that:

  * enqueue_alert atomically supersedes prior in-progress rows before inserting
    the new one (at most one in-progress alert per patient at any time).
  * supersede_prior_alerts works as a standalone call (for testing / admin).
  * count_superseded_alerts returns the running tally.
  * list_pending_alerts never surfaces superseded rows.
  * Alerts for other patients are never affected.
"""

from __future__ import annotations

import backend.api.review_queue as rq
import pytest
from backend.api.review_queue import (
    count_superseded_alerts,
    count_unread_alerts,
    enqueue_alert,
    get_alert,
    list_pending_alerts,
    supersede_prior_alerts,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect the review queue to a fresh temp SQLite DB for each test."""
    db_path = tmp_path / "test_supersede.db"
    monkeypatch.setattr(rq, "DB_PATH", db_path)
    rq.init_db()


def _enqueue(patient_id: str = "PT-007", severity: str = "critical") -> str:
    return enqueue_alert(
        patient_id=patient_id,
        severity=severity,
        sbar={
            "situation": "Deteriorating vitals",
            "background": "48h post-op",
            "assessment": "Probable sepsis",
            "recommendation": "Activate RRT",
        },
        narrative="Patient deteriorating",
        recipient_role="charge_nurse",
        model_used="test-model",
        communication_draft={"resourceType": "Communication", "status": "in-progress"},
    )


# ---------------------------------------------------------------------------
# supersede_prior_alerts (standalone)
# ---------------------------------------------------------------------------


def test_supersede_prior_alerts_marks_in_progress_as_superseded():
    """supersede_prior_alerts flips an in-progress alert to superseded."""
    id1 = _enqueue()
    assert get_alert(id1)["status"] == "in-progress"

    count = supersede_prior_alerts("PT-007")

    assert count == 1
    assert get_alert(id1)["status"] == "superseded"


def test_supersede_prior_alerts_returns_zero_when_none_open():
    """supersede_prior_alerts returns 0 when there are no open alerts."""
    count = supersede_prior_alerts("PT-007")
    assert count == 0


def test_supersede_prior_alerts_does_not_touch_other_patients():
    """supersede_prior_alerts for one patient leaves other patients' alerts alone."""
    id_007 = _enqueue("PT-007")
    id_008 = _enqueue("PT-008")

    supersede_prior_alerts("PT-007")

    assert get_alert(id_007)["status"] == "superseded"
    assert get_alert(id_008)["status"] == "in-progress"


# ---------------------------------------------------------------------------
# enqueue_alert auto-supersede on re-tick
# ---------------------------------------------------------------------------


def test_second_enqueue_supersedes_first():
    """Second tick: old alert flipped to superseded, new one in-progress."""
    id1 = _enqueue("PT-007")
    id2 = _enqueue("PT-007")

    assert get_alert(id1)["status"] == "superseded", "prior alert must be superseded"
    assert get_alert(id2)["status"] == "in-progress", "new alert must be in-progress"


def test_three_ticks_only_one_in_progress():
    """After three ticks on the same patient, exactly one alert is in-progress."""
    _enqueue("PT-007")
    _enqueue("PT-007")
    _enqueue("PT-007")

    pending = list_pending_alerts()
    pt007 = [a for a in pending if a["patient_id"] == "PT-007"]
    assert len(pt007) == 1
    assert pt007[0]["status"] == "in-progress"


def test_enqueue_does_not_supersede_completed_alerts():
    """enqueue_alert should not touch already-completed alerts for the patient."""
    from backend.api.review_queue import approve_alert, claim_alert_for_writing

    id1 = _enqueue("PT-007")
    claim_alert_for_writing(id1)
    approve_alert(id1, "prac-1", "approved", "audit-1")
    assert get_alert(id1)["status"] == "completed"

    # Second tick should not touch the completed alert
    id2 = _enqueue("PT-007")
    assert get_alert(id1)["status"] == "completed", "completed alert must be untouched"
    assert get_alert(id2)["status"] == "in-progress"


# ---------------------------------------------------------------------------
# count_superseded_alerts
# ---------------------------------------------------------------------------


def test_count_superseded_starts_at_zero():
    """No superseded alerts until a second tick fires."""
    _enqueue("PT-007")
    assert count_superseded_alerts("PT-007") == 0


def test_count_superseded_increments_per_retick():
    """count_superseded_alerts tracks the cumulative tally of replaced alerts."""
    _enqueue("PT-007")
    assert count_superseded_alerts("PT-007") == 0

    _enqueue("PT-007")
    assert count_superseded_alerts("PT-007") == 1

    _enqueue("PT-007")
    assert count_superseded_alerts("PT-007") == 2


# ---------------------------------------------------------------------------
# count_unread_alerts stays at 1 after multiple ticks
# ---------------------------------------------------------------------------


def test_count_unread_stays_one_after_retick():
    """count_unread_alerts never exceeds 1 for a patient with multiple ticks."""
    _enqueue("PT-007")
    _enqueue("PT-007")
    _enqueue("PT-007")

    assert count_unread_alerts("PT-007") == 1


# ---------------------------------------------------------------------------
# list_pending_alerts never surfaces superseded rows
# ---------------------------------------------------------------------------


def test_list_pending_excludes_superseded():
    """list_pending_alerts only returns in-progress rows."""
    _enqueue("PT-007")
    _enqueue("PT-007")  # supersedes the first

    pending = list_pending_alerts()
    assert all(a["status"] == "in-progress" for a in pending)
    assert sum(1 for a in pending if a["patient_id"] == "PT-007") == 1


def test_list_pending_multiple_patients_each_get_one():
    """Each patient has at most one in-progress alert regardless of tick count."""
    _enqueue("PT-007")
    _enqueue("PT-007")
    _enqueue("PT-008")
    _enqueue("PT-008")
    _enqueue("PT-008")

    pending = list_pending_alerts()
    patient_ids = [a["patient_id"] for a in pending]
    assert patient_ids.count("PT-007") == 1
    assert patient_ids.count("PT-008") == 1
