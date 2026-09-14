"""Domain types of the raffle module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RaffleStatus(StrEnum):
    """Lifecycle of a raffle."""

    OPEN = "open"
    DRAWN = "drawn"
    CANCELLED = "cancelled"


class JoinResult(StrEnum):
    """Outcome of an attempt to enter a raffle."""

    JOINED = "joined"
    DUPLICATE = "duplicate"
    CLOSED = "closed"
    EXPIRED = "expired"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class Raffle:
    id: int
    title: str
    winners_count: int
    deadline_at: datetime
    channels: tuple[str, ...]
    status: RaffleStatus
    created_by: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Participant:
    raffle_id: int
    user_id: int
    username: str | None
    joined_at: datetime

    @property
    def label(self) -> str:
        return f"@{self.username}" if self.username else f"id{self.user_id}"


@dataclass(frozen=True, slots=True)
class ExcludedParticipant:
    user_id: int
    reason: str


@dataclass(frozen=True, slots=True)
class RaffleSummary:
    raffle: Raffle
    participants_count: int


@dataclass(frozen=True, slots=True)
class DrawRecord:
    """Audit row: who was in the pool and who won."""

    id: int
    raffle_id: int
    drawn_at: datetime
    drawn_by: int
    participants_snapshot: tuple[int, ...]
    eligible_snapshot: tuple[int, ...]
    excluded_snapshot: tuple[ExcludedParticipant, ...]
    winners: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DrawOutcome:
    draw_id: int
    raffle: Raffle
    winners: tuple[Participant, ...]
    participants_count: int
    eligible_count: int
    excluded: tuple[ExcludedParticipant, ...]
