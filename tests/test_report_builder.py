from datetime import UTC, datetime

from app.report.builder import (
    ProjectSummary,
    render_help,
    render_list,
    render_report,
    render_risk,
)
from app.status.mapping import BusinessStatus
from app.status.parser import WeeklyStatus
from app.tracker.models import Portfolio, Project, TrackerUser

NOW = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)


def _project(
    *,
    pid: str = "proj-1",
    short_id: int = 7,
    summary: str = "Bot",
    lead_display: str | None = "Иван Иванов",
) -> Project:
    lead = TrackerUser(id="u1", display=lead_display) if lead_display is not None else None
    return Project(
        id=pid,
        short_id=short_id,
        summary=summary,
        description=None,
        entity_status="in_progress",
        parent_portfolio_id="pf1",
        parent_portfolio_display="Команда А",
        lead=lead,
        start=None,
        end=None,
        updated_at=None,
        tags=(),
    )


def _summary(
    *,
    project: Project | None = None,
    weekly_status: WeeklyStatus | None = None,
    business_status: BusinessStatus = BusinessStatus.ON_TRACK,
    is_stale: bool = False,
    project_url: str = "https://tracker.yandex.ru/projects/7",
) -> ProjectSummary:
    return ProjectSummary(
        project=project or _project(),
        weekly_status=weekly_status,
        business_status=business_status,
        is_stale=is_stale,
        project_url=project_url,
    )


def test_help_lists_all_ten_commands():
    text = render_help()
    for cmd in (
        "/show_domain_report",
        "/show_subdomain_report",
        "/show_team_report",
        "/show_domain_list",
        "/show_subdomain_list",
        "/show_team_list",
        "/show_domain_risk",
        "/show_subdomain_risk",
        "/show_team_risk",
        "/help",
    ):
        assert cmd in text


def test_render_list_empty():
    text = render_list("Домены", [])
    assert "Домены" in text
    assert "Нет портфелей" in text


def test_render_list_with_items():
    portfolios = [
        Portfolio(id="d1", short_id=1, summary="B2B", parent_id=None, lead=None),
        Portfolio(id="d2", short_id=2, summary="B2C", parent_id=None, lead=None),
    ]
    text = render_list("Домены", portfolios)
    assert "- B2B" in text
    assert "- B2C" in text


def test_render_report_empty():
    text = render_report("Отчёт: Команда А", [])
    assert "Нет проектов" in text


def test_render_report_on_track_project():
    ws = WeeklyStatus(
        comments="всё идёт по плану",
        deadline="25.04.2026",
        created_at=NOW,
        raw="#WeeklyStatus\nComments: всё идёт по плану\nDL по решению: 25.04.2026",
    )
    s = _summary(weekly_status=ws, business_status=BusinessStatus.ON_TRACK)
    text = render_report("Отчёт: Команда А", [s])
    assert "[Bot](https://tracker.yandex.ru/projects/7)" in text
    assert "Ответственный: Иван Иванов" in text
    assert "🟢" in text
    assert "По плану" in text
    assert "всё идёт по плану" in text
    assert "DL по решению: 25.04.2026" in text
    assert "устарели" not in text


def test_render_report_missing_lead_and_comment():
    s = _summary(
        project=_project(lead_display=None),
        weekly_status=None,
        business_status=BusinessStatus.UNKNOWN,
    )
    text = render_report("Отчёт: Команда А", [s])
    assert "Ответственный: —" in text
    assert "Комментарий: —" in text
    assert "⚪" in text


def test_render_report_stale_project_shows_reference_comment_and_mark():
    stale_ws = WeeklyStatus(
        comments="был риск",
        deadline=None,
        created_at=NOW,
        raw="",
    )
    s = _summary(
        weekly_status=stale_ws,
        business_status=BusinessStatus.UNKNOWN,
        is_stale=True,
    )
    text = render_report("Отчёт: Команда А", [s])
    assert "был риск" in text
    assert "Статус неизвестен" in text
    assert "устарели" in text


def test_render_report_preserves_multiline_comment_formatting():
    ws = WeeklyStatus(
        comments="- пункт 1\n- пункт 2\n\nextra",
        deadline=None,
        created_at=NOW,
        raw="",
    )
    s = _summary(weekly_status=ws)
    text = render_report("Отчёт: Команда А", [s])
    assert "  - пункт 1" in text
    assert "  - пункт 2" in text
    assert "  extra" in text


def test_render_risk_excludes_on_track_and_unknown():
    on_track = _summary(
        project=_project(pid="p1", summary="OnTrack"),
        business_status=BusinessStatus.ON_TRACK,
    )
    at_risk = _summary(
        project=_project(pid="p2", summary="AtRisk"),
        business_status=BusinessStatus.AT_RISK,
    )
    blocked = _summary(
        project=_project(pid="p3", summary="Blocked"),
        business_status=BusinessStatus.BLOCKED,
    )
    unknown = _summary(
        project=_project(pid="p4", summary="Unknown"),
        business_status=BusinessStatus.UNKNOWN,
    )
    text = render_risk("Риски", [on_track, at_risk, blocked, unknown])
    assert "AtRisk" in text
    assert "Blocked" in text
    assert "OnTrack" not in text
    assert "Unknown" not in text


def test_render_risk_empty_when_no_risky_projects():
    on_track = _summary(business_status=BusinessStatus.ON_TRACK)
    unknown = _summary(business_status=BusinessStatus.UNKNOWN)
    text = render_risk("Риски", [on_track, unknown])
    assert "Проектов с рисками нет" in text
