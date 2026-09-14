"""Raffle rules: who may enter, who is eligible at draw time, who wins."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from modules.raffle.errors import (
    NoEligibleParticipantsError,
    RaffleClosedError,
    RaffleNotFoundError,
)
from modules.raffle.models import (
    DrawOutcome,
    ExcludedParticipant,
    JoinResult,
    Participant,
    Raffle,
    RaffleSource,
    RaffleStatus,
    RaffleSummary,
)
from modules.raffle.repository import RaffleRepository

UNSUBSCRIBED_REASON = "не подписан на канал {channel}"
DEMO_USER_ID_BASE = 900_000_000


class SubscriptionChecker(Protocol):
    """Answers whether a user is currently subscribed to a channel."""

    async def is_subscribed(self, channel: str, user_id: int) -> bool: ...


class AllowAllChecker:
    """Checker for raffles without channel conditions and for demo draws."""

    async def is_subscribed(self, channel: str, user_id: int) -> bool:
        return True


def utcnow() -> datetime:
    return datetime.now(UTC)


class RaffleService:
    """One instance per table set: one for live raffles, one for demo ones."""

    def __init__(
        self,
        repository: RaffleRepository,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repository = repository
        self._now = now

    @property
    def repository(self) -> RaffleRepository:
        return self._repository

    async def create_raffle(
        self,
        *,
        title: str,
        winners_count: int,
        deadline_at: datetime,
        channels: Sequence[str],
        created_by: int,
        source: RaffleSource = RaffleSource.BOT,
    ) -> Raffle:
        return await self._repository.create_raffle(
            title=title,
            winners_count=winners_count,
            deadline_at=deadline_at,
            channels=channels,
            created_by=created_by,
            created_at=self._now(),
            source=source,
        )

    async def list_raffles(self) -> list[RaffleSummary]:
        raffles = await self._repository.list_raffles()
        return [
            RaffleSummary(
                raffle=raffle,
                participants_count=await self._repository.count_participants(raffle.id),
            )
            for raffle in raffles
        ]

    async def join(self, raffle_id: int, user_id: int, username: str | None) -> JoinResult:
        """Enter a raffle: only while it is open and only once per user."""
        raffle = await self._repository.get_raffle(raffle_id)
        if raffle is None:
            return JoinResult.NOT_FOUND
        if raffle.status is not RaffleStatus.OPEN:
            return JoinResult.CLOSED
        if self._now() >= raffle.deadline_at:
            return JoinResult.EXPIRED
        added = await self._repository.add_participant(
            raffle_id=raffle_id,
            user_id=user_id,
            username=username,
            joined_at=self._now(),
        )
        return JoinResult.JOINED if added else JoinResult.DUPLICATE

    async def draw(
        self,
        raffle_id: int,
        drawn_by: int,
        checker: SubscriptionChecker,
    ) -> DrawOutcome:
        """Pick winners among participants that still satisfy the conditions.

        Raises ChannelAccessError before touching any data when the bot cannot read
        channel membership, so a misconfigured channel never half-finishes a draw.
        """
        raffle = await self._repository.get_raffle(raffle_id)
        if raffle is None:
            raise RaffleNotFoundError(raffle_id)
        if raffle.status is not RaffleStatus.OPEN:
            raise RaffleClosedError(raffle_id, raffle.status.value)

        participants = await self._repository.list_participants(raffle_id)
        eligible: list[Participant] = []
        excluded: list[ExcludedParticipant] = []
        for participant in participants:
            reason = await self._rejection_reason(participant, raffle.channels, checker)
            if reason is None:
                eligible.append(participant)
            else:
                excluded.append(ExcludedParticipant(participant.user_id, reason))

        if not eligible:
            raise NoEligibleParticipantsError(raffle_id)

        winners_count = min(raffle.winners_count, len(eligible))
        winners = tuple(secrets.SystemRandom().sample(eligible, winners_count))

        draw_id = await self._repository.record_draw(
            raffle_id=raffle_id,
            drawn_at=self._now(),
            drawn_by=drawn_by,
            participants=participants,
            eligible=eligible,
            excluded=excluded,
            winners=winners,
        )
        await self._repository.set_status(raffle_id, RaffleStatus.DRAWN)

        return DrawOutcome(
            draw_id=draw_id,
            raffle=raffle,
            winners=winners,
            participants_count=len(participants),
            eligible_count=len(eligible),
            excluded=tuple(excluded),
        )

    async def _rejection_reason(
        self,
        participant: Participant,
        channels: Sequence[str],
        checker: SubscriptionChecker,
    ) -> str | None:
        for channel in channels:
            if not await checker.is_subscribed(channel, participant.user_id):
                return UNSUBSCRIBED_REASON.format(channel=channel)
        return None


async def run_demo_draw(
    service: RaffleService,
    *,
    participants: int = 10,
    winners: int = 1,
    created_by: int,
    user_ids: Sequence[int] | None = None,
) -> DrawOutcome:
    """Full raffle cycle over the demo tables: create, fill, draw.

    Participants are generated by default, or taken from `user_ids` when a list is supplied.
    """
    raffle = await service.create_raffle(
        title=f"Демо-розыгрыш {utcnow():%Y-%m-%d %H:%M}",
        winners_count=winners,
        deadline_at=utcnow() + timedelta(hours=1),
        channels=(),
        created_by=created_by,
    )
    ids = (
        list(user_ids)
        if user_ids is not None
        else [DEMO_USER_ID_BASE + index for index in range(1, participants + 1)]
    )
    for index, user_id in enumerate(ids, start=1):
        await service.join(raffle.id, user_id, f"demo_user_{index}")
    return await service.draw(raffle.id, created_by, AllowAllChecker())
