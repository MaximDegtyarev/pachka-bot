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


async def probe_with_header(
    base: str, token: str, org_id: str, header_name: str, portfolio_id: str
) -> None:
    print(f"\n########## Header: {header_name}={org_id} ##########")
    headers = {
        "Authorization": f"OAuth {token}",
        header_name: org_id,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=30.0) as client:
        await _try(client, "GET", "/v2/myself")
        await _try(client, "GET", f"/v2/entities/portfolio/{portfolio_id}")
        await _try(
            client,
            "POST",
            "/v2/entities/project/_search",
            json={"filter": {"parentEntity": portfolio_id}},
            params={"perPage": 50},
        )


async def main(portfolio_id: str) -> None:
    token = os.environ["TRACKER_OAUTH_TOKEN"]
    org_id = os.environ["TRACKER_ORG_ID"]
    base = os.environ.get("TRACKER_API_BASE", "https://api.tracker.yandex.net")

    for header in ("X-Org-ID", "X-Cloud-Org-ID"):
        await probe_with_header(base, token, org_id, header, portfolio_id)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
