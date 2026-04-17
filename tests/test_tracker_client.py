"""Unit tests for YandexTrackerClient, fed with fixtures captured from the live API."""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from app.tracker.client import YandexTrackerClient

BASE_URL = "https://api.tracker.yandex.net"
TOKEN = "test-token"
ORG_ID = "8426512"


PORTFOLIO_JSON = {
    "self": f"{BASE_URL}/v2/entities/portfolio/69e213652577131acba63864",
    "id": "69e213652577131acba63864",
    "version": 2,
    "shortId": 19,
    "entityType": "portfolio",
    "createdAt": "2026-04-17T11:03:01.177+0000",
    "updatedAt": "2026-04-17T11:31:48.593+0000",
    "fields": {
        "summary": "B2B PMO",
        "parentEntity": None,
        "lead": {
            "self": f"{BASE_URL}/v2/users/8000000000000004",
            "id": "8000000000000004",
            "display": "Maxim Degtyarev",
            "cloudUid": "ajerm5kvdf5n3pdntlck",
            "passportUid": 529445253,
        },
    },
}

SUBDOMAIN_JSON = {
    **PORTFOLIO_JSON,
    "id": "69e21375562b1c65ac0cdb8b",
    "shortId": 20,
    "fields": {
        "summary": "Subdomain",
        "parentEntity": {
            "self": f"{BASE_URL}/v2/entities/portfolio/69e213652577131acba63864",
            "id": "69e213652577131acba63864",
            "display": "B2B PMO",
        },
        "lead": PORTFOLIO_JSON["fields"]["lead"],
    },
}

PROJECT_JSON = {
    "self": f"{BASE_URL}/v2/entities/project/69e2138e71a22713b3e17e74",
    "id": "69e2138e71a22713b3e17e74",
    "version": 4,
    "shortId": 22,
    "entityType": "project",
    "createdAt": "2026-04-17T11:03:42.109+0000",
    "updatedAt": "2026-04-17T11:31:49.005+0000",
    "fields": {
        "summary": "Project bot",
        "description": "hello",
        "entityStatus": "in_progress",
        "parentEntity": {
            "self": f"{BASE_URL}/v2/entities/portfolio/69e2138070fcad39d9d16d5f",
            "id": "69e2138070fcad39d9d16d5f",
            "display": "Team ",
        },
        "start": None,
        "end": "2026-06-30",
        "lead": PORTFOLIO_JSON["fields"]["lead"],
        "teamUsers": [],
        "tags": ["tag-a", "tag-b"],
    },
}


@pytest.fixture
def client() -> YandexTrackerClient:
    return YandexTrackerClient(
        base_url=BASE_URL,
        oauth_token=TOKEN,
        org_id=ORG_ID,
    )


async def test_get_portfolio_parses_parent_and_lead(
    client: YandexTrackerClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2/entities/portfolio/69e21375562b1c65ac0cdb8b?fields=summary,parentEntity,lead",
        json=SUBDOMAIN_JSON,
    )
    p = await client.get_portfolio("69e21375562b1c65ac0cdb8b")
    assert p.id == "69e21375562b1c65ac0cdb8b"
    assert p.short_id == 20
    assert p.summary == "Subdomain"
    assert p.parent_id == "69e213652577131acba63864"
    assert p.lead is not None
    assert p.lead.display == "Maxim Degtyarev"
    assert p.lead.passport_uid == 529445253


async def test_get_portfolio_root_has_no_parent(
    client: YandexTrackerClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2/entities/portfolio/69e213652577131acba63864?fields=summary,parentEntity,lead",
        json=PORTFOLIO_JSON,
    )
    p = await client.get_portfolio("69e213652577131acba63864")
    assert p.parent_id is None
    assert p.summary == "B2B PMO"


async def test_get_project_parses_all_fields(
    client: YandexTrackerClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=(
            f"{BASE_URL}/v2/entities/project/69e2138e71a22713b3e17e74"
            "?fields=summary,description,entityStatus,parentEntity,lead,start,end,tags"
        ),
        json=PROJECT_JSON,
    )
    p = await client.get_project("69e2138e71a22713b3e17e74")
    assert p.summary == "Project bot"
    assert p.description == "hello"
    assert p.entity_status == "in_progress"
    assert p.parent_portfolio_id == "69e2138070fcad39d9d16d5f"
    assert p.parent_portfolio_display == "Team "
    assert p.end == "2026-06-30"
    assert p.start is None
    assert p.tags == ("tag-a", "tag-b")
    assert p.updated_at is not None
    assert p.updated_at.year == 2026
    assert p.lead is not None and p.lead.id == "8000000000000004"


async def test_list_projects_paginates_until_done(
    client: YandexTrackerClient, httpx_mock: HTTPXMock
) -> None:
    page1 = {"hits": 3, "pages": 2, "values": [PROJECT_JSON]}
    page2 = {"hits": 3, "pages": 2, "values": [PROJECT_JSON, PROJECT_JSON]}
    httpx_mock.add_response(
        method="POST",
        url=(
            f"{BASE_URL}/v2/entities/project/_search"
            "?perPage=50&page=1&fields=summary,description,entityStatus,parentEntity,lead,start,end,tags"
        ),
        json=page1,
    )
    httpx_mock.add_response(
        method="POST",
        url=(
            f"{BASE_URL}/v2/entities/project/_search"
            "?perPage=50&page=2&fields=summary,description,entityStatus,parentEntity,lead,start,end,tags"
        ),
        json=page2,
    )
    projects = await client.list_projects_in_portfolio("69e2138070fcad39d9d16d5f")
    assert len(projects) == 3
    assert all(p.summary == "Project bot" for p in projects)


async def test_list_projects_empty_portfolio(
    client: YandexTrackerClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=(
            f"{BASE_URL}/v2/entities/project/_search"
            "?perPage=50&page=1&fields=summary,description,entityStatus,parentEntity,lead,start,end,tags"
        ),
        json={"hits": 0, "pages": 0, "values": []},
    )
    projects = await client.list_projects_in_portfolio("69e21375562b1c65ac0cdb8b")
    assert projects == []
