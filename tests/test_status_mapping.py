from app.status.mapping import (
    STATUS_EMOJI,
    STATUS_LABEL_RU,
    BusinessStatus,
    map_tracker_status,
)


def test_known_codes_map_to_business_statuses():
    assert map_tracker_status("on_track") == BusinessStatus.ON_TRACK
    assert map_tracker_status("at_risk") == BusinessStatus.AT_RISK
    assert map_tracker_status("blocked") == BusinessStatus.BLOCKED


def test_case_and_whitespace_insensitive():
    assert map_tracker_status("  On_Track  ") == BusinessStatus.ON_TRACK
    assert map_tracker_status("AT_RISK") == BusinessStatus.AT_RISK


def test_unknown_and_draft_fall_back_to_unknown():
    assert map_tracker_status("draft") == BusinessStatus.UNKNOWN
    assert map_tracker_status("in_progress") == BusinessStatus.UNKNOWN
    assert map_tracker_status("launched") == BusinessStatus.UNKNOWN
    assert map_tracker_status(None) == BusinessStatus.UNKNOWN
    assert map_tracker_status("") == BusinessStatus.UNKNOWN


def test_every_business_status_has_emoji_and_label():
    for status in BusinessStatus:
        assert status in STATUS_EMOJI
        assert status in STATUS_LABEL_RU
