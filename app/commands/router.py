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
    """State stored per chat while waiting for the user to pick a number.

    `current_level` = what's being picked right now.
    `final_level`   = what we ultimately want to render.
    When `current_level == final_level`, the next numeric input produces the report.
    Otherwise, the pick narrows the scope (e.g. domain → team).
    """

    action: Action
    current_level: Level
    final_level: Level
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

    Dialog flow:
      - `/show_domain_*`       → pick domain (skipped if one domain is configured).
      - `/show_subdomain_*`    → pick domain → pick subdomain (domain step skipped
                                  if only one domain is configured).
      - `/show_team_*`         → pick domain → pick team (team list is flattened
                                  across all subdomains of the chosen domain).

    Any single-choice step is auto-skipped. In-memory pending state; cleared on
    restart.
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
        # For subdomain/team reports, start from domain selection so the final
        # list stays scoped to one domain.
        if level in ("subdomain", "team"):
            domains = await self._load_domains()
            if not domains:
                return "Нет доступных доменов."
            if len(domains) == 1:
                return await self._ask_within_domain(chat_id, domains[0], level, action)
            return self._pend(chat_id, _PendingSelection(
                action=action, current_level="domain", final_level=level, choices=domains,
            ))

        # Domain-level commands: pick a domain (or skip if single).
        domains = await self._load_domains()
        if not domains:
            return "Нет доступных доменов."
        if len(domains) == 1:
            return await self._render_for(domains[0], "domain", action)
        return self._pend(chat_id, _PendingSelection(
            action=action, current_level="domain", final_level="domain", choices=domains,
        ))

    async def _ask_within_domain(
        self, chat_id: int, domain: Portfolio, final_level: Level, action: Action
    ) -> str:
        choices = await self._children_for(domain, final_level)
        if not choices:
            return f"В домене «{domain.summary}» нет {_LEVEL_NOUN[final_level]}."
        if len(choices) == 1:
            return await self._render_for(choices[0], final_level, action)
        return self._pend(chat_id, _PendingSelection(
            action=action, current_level=final_level, final_level=final_level, choices=choices,
        ))

    async def _resolve(self, chat_id: int, number: int) -> str:
        pending = self._pending.pop(chat_id)
        idx = number - 1
        if not (0 <= idx < len(pending.choices)):
            return f"Неверный номер. Введите от 1 до {len(pending.choices)}."
        selected = pending.choices[idx]

        if pending.current_level == pending.final_level:
            return await self._render_for(selected, pending.final_level, pending.action)

        # We just picked a domain; drill down to the final level inside it.
        return await self._ask_within_domain(chat_id, selected, pending.final_level, pending.action)

    def _pend(self, chat_id: int, selection: _PendingSelection) -> str:
        self._pending[chat_id] = selection
        lines = [_SELECTION_HEADER[selection.current_level], ""]
        lines.extend(f"{i + 1}. {p.summary}" for i, p in enumerate(selection.choices))
        lines.append("\nВведите номер:")
        return "\n".join(lines)

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

    async def _children_for(self, domain: Portfolio, final_level: Level) -> list[Portfolio]:
        if final_level == "subdomain":
            return await self._agg.list_subdomains(domain.id)
        # team: flatten teams across all subdomains of the domain.
        teams: list[Portfolio] = []
        for sub in await self._agg.list_subdomains(domain.id):
            teams.extend(await self._agg.list_teams(sub.id))
        return teams

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
