from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class WeeklyStatus:
    """Parsed #WeeklyStatus comment body."""

    comments: str
    deadline: str | None
    created_at: datetime
    raw: str

    def is_fresh(self, now: datetime, freshness_days: int) -> bool:
        return (now - self.created_at) <= timedelta(days=freshness_days)


_TAG_RE = re.compile(r"\\?#WeeklyStatus\b", re.IGNORECASE)
_COMMENTS_RE = re.compile(r"^\s*Comments\s*:\s*", re.IGNORECASE)
_DEADLINE_RE = re.compile(r"^\s*DL\s*по\s*решению\s*:\s*", re.IGNORECASE)


def has_weekly_status_tag(text: str) -> bool:
    return bool(_TAG_RE.search(text or ""))


def parse_weekly_status(text: str, created_at: datetime) -> WeeklyStatus | None:
    """Parse a comment body into a WeeklyStatus, or None if tag is missing.

    Expected template (fields order is not strict, labels are case-insensitive):

        #WeeklyStatus
        Comments: <free text, may be multiline>
        DL по решению: <deadline>
    """
    if not text or not has_weekly_status_tag(text):
        return None

    lines = text.splitlines()
    comments_lines: list[str] = []
    deadline: str | None = None
    current: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip()
        if _TAG_RE.search(line) and not _COMMENTS_RE.match(line) and not _DEADLINE_RE.match(line):
            # Skip the tag line itself
            current = None
            continue
        if _COMMENTS_RE.match(line):
            current = "comments"
            rest = _COMMENTS_RE.sub("", line)
            if rest:
                comments_lines.append(rest)
            continue
        if _DEADLINE_RE.match(line):
            current = "deadline"
            rest = _DEADLINE_RE.sub("", line).strip()
            deadline = rest or None
            continue
        if current == "comments":
            comments_lines.append(raw_line)
        # Unlabeled lines outside known sections are ignored

    return WeeklyStatus(
        comments="\n".join(comments_lines).strip(),
        deadline=deadline,
        created_at=created_at,
        raw=text,
    )


def pick_latest_weekly_status(
    comments: list[tuple[str, datetime]],
) -> WeeklyStatus | None:
    """Given [(body, created_at), ...], return the latest successfully parsed WeeklyStatus."""
    parsed: list[WeeklyStatus] = []
    for body, created_at in comments:
        ws = parse_weekly_status(body, created_at)
        if ws is not None:
            parsed.append(ws)
    if not parsed:
        return None
    return max(parsed, key=lambda w: w.created_at)


def utcnow() -> datetime:
    return datetime.now(tz=UTC)
