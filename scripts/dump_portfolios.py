"""Exploratory script: dump a Yandex Tracker portfolio with its nested projects.

Usage:
    python -m scripts.dump_portfolios <portfolio_id>

Requires TRACKER_OAUTH_TOKEN and TRACKER_ORG_ID in the environment (or .env).
Intended to help verify API shapes and build the hardcoded portfolio map.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx


async def _try(client: httpx.AsyncClient, method: str, url: str, **kw) -> None:
    r = await client.request(method, url, **kw)
    print(f"{method} {url} -> {r.status_code}")
    try:
        print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:4000])
    except Exception:
        print(r.text[:2000])


PROJECT_FIELDS = ",".join(
    [
        "summary",
        "description",
        "status",
        "lead",
        "teamUsers",
        "parentEntity",
        "parentEntityId",
        "start",
        "end",
        "tags",
    ]
)


async def main(portfolio_id: str) -> None:
    token = os.environ["TRACKER_OAUTH_TOKEN"]
    org_id = os.environ["TRACKER_ORG_ID"]
    base = os.environ.get("TRACKER_API_BASE", "https://api.tracker.yandex.net")

    headers = {
        "Authorization": f"OAuth {token}",
        "X-Org-ID": org_id,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=30.0) as client:
        print("=== 1. Portfolio with fields ===")
        await _try(
            client,
            "GET",
            f"/v2/entities/portfolio/{portfolio_id}",
            params={"fields": "summary,description,lead,teamUsers"},
        )

        print("\n=== 2. ALL projects in the org (no filter, first 50) ===")
        await _try(
            client,
            "POST",
            "/v2/entities/project/_search",
            json={},
            params={"perPage": 50, "fields": PROJECT_FIELDS},
        )

        print("\n=== 3. Projects by parentEntity (original filter) ===")
        await _try(
            client,
            "POST",
            "/v2/entities/project/_search",
            json={"filter": {"parentEntity": portfolio_id}},
            params={"perPage": 50, "fields": PROJECT_FIELDS},
        )

        print("\n=== 4. Projects by parentEntityId (alt filter key) ===")
        await _try(
            client,
            "POST",
            "/v2/entities/project/_search",
            json={"filter": {"parentEntityId": portfolio_id}},
            params={"perPage": 50, "fields": PROJECT_FIELDS},
        )

        print("\n=== 5. ALL portfolios in the org ===")
        await _try(
            client,
            "POST",
            "/v2/entities/portfolio/_search",
            json={},
            params={"perPage": 50, "fields": "summary,lead,parentEntity"},
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
