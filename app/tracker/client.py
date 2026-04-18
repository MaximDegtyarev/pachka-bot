from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

import httpx

from app.tracker.models import Comment, Portfolio, Project, TrackerUser

PORTFOLIO_FIELDS = "summary,parentEntity,lead"
PROJECT_FIELDS = "summary,description,entityStatus,parentEntity,lead,start,end,tags"


class TrackerClient(Protocol):
    async def get_portfolio(self, portfolio_id: str) -> Portfolio: ...
    async def list_child_portfolios(self, parent_id: str) -> list[Portfolio]: ...
    async def list_projects_in_portfolio(self, portfolio_id: str) -> list[Project]: ...
    async def get_project(self, project_id: str) -> Project: ...
    async def list_project_comments(self, project_id: str) -> list[Comment]: ...


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Tracker returns "2026-04-17T11:09:21.103+0000"; fromisoformat wants "+00:00".
    if value.endswith("+0000"):
        value = value[:-5] + "+00:00"
    elif len(value) >= 5 and value[-5] in "+-" and value[-3] != ":":
        value = value[:-2] + ":" + value[-2:]
    return datetime.fromisoformat(value)


def _parse_user(data: dict[str, Any] | None) -> TrackerUser | None:
    if not data:
        return None
    return TrackerUser(
        id=str(data["id"]),
        display=data.get("display"),
        cloud_uid=data.get("cloudUid"),
        passport_uid=data.get("passportUid"),
    )


def _parse_portfolio(data: dict[str, Any]) -> Portfolio:
    f = data.get("fields") or {}
    parent = f.get("parentEntity")
    return Portfolio(
        id=str(data["id"]),
        short_id=int(data["shortId"]),
        summary=(f.get("summary") or "").strip(),
        parent_id=str(parent["id"]) if parent else None,
        lead=_parse_user(f.get("lead")),
    )


def _parse_comment(data: dict[str, Any]) -> Comment:
    created_at = _parse_dt(data.get("createdAt"))
    assert created_at is not None, "Tracker comment without createdAt"
    return Comment(
        id=str(data.get("longId") or data.get("id")),
        body=data.get("text") or "",
        created_at=created_at,
        author=_parse_user(data.get("createdBy")),
    )


def _parse_project(data: dict[str, Any]) -> Project:
    f = data.get("fields") or {}
    parent = f.get("parentEntity")
    return Project(
        id=str(data["id"]),
        short_id=int(data["shortId"]),
        summary=(f.get("summary") or "").strip(),
        description=f.get("description"),
        entity_status=f.get("entityStatus"),
        parent_portfolio_id=str(parent["id"]) if parent else None,
        parent_portfolio_display=parent.get("display") if parent else None,
        lead=_parse_user(f.get("lead")),
        start=f.get("start"),
        end=f.get("end"),
        updated_at=_parse_dt(data.get("updatedAt")),
        tags=tuple(f.get("tags") or ()),
    )


class YandexTrackerClient:
    """HTTP client for Yandex Tracker's entities API.

    Endpoints used:
      - GET  /v2/entities/portfolio/{id}
      - POST /v2/entities/portfolio/_search
      - GET  /v2/entities/project/{id}
      - POST /v2/entities/project/_search
      - GET  /v2/entities/project/{id}/comments           (probed separately)

    Header: X-Org-ID for Yandex 360 orgs, X-Cloud-Org-ID for Yandex Cloud orgs.
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
        r = await self._http.get(
            f"/v2/entities/portfolio/{portfolio_id}",
            params={"fields": PORTFOLIO_FIELDS},
        )
        r.raise_for_status()
        return _parse_portfolio(r.json())

    async def list_child_portfolios(
        self, parent_id: str, *, per_page: int = 50
    ) -> list[Portfolio]:
        return [
            _parse_portfolio(raw)
            for raw in await self._search_all(
                "/v2/entities/portfolio/_search",
                body={"filter": {"parentEntity": parent_id}},
                fields=PORTFOLIO_FIELDS,
                per_page=per_page,
            )
        ]

    async def list_projects_in_portfolio(
        self, portfolio_id: str, *, per_page: int = 50
    ) -> list[Project]:
        return [
            _parse_project(raw)
            for raw in await self._search_all(
                "/v2/entities/project/_search",
                body={"filter": {"parentEntity": portfolio_id}},
                fields=PROJECT_FIELDS,
                per_page=per_page,
            )
        ]

    async def get_project(self, project_id: str) -> Project:
        r = await self._http.get(
            f"/v2/entities/project/{project_id}",
            params={"fields": PROJECT_FIELDS},
        )
        r.raise_for_status()
        return _parse_project(r.json())

    async def list_project_comments(self, project_id: str) -> list[Comment]:
        r = await self._http.get(f"/v2/entities/project/{project_id}/comments")
        r.raise_for_status()
        payload = r.json()
        return [_parse_comment(item) for item in payload]

    async def _search_all(
        self,
        path: str,
        *,
        body: dict[str, Any],
        fields: str,
        per_page: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            r = await self._http.post(
                path,
                json=body,
                params={"perPage": per_page, "page": page, "fields": fields},
            )
            r.raise_for_status()
            payload = r.json()
            results.extend(payload.get("values") or [])
            total_pages = int(payload.get("pages") or 0)
            if page >= total_pages:
                break
            page += 1
        return results
