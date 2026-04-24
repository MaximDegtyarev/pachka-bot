from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.commands.router import CommandRouter
from app.report.aggregator import AggregatorConfig, StatusAggregator
from app.tracker.models import Comment, Portfolio, Project, TrackerUser

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
        entity_status="according_to_plan",
        parent_portfolio_id=None,
        parent_portfolio_display=None,
        lead=TrackerUser(id="u1", display="Лид"),
        start=None,
        end=None,
        updated_at=None,
        tags=(),
    )


class FakeTracker:
    def __init__(self, portfolios: dict, children: dict, projects: dict) -> None:
        self.portfolios = portfolios
        self.children = children
        self.projects = projects

    async def get_portfolio(self, pid: str) -> Portfolio:
        return self.portfolios[pid]

    async def list_child_portfolios(self, parent_id: str) -> list[Portfolio]:
        return self.children.get(parent_id, [])

    async def list_projects_in_portfolio(self, portfolio_id: str) -> list[Project]:
        return self.projects.get(portfolio_id, [])

    async def list_project_comments(self, project_id: str) -> list[Comment]:
        return []


DOMAIN_A = _portfolio("domain-1", "B2B PMO")
DOMAIN_B = _portfolio("domain-2", "B2C PMO")
SUBDOMAIN_A = _portfolio("sub-a", "SubA")
SUBDOMAIN_B = _portfolio("sub-b", "SubB")
TEAM_1 = _portfolio("team-1", "Team 1")
TEAM_2 = _portfolio("team-2", "Team 2")
PROJ_1 = _project("proj-1", "Project Alpha")
PROJ_2 = _project("proj-2", "Project Beta")


def _make_router(domain_ids: list[str]) -> CommandRouter:
    tracker = FakeTracker(
        portfolios={
            "domain-1": DOMAIN_A,
            "domain-2": DOMAIN_B,
            "sub-a": SUBDOMAIN_A,
            "sub-b": SUBDOMAIN_B,
            "team-1": TEAM_1,
            "team-2": TEAM_2,
        },
        children={
            "domain-1": [SUBDOMAIN_A, SUBDOMAIN_B],
            "domain-2": [],
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
    return CommandRouter(agg, domain_ids=domain_ids)


@pytest.fixture
def router() -> CommandRouter:
    return _make_router(["domain-1"])


@pytest.fixture
def multi_domain_router() -> CommandRouter:
    return _make_router(["domain-1", "domain-2"])


async def test_help(router: CommandRouter):
    reply = await router.handle(1, "/help")
    assert "/show_domain_report" in reply
    assert "/show_domain_blocked" in reply
    assert "/show_domain_on_track" in reply
    assert "/help" in reply


async def test_unknown_command(router: CommandRouter):
    reply = await router.handle(1, "/foo")
    assert "неизвестная" in reply.lower()


async def test_domain_report_single_domain_runs_directly(router: CommandRouter):
    reply = await router.handle(1, "/show_domain_report")
    assert "B2B PMO" in reply
    assert "Отчёт" in reply


async def test_domain_list_shows_configured_domains(router: CommandRouter):
    reply = await router.handle(1, "/show_domain_list")
    assert "B2B PMO" in reply
    assert "SubA" not in reply


async def test_multi_domain_list(multi_domain_router: CommandRouter):
    reply = await multi_domain_router.handle(1, "/show_domain_list")
    assert "B2B PMO" in reply
    assert "B2C PMO" in reply


async def test_multi_domain_report_asks_choice(multi_domain_router: CommandRouter):
    reply = await multi_domain_router.handle(42, "/show_domain_report")
    assert "1." in reply and "B2B PMO" in reply
    assert "2." in reply and "B2C PMO" in reply

    reply = await multi_domain_router.handle(42, "1")
    assert "B2B PMO" in reply


async def test_subdomain_list(router: CommandRouter):
    reply = await router.handle(1, "/show_subdomain_list")
    assert "SubA" in reply
    assert "SubB" in reply


async def test_team_list(router: CommandRouter):
    reply = await router.handle(1, "/show_team_list")
    assert "Team 1" in reply
    assert "Team 2" in reply


async def test_subdomain_report_two_step(router: CommandRouter):
    reply = await router.handle(42, "/show_subdomain_report")
    assert "1." in reply and "SubA" in reply
    assert "2." in reply and "SubB" in reply

    reply = await router.handle(42, "1")
    assert "SubA" in reply
    assert "Отчёт" in reply


async def test_subdomain_risk_two_step(router: CommandRouter):
    await router.handle(42, "/show_subdomain_risk")
    reply = await router.handle(42, "2")
    assert "SubB" in reply
    assert "Риски" in reply


async def test_team_report_two_step(router: CommandRouter):
    await router.handle(42, "/show_team_report")
    reply = await router.handle(42, "1")
    assert "Team 1" in reply
    assert "Отчёт" in reply


async def test_blocked_command(router: CommandRouter):
    await router.handle(42, "/show_team_blocked")
    reply = await router.handle(42, "1")
    assert "Заблокированные" in reply


async def test_on_track_command(router: CommandRouter):
    await router.handle(42, "/show_team_on_track")
    reply = await router.handle(42, "1")
    assert "По плану" in reply


async def test_out_of_range_number(router: CommandRouter):
    await router.handle(42, "/show_subdomain_report")
    reply = await router.handle(42, "99")
    assert "1 до 2" in reply
    assert 42 not in router._pending


async def test_non_numeric_cancels_pending(router: CommandRouter):
    await router.handle(42, "/show_subdomain_report")
    reply = await router.handle(42, "/help")
    assert "/show_domain_report" in reply
    assert 42 not in router._pending


async def test_independent_chat_state(router: CommandRouter):
    await router.handle(10, "/show_subdomain_report")
    await router.handle(20, "/show_subdomain_report")

    reply_10 = await router.handle(10, "1")
    reply_20 = await router.handle(20, "2")

    assert "SubA" in reply_10
    assert "SubB" in reply_20


async def test_multi_domain_team_report_drills_down(multi_domain_router: CommandRouter):
    reply = await multi_domain_router.handle(42, "/show_team_report")
    assert "Выберите домен" in reply
    assert "B2B PMO" in reply and "B2C PMO" in reply

    reply = await multi_domain_router.handle(42, "1")
    assert "Выберите команду" in reply
    assert "Team 1" in reply and "Team 2" in reply

    reply = await multi_domain_router.handle(42, "1")
    assert "Team 1" in reply
    assert "Отчёт" in reply
    assert 42 not in multi_domain_router._pending


async def test_multi_domain_subdomain_report_drills_down(multi_domain_router: CommandRouter):
    reply = await multi_domain_router.handle(42, "/show_subdomain_report")
    assert "Выберите домен" in reply

    reply = await multi_domain_router.handle(42, "1")
    assert "Выберите поддомен" in reply
    assert "SubA" in reply and "SubB" in reply

    reply = await multi_domain_router.handle(42, "2")
    assert "SubB" in reply
    assert "Отчёт" in reply


async def test_multi_domain_team_report_skips_domain_with_no_teams(multi_domain_router: CommandRouter):
    # domain-2 has no subdomains/teams in the fixture.
    await multi_domain_router.handle(42, "/show_team_report")
    reply = await multi_domain_router.handle(42, "2")
    assert "нет команд" in reply.lower()
    assert 42 not in multi_domain_router._pending


async def test_cross_team_command(router: CommandRouter):
    reply = await router.handle(42, "/show_cross_team")
    assert "Выберите команду" in reply

    reply = await router.handle(42, "1")
    assert "Кросс" in reply


async def test_cross_domain_command_single_domain(router: CommandRouter):
    reply = await router.handle(1, "/show_cross_domain")
    assert "Кросс" in reply


async def test_help_includes_cross_commands(router: CommandRouter):
    reply = await router.handle(1, "/help")
    assert "/show_cross_domain" in reply
    assert "/show_cross_subdomain" in reply
    assert "/show_cross_team" in reply
