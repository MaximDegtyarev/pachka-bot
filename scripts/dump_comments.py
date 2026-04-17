"""Exploratory probe: find the comments endpoint for a Tracker project entity.

Usage:
    python -m scripts.dump_comments <project_id_or_shortId>

Tries several plausible URLs — we don't know the exact one yet. The project may
also be referred to by its shortId (e.g. "22"); both are tried where it makes
sense. Pick one of the projects created today (e.g. "Project bot"), post a
comment containing "#WeeklyStatus", then run this to see what the API returns.
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
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(r.text)


async def main(project_ref: str) -> None:
    token = os.environ["TRACKER_OAUTH_TOKEN"]
    org_id = os.environ["TRACKER_ORG_ID"]
    base = os.environ.get("TRACKER_API_BASE", "https://api.tracker.yandex.net")

    headers = {
        "Authorization": f"OAuth {token}",
        "X-Org-ID": org_id,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=30.0) as client:
        print("=== A. Comments via entities path ===")
        await _try(client, "GET", f"/v2/entities/project/{project_ref}/comments")

        print("\n=== B. Comments via top-level issues path (legacy) ===")
        await _try(client, "GET", f"/v2/issues/{project_ref}/comments")

        print("\n=== C. Project with comments field expanded ===")
        await _try(
            client,
            "GET",
            f"/v2/entities/project/{project_ref}",
            params={"fields": "summary,comments"},
        )

        print("\n=== D. Comments via projects (alternate collection) ===")
        await _try(client, "GET", f"/v2/entities/project/{project_ref}/updates")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
