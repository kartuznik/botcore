"""Parsing of admin input: deadlines, channel lists, command arguments."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

MAX_WINNERS = 100
MAX_TITLE_LENGTH = 120
SKIP_WORDS = frozenset({"-", "нет", "no", "skip", "без", "без условия"})
_RELATIVE_RE = re.compile(r"^(\d+)\s*(m|min|м|мин|h|ч|d|д)$", re.IGNORECASE)
_UNIT_TO_DELTA = {
    "m": "minutes",
    "min": "minutes",
    "м": "minutes",
    "мин": "minutes",
    "h": "hours",
    "ч": "hours",
    "d": "days",
    "д": "days",
}
_DATE_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M", "%d.%m.%Y")


class DeadlineError(ValueError):
    """Base class for deadline problems. Never raised directly."""


class DeadlineFormatError(DeadlineError):
    """Input does not look like any supported deadline format."""


class DeadlinePastError(DeadlineError):
    """Input parsed fine but points at a moment that has already passed."""


@dataclass(frozen=True, slots=True)
class DemoArgs:
    """Arguments of /demodraw: generated participants or an explicit id list."""

    participants: int
    winners: int
    user_ids: tuple[int, ...] | None


def parse_positive_int(raw: str | None, maximum: int) -> int | None:
    if raw is None:
        return None
    candidate = raw.strip()
    if not candidate.isdigit():
        return None
    value = int(candidate)
    return value if 1 <= value <= maximum else None


def parse_deadline(raw: str, now: datetime) -> datetime:
    """Parse a deadline in UTC. A bare number means hours: '2' is now + 2h.

    Raises:
        DeadlineFormatError: the input matches none of the supported formats.
        DeadlinePastError: the input is a valid moment, but not in the future.
    """
    candidate = raw.strip()
    parsed = _parse_relative(candidate, now) or _parse_absolute(candidate)
    if parsed is None:
        raise DeadlineFormatError(candidate)
    if parsed <= now:
        raise DeadlinePastError(candidate)
    return parsed


def _parse_relative(candidate: str, now: datetime) -> datetime | None:
    if candidate.isdigit():
        return now + timedelta(hours=int(candidate))
    match = _RELATIVE_RE.match(candidate)
    if match is None:
        return None
    unit = _UNIT_TO_DELTA[match.group(2).lower()]
    return now + timedelta(**{unit: int(match.group(1))})


def _parse_absolute(candidate: str) -> datetime | None:
    for pattern in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(candidate, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
        return parsed.replace(hour=23, minute=59) if pattern == "%d.%m.%Y" else parsed
    return None


def parse_channels(raw: str) -> tuple[str, ...]:
    """Normalize a channel list: '@name', 't.me/name' and '-100…' are all accepted."""
    if raw.strip().lower() in SKIP_WORDS:
        return ()
    channels: list[str] = []
    for chunk in re.split(r"[,\s]+", raw.strip()):
        channel = _normalize_channel(chunk)
        if channel and channel not in channels:
            channels.append(channel)
    return tuple(channels)


def parse_demo_args(raw: str | None, default_participants: int) -> DemoArgs:
    """'/demodraw', '/demodraw 20', '/demodraw 20 3', '/demodraw 111,222,333 2'."""
    tokens = (raw or "").split()
    participants = default_participants
    winners = 1
    user_ids: tuple[int, ...] | None = None

    if tokens:
        head = tokens[0]
        if "," in head:
            user_ids = tuple(
                int(item) for item in head.split(",") if item.strip().lstrip("-").isdigit()
            )
            participants = len(user_ids)
        else:
            participants = parse_positive_int(head, 10_000) or default_participants
    if len(tokens) > 1:
        winners = parse_positive_int(tokens[1], MAX_WINNERS) or 1
    return DemoArgs(participants=participants, winners=winners, user_ids=user_ids)


def _normalize_channel(chunk: str) -> str:
    candidate = chunk.strip().rstrip("/")
    if not candidate:
        return ""
    if candidate.lstrip("-").isdigit():
        return candidate
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if candidate.lower().startswith(prefix):
            candidate = candidate[len(prefix) :]
            break
    candidate = candidate.lstrip("@")
    return f"@{candidate}" if candidate else ""
