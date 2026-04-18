from enum import StrEnum


class BusinessStatus(StrEnum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


STATUS_EMOJI: dict[BusinessStatus, str] = {
    BusinessStatus.ON_TRACK: "\U0001F7E2",  # green circle
    BusinessStatus.AT_RISK: "\U0001F7E1",  # yellow circle
    BusinessStatus.BLOCKED: "\U0001F534",  # red circle
    BusinessStatus.UNKNOWN: "\u26AA",  # white circle
}


STATUS_LABEL_RU: dict[BusinessStatus, str] = {
    BusinessStatus.ON_TRACK: "По плану",
    BusinessStatus.AT_RISK: "Есть риски",
    BusinessStatus.BLOCKED: "Заблокирован",
    BusinessStatus.UNKNOWN: "Статус неизвестен или отсутствует",
}


# Confirmed live against the Tracker /v2/entities/project API:
# Tracker UI «По плану»      → "on_track"
# Tracker UI «Есть риски»    → "at_risk"
# Tracker UI «Заблокирован»  → "blocked"
# Any other value (draft, in_progress, launched, paused, ...) falls back to UNKNOWN.
TRACKER_STATUS_MAP: dict[str, BusinessStatus] = {
    "on_track": BusinessStatus.ON_TRACK,
    "at_risk": BusinessStatus.AT_RISK,
    "blocked": BusinessStatus.BLOCKED,
}


def map_tracker_status(entity_status: str | None) -> BusinessStatus:
    if not entity_status:
        return BusinessStatus.UNKNOWN
    return TRACKER_STATUS_MAP.get(entity_status.strip().lower(), BusinessStatus.UNKNOWN)
