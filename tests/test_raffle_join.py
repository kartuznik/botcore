"""Entering a raffle: open window, one entry per user, closed raffles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from modules.raffle.models import JoinResult, RaffleStatus
from tests.conftest import ADMIN_ID, RaffleEnv


async def test_join_inside_the_window(raffle_env: RaffleEnv) -> None:
    raffle = await raffle_env.open_raffle()

    result = await raffle_env.live.join(raffle.id, user_id=101, username="first")

    assert result is JoinResult.JOINED
    participants = await raffle_env.live.repository.list_participants(raffle.id)
    assert [participant.user_id for participant in participants] == [101]


async def test_second_entry_of_the_same_user_is_rejected(raffle_env: RaffleEnv) -> None:
    raffle = await raffle_env.open_raffle()
    await raffle_env.live.join(raffle.id, user_id=101, username="first")

    result = await raffle_env.live.join(raffle.id, user_id=101, username="first-renamed")

    assert result is JoinResult.DUPLICATE
    assert await raffle_env.live.repository.count_participants(raffle.id) == 1


async def test_join_after_the_deadline_is_rejected(raffle_env: RaffleEnv) -> None:
    raffle = await raffle_env.live.create_raffle(
        title="Уже закончился",
        winners_count=1,
        deadline_at=datetime.now(UTC) - timedelta(minutes=5),
        channels=(),
        created_by=ADMIN_ID,
    )

    result = await raffle_env.live.join(raffle.id, user_id=101, username="late")

    assert result is JoinResult.EXPIRED
    assert await raffle_env.live.repository.count_participants(raffle.id) == 0


async def test_join_closed_raffle_is_rejected(raffle_env: RaffleEnv) -> None:
    raffle = await raffle_env.open_raffle()
    await raffle_env.live.repository.set_status(raffle.id, RaffleStatus.DRAWN)

    result = await raffle_env.live.join(raffle.id, user_id=101, username="late")

    assert result is JoinResult.CLOSED
    assert await raffle_env.live.repository.count_participants(raffle.id) == 0


async def test_join_unknown_raffle_is_rejected(raffle_env: RaffleEnv) -> None:
    assert await raffle_env.live.join(4242, user_id=101, username="lost") is JoinResult.NOT_FOUND
