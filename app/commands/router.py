from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.report.aggregator import StatusAggregator
from app.report.builder import (
    render_blocked,
    render_help,
    render_list,
    render_on_track,
    render_report,
    render_risk,
)
from app.tracker.models import Portfolio

Action = Literal["report", "risk", "blocked", "on_track"]
Level = Literal["domain", "subdomain", "team"]


@dataclass
class _PendingSelection:
    """State stored per chat while waiting for the user to pick a number."""

    action: Action
    level: Level
    choices: list[Portfolio]


_SELECTION_HEADER: dict[Level, str] = {
    "domain": "Выберите домен:",
    "subdomain": "Выберите поддомен:",
    "team": "Выберите команду:",
}

_LEVEL_NOUN: dict[Level, str] = {
    "domain": "доменов",
    "subdomain": "поддоменов",
    "team": "команд",
}

_LEVEL_GENITIVE: dict[Level, str] = {
    "domain": "домена",
    "subdomain": "поддомена",
    "team": "команды",
}

_ACTION_LABEL: dict[Action, str] = {
    "report": "Отчёт",
    "risk": "Риски",
    "blocked": "Заблокированные",
    "on_track": "По плану",
}

_RENDERERS = {
    "report": render_report,
    "risk": render_risk,
    "blocked": render_blocked,
    "on_track": render_on_track,
}


class CommandRouter:
    """Maps Pachka slash-commands to Tracker data calls and produces Markdown replies.

    Two-step dialog for any command that must disambiguate between multiple portfolios:
      1. Bot sends a numbered list.
      2. User replies with a number → bot fetches and renders the chosen view.
    If only one portfolio matches, the dialog is skipped.

    In-memory pending state; cleared on restart.
    """

    def __init__(self, aggregator: StatusAggregator, domain_ids: list[str]) -> None:
        self._agg = aggregator
        self._domain_ids = domain_ids
        self._pending: dict[int, _PendingSelection] = {}

    async def handle(self, chat_id: int, text: str) -> str:
        text = (text or "").strip()

        if chat_id in self._pending and text.lstrip("-").isdigit():
            return await self._resolve(chat_id, int(text))

        cmd = text.split()[0].lower() if text else ""

        if chat_id in self._pending:
            del self._pending[chat_id]

        if cmd == "/help":
            return render_help()
        if cmd == "/show_domain_list":
            return await self._domain_list()
        if cmd == "/show_subdomain_list":
            return await self._subdomain_list()
        if cmd == "/show_team_list":
            return await self._team_list()

        for action in ("report", "risk", "blocked", "on_track"):
            for level in ("domain", "subdomain", "team"):
                if cmd == f"/show_{level}_{action}":
                    return await self._ask(chat_id, level, action)  # type: ignore[arg-type]

        return "Неизвестная команда. Введите /help для справки."

    # ── list commands ───────────────────────────────────────────────────────

    async def _domain_list(self) -> str:
        domains = await self._load_domains()
        return render_list("Домены", domains, web_base=self._agg.web_base)

    async def _subdomain_list(self) -> str:
        subs = await self._all_subdomains()
        return render_list("Поддомены", subs, web_base=self._agg.web_base)

    async def _team_list(self) -> str:
        teams = await self._all_teams()
        return render_list("Команды", teams, web_base=self._agg.web_base)

    # ── dialog ──────────────────────────────────────────────────────────────

    async def _ask(self, chat_id: int, level: Level, action: Action) -> str:
        choices = await self._list_for_level(level)
        if not choices:
            return f"Нет доступных {_LEVEL_NOUN[level]}."
        if len(choices) == 1:
            return await self._render_for(choices[0], level, action)

        self._pending[chat_id] = _PendingSelection(action=action, level=level, choices=choices)
        lines = [_SELECTION_HEADER[level], ""]
        lines.extend(f"{i + 1}. {p.summary}" for i, p in enumerate(choices))
        lines.append("\nВведите номер:")
        return "\n".join(lines)

    async def _resolve(self, chat_id: int, number: int) -> str:
        pending = self._pending.pop(chat_id)
        idx = number - 1
        if not (0 <= idx < len(pending.choices)):
            return f"Неверный номер. Введите от 1 до {len(pending.choices)}."
        return await self._render_for(pending.choices[idx], pending.level, pending.action)

    async def _render_for(self, portfolio: Portfolio, level: Level, action: Action) -> str:
        if level == "domain":
            summaries = await self._agg.domain_report(portfolio.id)
        elif level == "subdomain":
            summaries = await self._agg.subdomain_report(portfolio.id)
        else:
            summaries = await self._agg.team_report(portfolio.id)
        title = f"{_ACTION_LABEL[action]} {_LEVEL_GENITIVE[level]}: {portfolio.summary}"
        return _RENDERERS[action](title, summaries)

    # ── helpers ────────────────────────────────────────────────────────────

    async def _list_for_level(self, level: Level) -> list[Portfolio]:
        if level == "domain":
            return await self._load_domains()
        if level == "subdomain":
            return await self._all_subdomains()
        return await self._all_teams()

    async def _load_domains(self) -> list[Portfolio]:
        return [await self._agg.get_portfolio(did) for did in self._domain_ids]

    async def _all_subdomains(self) -> list[Portfolio]:
        result: list[Portfolio] = []
        for did in self._domain_ids:
            result.extend(await self._agg.list_subdomains(did))
        return result

    async def _all_teams(self) -> list[Portfolio]:
        teams: list[Portfolio] = []
        for sub in await self._all_subdomains():
            teams.extend(await self._agg.list_teams(sub.id))
        return teams
