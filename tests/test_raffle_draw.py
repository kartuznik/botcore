"""Draw rules: eligibility, unique winners, audit trail and channel access errors."""

from __future__ import annotations

import pytest

from modules.raffle.errors import (
    ChannelAccessError,
    NoEligibleParticipantsError,
    RaffleClosedError,
    RaffleNotFoundError,
)
from modules.raffle.models import RaffleStatus
from tests.conftest import ADMIN_ID, FakeChecker, RaffleEnv

CHANNEL = "@demo_channel"


async def _fill(env: RaffleEnv, raffle_id: int, user_ids: range | list[int]) -> None:
    for user_id in user_ids:
        await env.live.join(raffle_id, user_id, f"user{user_id}")


async def test_winners_are_unique_and_match_the_requested_count(raffle_env: RaffleEnv) -> None:
    for _ in range(5):
        raffle = await raffle_env.open_raffle(winners=3)
        await _fill(raffle_env, raffle.id, range(101, 111))

        outcome = await raffle_env.live.draw(raffle.id, ADMIN_ID, FakeChecker())

        winner_ids = [winner.user_id for winner in outcome.winners]
        assert len(winner_ids) == 3
        assert len(set(winner_ids)) == 3
        assert set(winner_ids) <= set(range(101, 111))


async def test_unsubscribed_participant_is_excluded(raffle_env: RaffleEnv) -> None:
    raffle = await raffle_env.open_raffle(winners=2, channels=(CHANNEL,))
    await _fill(raffle_env, raffle.id, [101, 102, 103])
    checker = FakeChecker(subscribed={101, 102})  # 103 unsubscribed before the draw

    outcome = await raffle_env.live.draw(raffle.id, ADMIN_ID, checker)

    assert {winner.user_id for winner in outcome.winners} == {101, 102}
    assert outcome.participants_count == 3
    assert outcome.eligible_count == 2
    assert [item.user_id for item in outcome.excluded] == [103]
    assert CHANNEL in outcome.excluded[0].reason


async def test_draw_is_logged_with_full_snapshot(raffle_env: RaffleEnv) -> None:
    raffle = await raffle_env.open_raffle(winners=1, channels=(CHANNEL,))
    await _fill(raffle_env, raffle.id, [101, 102, 103])

    outcome = await raffle_env.live.draw(raffle.id, ADMIN_ID, FakeChecker(subscribed={101, 102}))

    records = await raffle_env.live.repository.list_draws(raffle.id)
    assert len(records) == 1
    record = records[0]
    assert record.id == outcome.draw_id
    assert record.drawn_by == ADMIN_ID
    assert record.participants_snapshot == (101, 102, 103)
    assert record.eligible_snapshot == (101, 102)
    assert [item.user_id for item in record.excluded_snapshot] == [103]
    assert record.winners == tuple(winner.user_id for winner in outcome.winners)


async def test_channel_without_bot_admin_rights_does_not_start_a_draw(
    raffle_env: RaffleEnv,
) -> None:
    raffle = await raffle_env.open_raffle(winners=1, channels=(CHANNEL,))
    await _fill(raffle_env, raffle.id, [101, 102])

    with pytest.raises(ChannelAccessError) as error_info:
        await raffle_env.live.draw(raffle.id, ADMIN_ID, FakeChecker(broken_channels={CHANNEL}))

    assert error_info.value.channel == CHANNEL
    stored = await raffle_env.live.repository.get_raffle(raffle.id)
    assert stored is not None
    assert stored.status is RaffleStatus.OPEN  # raffle stays open, admin can retry
    assert await raffle_env.live.repository.count_draws() == 0


async def test_raffle_cannot_be_drawn_twice(raffle_env: RaffleEnv) -> None:
    raffle = await raffle_env.open_raffle(winners=1)
    await _fill(raffle_env, raffle.id, [101, 102])
    await raffle_env.live.draw(raffle.id, ADMIN_ID, FakeChecker())

    with pytest.raises(RaffleClosedError):
        await raffle_env.live.draw(raffle.id, ADMIN_ID, FakeChecker())

    assert await raffle_env.live.repository.count_draws() == 1


async def test_draw_without_eligible_participants_fails_loudly(raffle_env: RaffleEnv) -> None:
    raffle = await raffle_env.open_raffle(winners=1, channels=(CHANNEL,))
    await _fill(raffle_env, raffle.id, [101, 102])

    with pytest.raises(NoEligibleParticipantsError):
        await raffle_env.live.draw(raffle.id, ADMIN_ID, FakeChecker(subscribed=set()))

    stored = await raffle_env.live.repository.get_raffle(raffle.id)
    assert stored is not None
    assert stored.status is RaffleStatus.OPEN


async def test_fewer_eligible_than_slots_draws_everyone_left(raffle_env: RaffleEnv) -> None:
    raffle = await raffle_env.open_raffle(winners=5, channels=(CHANNEL,))
    await _fill(raffle_env, raffle.id, [101, 102, 103])

    outcome = await raffle_env.live.draw(raffle.id, ADMIN_ID, FakeChecker(subscribed={101, 103}))

    assert {winner.user_id for winner in outcome.winners} == {101, 103}


async def test_unknown_raffle_cannot_be_drawn(raffle_env: RaffleEnv) -> None:
    with pytest.raises(RaffleNotFoundError):
        await raffle_env.live.draw(4242, ADMIN_ID, FakeChecker())
