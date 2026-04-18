"""Exploratory probe: discover project status codes used by the workspace.

Usage:
    python -m scripts.dump_statuses

Lists distinct entityStatus values across ALL projects and also tries several
URLs that might expose the full list of allowed project statuses (workflow).
Run this AFTER setting at least one test project to "По плану", one to
"Есть риски", one to "Заблокирован" in the Tracker UI, so the API
returns the actual codes for those values.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import Counter

import httpx


async def _try(client: httpx.AsyncClient, method: str, url: str, **kw) -> None:
    r = await client.request(method, url, **kw)
    print(f"{method} {url} -> {r.status_code}")
    try:
        print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:2000])
    except Exception:
        print(r.text[:2000])


async def main() -> None:
    token = os.environ["TRACKER_OAUTH_TOKEN"]
    org_id = os.environ["TRACKER_ORG_ID"]
    base = os.environ.get("TRACKER_API_BASE", "https://api.tracker.yandex.net")

    headers = {
        "Authorization": f"OAuth {token}",
        "X-Org-ID": org_id,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=30.0) as client:
        print("=== 1. entityStatus values across ALL projects ===")
        r = await client.post(
            "/v2/entities/project/_search",
            json={},
            params={"perPage": 100, "fields": "summary,entityStatus"},
        )
        r.raise_for_status()
        values = r.json().get("values", [])
        counter: Counter[str] = Counter()
        for v in values:
            status = (v.get("fields") or {}).get("entityStatus")
            counter[str(status)] += 1
            print(f"  {v['id']}  {status!r}  summary={(v.get('fields') or {}).get('summary')!r}")
        print("\nTotals:")
        for status, count in counter.most_common():
            print(f"  {status!r}: {count}")

        print("\n=== 2. Possible status catalog endpoints ===")
        for url in (
            "/v2/statuses",
            "/v2/entities/project/statuses",
            "/v2/entities/project/_metadata",
            "/v2/entities/project/_fields",
            "/v2/fields/entityStatus",
        ):
            await _try(client, "GET", url)
            print()


if __name__ == "__main__":
    asyncio.run(main())
