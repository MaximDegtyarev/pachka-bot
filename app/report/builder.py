from __future__ import annotations

from dataclasses import dataclass

from app.status.mapping import STATUS_EMOJI, STATUS_LABEL_RU, BusinessStatus
from app.status.parser import WeeklyStatus
from app.tracker.models import Portfolio, Project


@dataclass(frozen=True)
class ProjectSummary:
    """Everything the builder needs to render one project row.

    Produced by the aggregator; the builder is pure.
    `weekly_status` may be set even when `is_stale` is True — per §7.2 we still
    show the last comment as reference, but `business_status` is UNKNOWN.
    """

    project: Project
    weekly_status: WeeklyStatus | None
    business_status: BusinessStatus
    is_stale: bool
    project_url: str


HELP_TEXT = (
    "**Команды бота**\n\n"
    "- `/show_domain_report` — отчёт по домену\n"
    "- `/show_subdomain_report` — отчёт по поддомену\n"
    "- `/show_team_report` — отчёт по команде\n"
    "- `/show_domain_list` — список доменов\n"
    "- `/show_subdomain_list` — список поддоменов\n"
    "- `/show_team_list` — список команд\n"
    "- `/show_domain_risk` — проекты с рисками в домене\n"
    "- `/show_subdomain_risk` — проекты с рисками в поддомене\n"
    "- `/show_team_risk` — проекты с рисками в команде\n"
    "- `/show_domain_blocked` — заблокированные проекты в домене\n"
    "- `/show_subdomain_blocked` — заблокированные проекты в поддомене\n"
    "- `/show_team_blocked` — заблокированные проекты в команде\n"
    "- `/show_domain_on_track` — проекты по плану в домене\n"
    "- `/show_subdomain_on_track` — проекты по плану в поддомене\n"
    "- `/show_team_on_track` — проекты по плану в команде\n"
    "- `/help` — эта справка"
)


def render_help() -> str:
    return HELP_TEXT


def render_list(title: str, portfolios: list[Portfolio], *, web_base: str | None = None) -> str:
    if not portfolios:
        return f"**{title}**\n\n_Нет портфелей._"
    lines = [f"**{title}**", ""]
    for p in portfolios:
        if web_base:
            url = f"{web_base.rstrip('/')}/pages/portfolios/{p.id}/projects"
            lines.append(f"- [{p.summary}]({url})")
        else:
            lines.append(f"- {p.summary}")
    return "\n".join(lines)


def render_report(title: str, summaries: list[ProjectSummary]) -> str:
    return _render_blocks(title, summaries, empty_msg="Нет проектов.")


def render_risk(title: str, summaries: list[ProjectSummary]) -> str:
    filtered = [s for s in summaries if s.business_status == BusinessStatus.AT_RISK]
    return _render_blocks(title, filtered, empty_msg="Проектов с рисками нет.")


def render_blocked(title: str, summaries: list[ProjectSummary]) -> str:
    filtered = [s for s in summaries if s.business_status == BusinessStatus.BLOCKED]
    return _render_blocks(title, filtered, empty_msg="Заблокированных проектов нет.")


def render_on_track(title: str, summaries: list[ProjectSummary]) -> str:
    filtered = [s for s in summaries if s.business_status == BusinessStatus.ON_TRACK]
    return _render_blocks(title, filtered, empty_msg="Проектов по плану нет.")


def _render_blocks(title: str, summaries: list[ProjectSummary], *, empty_msg: str) -> str:
    if not summaries:
        return f"**{title}**\n\n_{empty_msg}_"
    blocks = [f"**{title}**", ""]
    for s in summaries:
        blocks.append(_render_project_block(s))
        blocks.append("")
    return "\n".join(blocks).rstrip()


def _render_project_block(s: ProjectSummary) -> str:
    project = s.project
    emoji = STATUS_EMOJI[s.business_status]
    label = STATUS_LABEL_RU[s.business_status]
    lead = project.lead.display if project.lead and project.lead.display else "—"

    lines = [
        f"**[{project.summary}]({s.project_url})**",
        f"- Ответственный: {lead}",
        f"- Статус: {emoji} {label}",
    ]

    if project.end:
        lines.append(f"- Дедлайн: {project.end}")

    ws = s.weekly_status
    comments = ws.comments if ws and ws.comments else None
    if comments:
        lines.append("- Комментарий:")
        lines.append(_indent(comments, "  "))
    else:
        lines.append("- Комментарий: —")

    if ws and ws.deadline:
        lines.append(f"- DL по решению: {ws.deadline}")

    if s.is_stale:
        if ws is None:
            lines.append("- _Статус не заполнен (добавьте комментарий с #WeeklyStatus)._")
        else:
            lines.append("- _Данные устарели (старше 6 дней)._")
    return "\n".join(lines)


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else prefix.rstrip() for line in text.splitlines())
