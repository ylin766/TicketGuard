"""Tests for the grey-zone escalation decision in the security orchestrator."""

from backend.features.security.orchestrator import (
    GREY_ZONE_DANGER_MAX,
    GREY_ZONE_SAFE_MIN,
    is_grey_zone,
)


def _gz(result, score):
    return is_grey_zone(result, score)


def test_unavailable_pipeline_escalates():
    assert _gz({"status": "unavailable"}, 50) is True


def test_very_low_score_is_conclusive_danger():
    # Multi-source consensus of danger -> judge it directly, no agent needed.
    assert _gz({"status": "ok", "flagged": True}, 10) is False
    assert _gz({"status": "ok", "flagged": True}, GREY_ZONE_DANGER_MAX - 1) is False


def test_high_score_is_conclusive_safe():
    # Only a clearly-safe score skips the agent — even if a lone source flagged it.
    assert _gz({"status": "ok", "flagged": False}, 90) is False
    assert _gz({"status": "ok", "flagged": True}, 85) is False


def test_uncertain_middle_is_grey_zone():
    # Includes a lone false-positive flag (e.g. legit marketplace) -> agent confirms.
    assert _gz({"status": "ok", "flagged": True}, 77) is True
    assert _gz({"status": "ok", "flagged": False}, 55) is True
    assert _gz({"status": "ok", "flagged": False}, 25) is True


def test_grey_zone_boundaries():
    assert _gz({"status": "ok", "flagged": False}, GREY_ZONE_DANGER_MAX) is True
    assert _gz({"status": "ok", "flagged": False}, GREY_ZONE_DANGER_MAX - 1) is False
    assert _gz({"status": "ok", "flagged": False}, GREY_ZONE_SAFE_MIN) is False
    assert _gz({"status": "ok", "flagged": False}, GREY_ZONE_SAFE_MIN - 1) is True
