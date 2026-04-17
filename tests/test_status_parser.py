from datetime import UTC, datetime, timedelta

from app.status.parser import (
    has_weekly_status_tag,
    parse_weekly_status,
    pick_latest_weekly_status,
)

NOW = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)


def test_tag_detection():
    assert has_weekly_status_tag("#WeeklyStatus")
    assert has_weekly_status_tag("some text\n#weeklystatus\nmore")
    assert not has_weekly_status_tag("#Weekly or status")
    assert not has_weekly_status_tag("no tags here")


def test_parse_full_template():
    body = (
        "#WeeklyStatus\n"
        "Comments: всё идёт по плану,\n"
        "- пункт один\n"
        "- пункт два\n"
        "DL по решению: 25.04.2026\n"
    )
    ws = parse_weekly_status(body, NOW)
    assert ws is not None
    assert "всё идёт по плану" in ws.comments
    assert "пункт один" in ws.comments
    assert "пункт два" in ws.comments
    assert ws.deadline == "25.04.2026"


def test_parse_no_tag_returns_none():
    assert parse_weekly_status("Comments: nope", NOW) is None
    assert parse_weekly_status("", NOW) is None


def test_parse_only_tag_and_comments():
    body = "#WeeklyStatus\nComments: риск по интеграции"
    ws = parse_weekly_status(body, NOW)
    assert ws is not None
    assert ws.comments == "риск по интеграции"
    assert ws.deadline is None


def test_parse_preserves_formatting():
    body = "#WeeklyStatus\nComments:\n- A\n- B\n\nextra"
    ws = parse_weekly_status(body, NOW)
    assert ws is not None
    assert "- A" in ws.comments
    assert "- B" in ws.comments


def test_freshness():
    fresh = parse_weekly_status("#WeeklyStatus\nComments: x", NOW - timedelta(days=3))
    stale = parse_weekly_status("#WeeklyStatus\nComments: x", NOW - timedelta(days=10))
    assert fresh is not None and fresh.is_fresh(NOW, 6)
    assert stale is not None and not stale.is_fresh(NOW, 6)


def test_pick_latest_among_many():
    older = ("#WeeklyStatus\nComments: old", NOW - timedelta(days=5))
    newer = ("#WeeklyStatus\nComments: new", NOW - timedelta(days=1))
    irrelevant = ("just a comment", NOW)
    latest = pick_latest_weekly_status([older, newer, irrelevant])
    assert latest is not None
    assert latest.comments == "new"


def test_pick_latest_returns_none_when_no_tagged():
    latest = pick_latest_weekly_status([("random", NOW), ("more", NOW)])
    assert latest is None
