from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import structlog

from app.report.builder import ProjectSummary
from app.status.mapping import TRACKER_STATUS_MAP, BusinessStatus, map_tracker_status
from app.status.parser import pick_latest_weekly_status, utcnow
from app.tracker.models import Comment, Portfolio, Project

log = structlog.get_logger()


class TrackerClient(Protocol):
    async def get_portfolio(self, portfolio_id: str) -> Portfolio: ...
    async def list_child_portfolios(self, parent_id: str) -> list[Portfolio]: ...
    async def list_projects_in_portfolio(self, portfolio_id: str) -> list[Project]: ...
    async def list_project_comments(self, project_id: str) -> list[Comment]: ...


@dataclass(frozen=True)
class AggregatorConfig:
    web_base: str
    freshness_days: int = 6


class StatusAggregator:
    """Walks the portfolio tree and composes ProjectSummary lists per §4.2 and §9.2.

    - Team report: all projects in the team portfolio (no dedup; a project may be
      attached to several teams and must appear in each team's report).
    - Subdomain report: walk subdomain → teams → projects, dedup by project id.
    - Domain report: walk domain → subdomains → teams → projects, dedup by project id.

    Business status per project (§3.3, §7.2, §10):
    - Pick latest #WeeklyStatus comment.
    - If absent or older than freshness_days → status = UNKNOWN (stale).
    - Else → map project.entity_status to BusinessStatus.
    """

    def __init__(self, client: TrackerClient, config: AggregatorConfig) -> None:
        self._client = client
        self._config = config

    @property
    def web_base(self) -> str:
        return self._config.web_base

    async def get_portfolio(self, portfolio_id: str) -> Portfolio:
        return await self._client.get_portfolio(portfolio_id)

    async def list_subdomains(self, domain_id: str) -> list[Portfolio]:
        return await self._client.list_child_portfolios(domain_id)

    async def list_teams(self, subdomain_id: str) -> list[Portfolio]:
        return await self._client.list_child_portfolios(subdomain_id)

    async def team_report(
        self, team_id: str, *, now: datetime | None = None
    ) -> list[ProjectSummary]:
        projects = await self._client.list_projects_in_portfolio(team_id)
        return await self._summarize(projects, now=now or utcnow())

    async def subdomain_report(
        self, subdomain_id: str, *, now: datetime | None = None
    ) -> list[ProjectSummary]:
        teams = await self._client.list_child_portfolios(subdomain_id)
        projects = await self._collect_unique_projects([t.id for t in teams])
        return await self._summarize(projects, now=now or utcnow())

    async def domain_report(
        self, domain_id: str, *, now: datetime | None = None
    ) -> list[ProjectSummary]:
        team_ids: list[str] = []
        for sub in await self._client.list_child_portfolios(domain_id):
            team_ids.extend(t.id for t in await self._client.list_child_portfolios(sub.id))
        projects = await self._collect_unique_projects(team_ids)
        return await self._summarize(projects, now=now or utcnow())

    async def _collect_unique_projects(self, team_ids: list[str]) -> list[Project]:
        seen: dict[str, Project] = {}
        for tid in team_ids:
            for p in await self._client.list_projects_in_portfolio(tid):
                seen.setdefault(p.id, p)
        return list(seen.values())

    async def _summarize(
        self, projects: list[Project], *, now: datetime
    ) -> list[ProjectSummary]:
        result: list[ProjectSummary] = []
        for p in projects:
            raw_status = (p.entity_status or "").strip().lower()
            if raw_status not in TRACKER_STATUS_MAP:
                log.info("project.skipped", project_id=p.id, summary=p.summary, entity_status=p.entity_status)
                continue
            comments = await self._client.list_project_comments(p.id)
            ws = pick_latest_weekly_status([(c.body, c.created_at) for c in comments])
            is_stale = ws is None or not ws.is_fresh(now, self._config.freshness_days)
            mapped = map_tracker_status(p.entity_status)
            business_status = BusinessStatus.UNKNOWN if is_stale else mapped
            log.info(
                "project.status",
                project_id=p.id,
                summary=p.summary,
                entity_status=p.entity_status,
                mapped=mapped.value,
                is_stale=is_stale,
            )
            result.append(
                ProjectSummary(
                    project=p,
                    weekly_status=ws,
                    business_status=business_status,
                    is_stale=is_stale,
                    project_url=self._project_url(p),
                )
            )
        return result

    def _project_url(self, project: Project) -> str:
        return f"{self._config.web_base.rstrip('/')}/pages/projects/{project.short_id}"
