from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.report.aggregator import AggregatorConfig, StatusAggregator
from app.status.mapping import BusinessStatus
from app.tracker.models import Comment, Portfolio, Project, TrackerUser

NOW = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)


def _portfolio(pid: str, summary: str, parent: str | None = None) -> Portfolio:
    return Portfolio(id=pid, short_id=int(pid[-1]), summary=summary, parent_id=parent, lead=None)


def _project(pid: str, short_id: int, summary: str, entity_status: str = "in_progress") -> Project:
    return Project(
        id=pid,
        short_id=short_id,
        summary=summary,
        description=None,
        entity_status=entity_status,
        parent_portfolio_id=None,
        parent_portfolio_display=None,
        lead=TrackerUser(id="u1", display="Лид"),
        start=None,
        end=None,
        updated_at=None,
        tags=(),
    )


def _comment(body: str, age_days: int) -> Comment:
    return Comment(
        id=f"c-{age_days}",
        body=body,
        created_at=NOW - timedelta(days=age_days),
        author=None,
    )


class FakeTracker:
    def __init__(
        self,
        *,
        children: dict[str, list[Portfolio]] | None = None,
        projects: dict[str, list[Project]] | None = None,
        comments: dict[str, list[Comment]] | None = None,
    ) -> None:
        self.children = children or {}
        self.projects = projects or {}
        self.comments = comments or {}
        self.comments_calls: list[str] = []

    async def get_portfolio(self, portfolio_id: str) -> Portfolio:  # pragma: no cover - unused
        raise NotImplementedError

    async def list_child_portfolios(self, parent_id: str) -> list[Portfolio]:
        return self.children.get(parent_id, [])

    async def list_projects_in_portfolio(self, portfolio_id: str) -> list[Project]:
        return self.projects.get(portfolio_id, [])

    async def list_project_comments(self, project_id: str) -> list[Comment]:
        self.comments_calls.append(project_id)
        return self.comments.get(project_id, [])


@pytest.fixture
def cfg() -> AggregatorConfig:
    return AggregatorConfig(web_base="https://tracker.yandex.ru", freshness_days=6)


async def test_team_report_summaries_use_entity_status_when_fresh(cfg: AggregatorConfig):
    p = _project("p1", 10, "Bot", entity_status="at_risk")
    fake = FakeTracker(
        projects={"team-1": [p]},
        comments={"p1": [_comment("#WeeklyStatus\nComments: риск", age_days=1)]},
    )
    agg = StatusAggregator(fake, cfg)
    summaries = await agg.team_report("team-1", now=NOW)
    assert len(summaries) == 1
    s = summaries[0]
    assert s.business_status == BusinessStatus.AT_RISK
    assert s.is_stale is False
    assert s.weekly_status is not None and "риск" in s.weekly_status.comments
    assert s.project_url == "https://tracker.yandex.ru/pages/projects/10"


async def test_team_report_marks_unknown_when_no_comment(cfg: AggregatorConfig):
    p = _project("p1", 10, "Bot", entity_status="in_progress")
    fake = FakeTracker(projects={"team-1": [p]}, comments={"p1": []})
    agg = StatusAggregator(fake, cfg)
    (s,) = await agg.team_report("team-1", now=NOW)
    assert s.business_status == BusinessStatus.UNKNOWN
    assert s.is_stale is True
    assert s.weekly_status is None


async def test_team_report_marks_unknown_when_comment_stale(cfg: AggregatorConfig):
    p = _project("p1", 10, "Bot", entity_status="in_progress")
    fake = FakeTracker(
        projects={"team-1": [p]},
        comments={"p1": [_comment("#WeeklyStatus\nComments: старо", age_days=10)]},
    )
    agg = StatusAggregator(fake, cfg)
    (s,) = await agg.team_report("team-1", now=NOW)
    assert s.business_status == BusinessStatus.UNKNOWN
    assert s.is_stale is True
    # Comment is kept as reference per §7.2
    assert s.weekly_status is not None
    assert "старо" in s.weekly_status.comments


async def test_team_report_ignores_comments_without_weekly_tag(cfg: AggregatorConfig):
    p = _project("p1", 10, "Bot")
    fake = FakeTracker(
        projects={"team-1": [p]},
        comments={"p1": [_comment("just a chat message", age_days=1)]},
    )
    agg = StatusAggregator(fake, cfg)
    (s,) = await agg.team_report("team-1", now=NOW)
    assert s.weekly_status is None
    assert s.is_stale is True


async def test_subdomain_report_dedups_project_in_multiple_teams(cfg: AggregatorConfig):
    shared = _project("p-shared", 7, "Shared")
    only_a = _project("p-a", 8, "OnlyA")
    fake = FakeTracker(
        children={
            "sub-1": [_portfolio("t1", "Team A"), _portfolio("t2", "Team B")],
        },
        projects={
            "t1": [shared, only_a],
            "t2": [shared],
        },
        comments={"p-shared": [], "p-a": []},
    )
    agg = StatusAggregator(fake, cfg)
    summaries = await agg.subdomain_report("sub-1", now=NOW)
    ids = [s.project.id for s in summaries]
    assert ids.count("p-shared") == 1
    assert "p-a" in ids
    # Comments fetched once per unique project
    assert sorted(fake.comments_calls) == ["p-a", "p-shared"]


async def test_domain_report_walks_two_levels_and_dedups(cfg: AggregatorConfig):
    shared = _project("p-shared", 7, "Shared")
    p1 = _project("p-1", 8, "P1")
    p2 = _project("p-2", 9, "P2")
    fake = FakeTracker(
        children={
            "domain-1": [_portfolio("sub1", "Sub 1"), _portfolio("sub2", "Sub 2")],
            "sub1": [_portfolio("t1", "Team 1")],
            "sub2": [_portfolio("t2", "Team 2"), _portfolio("t3", "Team 3")],
        },
        projects={
            "t1": [shared, p1],
            "t2": [shared, p2],
            "t3": [p2],
        },
        comments={"p-shared": [], "p-1": [], "p-2": []},
    )
    agg = StatusAggregator(fake, cfg)
    summaries = await agg.domain_report("domain-1", now=NOW)
    ids = sorted(s.project.id for s in summaries)
    assert ids == ["p-1", "p-2", "p-shared"]


async def test_team_report_keeps_duplicates_within_team_skipped(cfg: AggregatorConfig):
    # Tracker returns each project once per team; no dedup inside a team is needed.
    # This sanity check confirms we don't accidentally drop rows for team-level reports.
    p1 = _project("p1", 1, "A")
    p2 = _project("p2", 2, "B")
    fake = FakeTracker(projects={"t1": [p1, p2]}, comments={"p1": [], "p2": []})
    agg = StatusAggregator(fake, cfg)
    summaries = await agg.team_report("t1", now=NOW)
    assert [s.project.id for s in summaries] == ["p1", "p2"]


async def test_list_subdomains_and_teams(cfg: AggregatorConfig):
    fake = FakeTracker(
        children={
            "d1": [_portfolio("s1", "Sub 1")],
            "s1": [_portfolio("t1", "Team 1"), _portfolio("t2", "Team 2")],
        }
    )
    agg = StatusAggregator(fake, cfg)
    subs = await agg.list_subdomains("d1")
    assert [p.summary for p in subs] == ["Sub 1"]
    teams = await agg.list_teams("s1")
    assert [p.summary for p in teams] == ["Team 1", "Team 2"]


async def test_project_url_strips_trailing_slash_in_web_base():
    fake = FakeTracker(
        projects={"t": [_project("p", 42, "X")]},
        comments={"p": []},
    )
    agg = StatusAggregator(
        fake,
        AggregatorConfig(web_base="https://tracker.yandex.ru/", freshness_days=6),
    )
    (s,) = await agg.team_report("t", now=NOW)
    assert s.project_url == "https://tracker.yandex.ru/pages/projects/42"
