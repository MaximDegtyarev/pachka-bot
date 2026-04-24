from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class TrackerUser:
    """Subset of Tracker user fields we actually use."""

    id: str
    display: str | None
    cloud_uid: str | None = None
    passport_uid: int | None = None


@dataclass(frozen=True)
class Portfolio:
    """A Tracker portfolio entity (domain / subdomain / team)."""

    id: str
    short_id: int
    summary: str
    parent_id: str | None
    lead: TrackerUser | None


@dataclass(frozen=True)
class Project:
    """A Tracker project entity (new /v2/entities/project API)."""

    id: str
    short_id: int
    summary: str
    description: str | None
    entity_status: str | None  # "draft" / "in_progress" / ... — technical status, NOT business status
    parent_portfolio_id: str | None  # fields.parentEntity.id
    parent_portfolio_display: str | None  # fields.parentEntity.display
    lead: TrackerUser | None
    start: str | None  # YYYY-MM-DD as returned by Tracker
    end: str | None
    updated_at: datetime | None
    tags: tuple[str, ...] = field(default_factory=tuple)
    # "clients" is the Tracker API field name for the Заказчик (customer) list on a project entity.
    clients: tuple[TrackerUser, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Comment:
    """A comment attached to a project entity. Used for #WeeklyStatus parsing."""

    id: str
    body: str
    created_at: datetime
    author: TrackerUser | None
