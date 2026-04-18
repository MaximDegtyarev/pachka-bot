from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.report.aggregator import StatusAggregator
from app.report.builder import render_help, render_list, render_report, render_risk
from app.tracker.models import Portfolio


@dataclass
class _PendingSelection:
    """State stored per chat while waiting for the user to pick a number."""

    action: Literal["report", "risk"]
    level: Literal["subdomain", "team"]
    choices: list[Portfolio]


_SELECTION_HEADER: dict[str, str] = {
    "subdomain": "Выберите поддомен:",
    "team": "Выберите команду:",
}

_LEVEL_NOUN: dict[str, str] = {
    "subdomain": "поддоменов",
    "team": "команд",
}


class CommandRouter:
    """Maps Pachka slash-commands to Tracker data calls and produces Markdown replies.

    Two-step dialog for subdomain/team commands:
      1. Bot sends a numbered list of portfolios.
      2. User replies with a number → bot fetches and renders the chosen report.

    In-memory pending state; cleared on restart.
    """

    def __init__(self, aggregator: StatusAggregator, domain_id: str) -> None:
        self._agg = aggregator
        self._domain_id = domain_id
        self._pending: dict[int, _PendingSelection] = {}

    async def handle(self, chat_id: int, text: str) -> str:
        text = (text or "").strip()

        # If there's a pending selection and the user replied with a number, resolve it.
        if chat_id in self._pending and text.lstrip("-").isdigit():
            return await self._resolve(chat_id, int(text))

        cmd = text.split()[0].lower() if text else ""

        # A non-numeric message always cancels any pending state silently.
        if chat_id in self._pending:
            del self._pending[chat_id]

        match cmd:
            case "/help":
                return render_help()
            case "/show_domain_report":
                return await self._domain_report()
            case "/show_domain_risk":
                return await self._domain_risk()
            case "/show_domain_list":
                return await self._domain_list()
            case "/show_subdomain_report":
                return await self._ask(chat_id, "subdomain", "report")
            case "/show_subdomain_risk":
                return await self._ask(chat_id, "subdomain", "risk")
            case "/show_subdomain_list":
                return await self._subdomain_list()
            case "/show_team_report":
                return await self._ask(chat_id, "team", "report")
            case "/show_team_risk":
                return await self._ask(chat_id, "team", "risk")
            case "/show_team_list":
                return await self._team_list()
            case _:
                return "Неизвестная команда. Введите /help для справки."

    # ── direct (no dialog) ──────────────────────────────────────────────────

    async def _domain_report(self) -> str:
        domain = await self._agg.get_portfolio(self._domain_id)
        summaries = await self._agg.domain_report(self._domain_id)
        return render_report(f"Отчёт по домену: {domain.summary}", summaries)

    async def _domain_risk(self) -> str:
        domain = await self._agg.get_portfolio(self._domain_id)
        summaries = await self._agg.domain_report(self._domain_id)
        return render_risk(f"Риски домена: {domain.summary}", summaries)

    async def _domain_list(self) -> str:
        subs = await self._agg.list_subdomains(self._domain_id)
        return render_list("Поддомены", subs, web_base=self._agg.web_base)

    async def _subdomain_list(self) -> str:
        subs = await self._agg.list_subdomains(self._domain_id)
        return render_list("Поддомены", subs, web_base=self._agg.web_base)

    async def _team_list(self) -> str:
        teams = await self._all_teams()
        return render_list("Команды", teams, web_base=self._agg.web_base)

    # ── two-step dialog ────────────────────────────────────────────────────

    async def _ask(
        self,
        chat_id: int,
        level: Literal["subdomain", "team"],
        action: Literal["report", "risk"],
    ) -> str:
        choices = (
            await self._agg.list_subdomains(self._domain_id)
            if level == "subdomain"
            else await self._all_teams()
        )
        if not choices:
            return f"Нет доступных {_LEVEL_NOUN[level]}."
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
        portfolio = pending.choices[idx]
        renderer = render_report if pending.action == "report" else render_risk
        action_label = "Отчёт" if pending.action == "report" else "Риски"
        if pending.level == "subdomain":
            summaries = await self._agg.subdomain_report(portfolio.id)
            title = f"{action_label} поддомена: {portfolio.summary}"
        else:
            summaries = await self._agg.team_report(portfolio.id)
            title = f"{action_label} команды: {portfolio.summary}"
        return renderer(title, summaries)

    # ── helpers ────────────────────────────────────────────────────────────

    async def _all_teams(self) -> list[Portfolio]:
        teams: list[Portfolio] = []
        for sub in await self._agg.list_subdomains(self._domain_id):
            teams.extend(await self._agg.list_teams(sub.id))
        return teams
