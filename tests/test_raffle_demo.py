"""Demo mode runs the same machinery over its own tables."""

from __future__ import annotations

from modules.raffle.service import run_demo_draw
from tests.conftest import ADMIN_ID, RaffleEnv


async def test_demo_draw_leaves_live_tables_empty(raffle_env: RaffleEnv) -> None:
    outcome = await run_demo_draw(raffle_env.demo, participants=8, winners=2, created_by=ADMIN_ID)

    assert len({winner.user_id for winner in outcome.winners}) == 2
    assert outcome.participants_count == 8

    demo_repository = raffle_env.demo.repository
    assert await demo_repository.count_raffles() == 1
    assert await demo_repository.count_participants() == 8
    assert await demo_repository.count_draws() == 1

    live_repository = raffle_env.live.repository
    assert await live_repository.count_raffles() == 0
    assert await live_repository.count_participants() == 0
    assert await live_repository.count_draws() == 0


async def test_demo_draw_accepts_an_explicit_participant_list(raffle_env: RaffleEnv) -> None:
    outcome = await run_demo_draw(
        raffle_env.demo,
        winners=1,
        created_by=ADMIN_ID,
        user_ids=[11, 22, 33],
    )

    assert outcome.participants_count == 3
    assert outcome.winners[0].user_id in {11, 22, 33}
    assert await raffle_env.live.repository.count_participants() == 0


async def test_demo_tables_are_named_apart_from_live_ones(raffle_env: RaffleEnv) -> None:
    assert raffle_env.demo.repository.tables.raffles == "demo_raffles"
    assert raffle_env.demo.repository.tables.participants == "demo_participants"
    assert raffle_env.demo.repository.tables.draws == "demo_draws"
    assert raffle_env.live.repository.tables.raffles == "raffles"
