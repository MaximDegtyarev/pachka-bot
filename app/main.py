from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.webhook import router as webhook_router
from app.commands.router import CommandRouter
from app.config import get_settings
from app.pachca.client import PachcaClient
from app.report.aggregator import AggregatorConfig, StatusAggregator
from app.tracker.client import YandexTrackerClient


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    tracker = YandexTrackerClient(
        base_url=settings.tracker_api_base,
        oauth_token=settings.tracker_oauth_token,
        org_id=settings.tracker_org_id,
        org_type=settings.tracker_org_type,
    )
    aggregator = StatusAggregator(
        tracker,
        AggregatorConfig(
            web_base=settings.tracker_web_base,
            freshness_days=settings.status_freshness_days,
        ),
    )
    pachca = PachcaClient(
        base_url=settings.pachca_api_base,
        access_token=settings.pachca_access_token,
    )
    command_router = CommandRouter(aggregator, domain_id=settings.portfolio_domain_id)

    application.state.command_router = command_router
    application.state.pachca = pachca

    yield

    await tracker.aclose()
    await pachca.aclose()


app = FastAPI(title="pachka-bot", version="0.1.0", lifespan=lifespan)

app.include_router(health_router)
app.include_router(webhook_router)
