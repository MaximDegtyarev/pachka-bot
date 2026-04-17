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


async def main(portfolio_id: str) -> None:
    token = os.environ["TRACKER_OAUTH_TOKEN"]
    org_id = os.environ["TRACKER_ORG_ID"]
    base = os.environ.get("TRACKER_API_BASE", "https://api.tracker.yandex.net")

    headers = {
        "Authorization": f"OAuth {token}",
        "X-Cloud-Org-ID": org_id,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=30.0) as client:
        print(f"== GET /v2/entities/portfolio/{portfolio_id}")
        r = await client.get(f"/v2/entities/portfolio/{portfolio_id}")
        print(r.status_code)
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))

        print("\n== POST /v2/entities/project/_search  (filter: parent=portfolio)")
        r = await client.post(
            "/v2/entities/project/_search",
            json={"filter": {"parentEntity": portfolio_id}},
            params={"perPage": 50},
        )
        print(r.status_code)
        print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
