from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    tracker_ok = False
    pachca_ok = False

    try:
        tracker_ok = await request.app.state.tracker.ping()
    except AttributeError:
        pass

    try:
        pachca_ok = await request.app.state.pachca.ping()
    except AttributeError:
        pass

    overall = "healthy" if (tracker_ok and pachca_ok) else "degraded"
    return {
        "status": overall,
        "version": "0.1.0",
        "tracker": "ok" if tracker_ok else "error",
        "pachca": "ok" if pachca_ok else "error",
    }
