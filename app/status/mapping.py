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


# Mapping from Yandex Tracker status key/name to business status.
# TODO: fill with the actual status keys from the target Tracker org.
TRACKER_STATUS_MAP: dict[str, BusinessStatus] = {
    "on_track": BusinessStatus.ON_TRACK,
    "по плану": BusinessStatus.ON_TRACK,
    "at_risk": BusinessStatus.AT_RISK,
    "есть риски": BusinessStatus.AT_RISK,
    "blocked": BusinessStatus.BLOCKED,
    "заблокирован": BusinessStatus.BLOCKED,
}


def map_tracker_status(value: str | None) -> BusinessStatus:
    if not value:
        return BusinessStatus.UNKNOWN
    return TRACKER_STATUS_MAP.get(value.strip().lower(), BusinessStatus.UNKNOWN)
