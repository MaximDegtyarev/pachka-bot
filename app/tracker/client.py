from __future__ import annotations

from typing import Protocol

import httpx

from app.tracker.models import Comment, Portfolio, Project


class TrackerClient(Protocol):
    async def get_portfolio(self, portfolio_id: str) -> Portfolio: ...
    async def list_projects_in_portfolio(self, portfolio_id: str) -> list[Project]: ...
    async def get_project(self, project_id: str) -> Project: ...
    async def list_project_comments(self, project_id: str) -> list[Comment]: ...


class YandexTrackerClient:
    """HTTP client for Yandex Tracker API.

    Endpoints used:
      - GET /v2/entities/portfolio/{id}
      - POST /v2/entities/project/_search     (filter by parent portfolio)
      - GET /v2/entities/project/{id}
      - GET /v2/issues/{key}/comments         (until we confirm project-level comments endpoint)

    NOTE: exact request/response shapes are verified against Yandex Tracker docs once the token
    is available. The implementation below intentionally leaves API calls as TODO — it is
    structured so that tests can mock individual methods without instantiating the client.
    """

    def __init__(
        self,
        *,
        base_url: str,
        oauth_token: str,
        org_id: str,
        org_type: str = "360",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        org_header = "X-Cloud-Org-ID" if org_type.lower() == "cloud" else "X-Org-ID"
        self._http = http_client or httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"OAuth {oauth_token}",
                org_header: org_id,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(15.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_portfolio(self, portfolio_id: str) -> Portfolio:
        raise NotImplementedError("wire up after live API check")

    async def list_projects_in_portfolio(self, portfolio_id: str) -> list[Project]:
        raise NotImplementedError("wire up after live API check")

    async def get_project(self, project_id: str) -> Project:
        raise NotImplementedError("wire up after live API check")

    async def list_project_comments(self, project_id: str) -> list[Comment]:
        raise NotImplementedError("wire up after live API check")
