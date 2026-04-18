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


async def _try(client: httpx.AsyncClient, method: str, url: str, **kw) -> dict | None:
    r = await client.request(method, url, **kw)
    print(f"{method} {url} -> {r.status_code}")
    try:
        data = r.json()
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return data
    except Exception:
        print(r.text)
        return None


PROJECT_FIELDS = ",".join(
    [
        "summary",
        "description",
        "lead",
        "teamUsers",
        "parentEntity",
        "start",
        "end",
        "tags",
        "entityStatus",
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
        print("=== 1. ALL portfolios (tree) ===")
        data = await _try(
            client,
            "POST",
            "/v2/entities/portfolio/_search",
            json={},
            params={"perPage": 100, "fields": "summary,lead,parentEntity"},
        )
        portfolios: list[dict] = (data or {}).get("values", [])
        print("\n--- Tree summary ---")
        for p in portfolios:
            pid = p.get("id")
            f = p.get("fields", {})
            parent = (f.get("parentEntity") or {}).get("id") or "ROOT"
            print(f"  {pid}  parent={parent}  summary={f.get('summary')!r}")

        print("\n=== 2. ALL projects in tracker (no filter, minimal fields) ===")
        await _try(
            client,
            "POST",
            "/v2/entities/project/_search",
            json={},
            params={"perPage": 50, "fields": "summary"},
        )

        print("\n=== 3. ALL projects with rich fields ===")
        await _try(
            client,
            "POST",
            "/v2/entities/project/_search",
            json={},
            params={"perPage": 50, "fields": PROJECT_FIELDS},
        )

        print("\n=== 4. Projects in each portfolio ===")
        for p in portfolios:
            pid = p["id"]
            summary = p.get("fields", {}).get("summary")
            print(f"\n--- portfolio {pid} ({summary!r}) ---")
            await _try(
                client,
                "POST",
                "/v2/entities/project/_search",
                json={"filter": {"parentEntity": pid}},
                params={"perPage": 50, "fields": PROJECT_FIELDS},
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
