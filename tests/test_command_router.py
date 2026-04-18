from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.commands.router import CommandRouter
from app.report.aggregator import AggregatorConfig, StatusAggregator
from app.report.builder import ProjectSummary
from app.status.mapping import BusinessStatus
from app.tracker.models import Comment, Portfolio, Project, TrackerUser

DOMAIN_ID = "domain-1"
NOW = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)


_SHORT_IDS: dict[str, int] = {}


def _portfolio(pid: str, summary: str) -> Portfolio:
    sid = _SHORT_IDS.setdefault(pid, len(_SHORT_IDS) + 1)
    return Portfolio(id=pid, short_id=sid, summary=summary, parent_id=None, lead=None)


def _project(pid: str, summary: str) -> Project:
    sid = _SHORT_IDS.setdefault(pid, len(_SHORT_IDS) + 1)
    return Project(
        id=pid,
        short_id=sid,
        summary=summary,
        description=None,
        entity_status="in_progress",
        parent_portfolio_id=None,
        parent_portfolio_display=None,
        lead=TrackerUser(id="u1", display="Лид"),
        start=None,
        end=None,
        updated_at=None,
        tags=(),
    )


def _summary(pid: str, summary: str) -> ProjectSummary:
    sid = _SHORT_IDS.setdefault(pid, len(_SHORT_IDS) + 1)
    return ProjectSummary(
        project=_project(pid, summary),
        weekly_status=None,
        business_status=BusinessStatus.ON_TRACK,
        is_stale=True,
        project_url=f"https://tracker.yandex.ru/projects/{sid}",
    )


class FakeTracker:
    def __init__(self, domain: Portfolio, children: dict, projects: dict) -> None:
        self.domain = domain
        self.children = children
        self.projects = projects

    async def get_portfolio(self, pid: str) -> Portfolio:
        if pid == self.domain.id:
            return self.domain
        for portf_list in self.children.values():
            for p in portf_list:
                if p.id == pid:
                    return p
        raise KeyError(pid)

    async def list_child_portfolios(self, parent_id: str) -> list[Portfolio]:
        return self.children.get(parent_id, [])

    async def list_projects_in_portfolio(self, portfolio_id: str) -> list[Project]:
        return self.projects.get(portfolio_id, [])

    async def list_project_comments(self, project_id: str) -> list[Comment]:
        return []


DOMAIN = _portfolio("domain-1", "B2B PMO")
SUBDOMAIN_A = _portfolio("sub-a", "SubA")
SUBDOMAIN_B = _portfolio("sub-b", "SubB")
TEAM_1 = _portfolio("team-1", "Team 1")
TEAM_2 = _portfolio("team-2", "Team 2")
PROJ_1 = _project("proj-1", "Project Alpha")
PROJ_2 = _project("proj-2", "Project Beta")


@pytest.fixture
def router() -> CommandRouter:
    tracker = FakeTracker(
        domain=DOMAIN,
        children={
            "domain-1": [SUBDOMAIN_A, SUBDOMAIN_B],
            "sub-a": [TEAM_1],
            "sub-b": [TEAM_2],
        },
        projects={
            "team-1": [PROJ_1],
            "team-2": [PROJ_2],
        },
    )
    cfg = AggregatorConfig(web_base="https://tracker.yandex.ru", freshness_days=6)
    agg = StatusAggregator(tracker, cfg)
    return CommandRouter(agg, DOMAIN_ID)


async def test_help(router: CommandRouter):
    reply = await router.handle(1, "/help")
    assert "/show_domain_report" in reply
    assert "/help" in reply


async def test_unknown_command(router: CommandRouter):
    reply = await router.handle(1, "/foo")
    assert "/help" in reply.lower() or "неизвестная" in reply.lower()


async def test_domain_report_direct(router: CommandRouter):
    reply = await router.handle(1, "/show_domain_report")
    assert "B2B PMO" in reply


async def test_domain_risk_direct(router: CommandRouter):
    reply = await router.handle(1, "/show_domain_risk")
    assert "B2B PMO" in reply


async def test_domain_list_shows_subdomains(router: CommandRouter):
    reply = await router.handle(1, "/show_domain_list")
    assert "SubA" in reply
    assert "SubB" in reply


async def test_subdomain_list_shows_subdomains(router: CommandRouter):
    reply = await router.handle(1, "/show_subdomain_list")
    assert "SubA" in reply


async def test_team_list_shows_all_teams(router: CommandRouter):
    reply = await router.handle(1, "/show_team_list")
    assert "Team 1" in reply
    assert "Team 2" in reply


async def test_subdomain_report_two_step(router: CommandRouter):
    # Step 1: command → numbered list
    reply = await router.handle(42, "/show_subdomain_report")
    assert "1." in reply and "SubA" in reply
    assert "2." in reply and "SubB" in reply

    # Step 2: pick SubA → report
    reply = await router.handle(42, "1")
    assert "SubA" in reply
    assert "Отчёт" in reply


async def test_subdomain_risk_two_step(router: CommandRouter):
    await router.handle(42, "/show_subdomain_risk")
    reply = await router.handle(42, "2")
    assert "SubB" in reply
    assert "Риски" in reply


async def test_team_report_two_step(router: CommandRouter):
    reply = await router.handle(42, "/show_team_report")
    assert "Team 1" in reply or "Team 2" in reply

    reply = await router.handle(42, "1")
    assert "Team 1" in reply
    assert "Отчёт" in reply


async def test_team_risk_two_step(router: CommandRouter):
    await router.handle(42, "/show_team_risk")
    reply = await router.handle(42, "2")
    assert "Team 2" in reply
    assert "Риски" in reply


async def test_out_of_range_number_returns_error(router: CommandRouter):
    await router.handle(42, "/show_subdomain_report")
    reply = await router.handle(42, "99")
    assert "1 до 2" in reply
    # Pending is cleared — a new command starts fresh
    assert 42 not in router._pending


async def test_non_numeric_reply_cancels_pending(router: CommandRouter):
    await router.handle(42, "/show_subdomain_report")
    # User sends something other than a number
    reply = await router.handle(42, "/help")
    assert "/show_domain_report" in reply  # help text, not a list
    assert 42 not in router._pending


async def test_different_chats_have_independent_state(router: CommandRouter):
    # Chat 10 picks subdomain A, chat 20 picks subdomain B
    await router.handle(10, "/show_subdomain_report")
    await router.handle(20, "/show_subdomain_report")

    reply_10 = await router.handle(10, "1")
    reply_20 = await router.handle(20, "2")

    assert "SubA" in reply_10
    assert "SubB" in reply_20
