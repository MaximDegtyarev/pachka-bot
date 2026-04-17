from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Portfolio:
    id: str
    title: str
    url: str


@dataclass(frozen=True)
class Project:
    id: str
    key: str
    title: str
    url: str
    status: str | None
    lead_login: str | None
    lead_display: str | None
    portfolio_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Comment:
    id: str
    body: str
    created_at: datetime
    author_login: str | None
