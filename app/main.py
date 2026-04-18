import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.webhook import router as webhook_router
from app.commands.router import CommandRouter
from app.config import get_settings
from app.pachca.client import PachcaClient
from app.report.aggregator import AggregatorConfig, StatusAggregator
from app.tracker.client import YandexTrackerClient


def _configure_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if level == "DEBUG" else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level, logging.INFO)
        ),
    )


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _configure_logging(settings.log_level.upper())

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

    application.state.tracker = tracker
    application.state.command_router = command_router
    application.state.pachca = pachca

    yield

    await tracker.aclose()
    await pachca.aclose()


app = FastAPI(title="pachka-bot", version="0.1.0", lifespan=lifespan)

app.include_router(health_router)
app.include_router(webhook_router)
