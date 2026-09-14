"""The bot side of the API bridge: announcements and the automatic draw."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.storage import SqliteStorage
from modules.raffle.models import RaffleSource, RaffleStatus
from modules.raffle.watcher import RaffleWatcher
from tests.conftest import ADMIN_ID, FakeChecker, RaffleEnv, RecordingSender


@pytest.fixture
async def storage(tmp_path: Path) -> AsyncGenerator[SqliteStorage, None]:
    backend = SqliteStorage(tmp_path / "kv.db")
    try:
        yield backend
    finally:
        await backend.close()


def build_watcher(
    env: RaffleEnv,
    sender: RecordingSender,
    storage: SqliteStorage,
    *,
    now: Callable[[], datetime] | None = None,
    checker: FakeChecker | None = None,
) -> RaffleWatcher:
    return RaffleWatcher(
        service=env.live,
        sender=sender,
        checker=checker or FakeChecker(),
        storage=storage,
        admin_ids=frozenset({ADMIN_ID}),
        now=now or (lambda: datetime.now(UTC)),
    )


def after(minutes: int) -> Callable[[], datetime]:
    return lambda: datetime.now(UTC) + timedelta(minutes=minutes)


async def test_new_api_raffle_is_announced_once(
    raffle_env: RaffleEnv,
    storage: SqliteStorage,
) -> None:
    raffle = await raffle_env.live.create_raffle(
        title="Розыгрыш из API",
        winners_count=1,
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
        channels=(),
        created_by=ADMIN_ID,
        source=RaffleSource.API,
    )
    sender = RecordingSender()
    watcher = build_watcher(raffle_env, sender, storage)

    await watcher.tick()
    await watcher.tick()

    assert len(sender.messages) == 1
    chat_id, text = sender.messages[0]
    assert chat_id == ADMIN_ID
    assert f"#{raffle.id}" in text
    assert "Розыгрыш из API" in text


async def test_bot_created_raffles_are_not_announced(
    raffle_env: RaffleEnv,
    storage: SqliteStorage,
) -> None:
    await raffle_env.open_raffle(title="Создан в боте")
    sender = RecordingSender()

    await build_watcher(raffle_env, sender, storage).tick()

    assert sender.messages == []


async def test_api_raffle_is_drawn_after_the_deadline(
    raffle_env: RaffleEnv,
    storage: SqliteStorage,
) -> None:
    raffle = await raffle_env.live.create_raffle(
        title="Тираж по дедлайну",
        winners_count=1,
        deadline_at=datetime.now(UTC) + timedelta(minutes=30),
        channels=(),
        created_by=ADMIN_ID,
        source=RaffleSource.API,
    )
    await raffle_env.live.join(raffle.id, 501, "first")
    await raffle_env.live.join(raffle.id, 502, "second")
    sender = RecordingSender()

    await build_watcher(raffle_env, sender, storage).tick()
    still_open = await raffle_env.live.repository.get_raffle(raffle.id)
    assert still_open is not None
    assert still_open.status is RaffleStatus.OPEN

    await build_watcher(raffle_env, sender, storage, now=after(31)).tick()

    stored = await raffle_env.live.repository.get_raffle(raffle.id)
    assert stored is not None
    assert stored.status is RaffleStatus.DRAWN
    draws = await raffle_env.live.repository.list_draws(raffle.id)
    assert len(draws) == 1
    assert len(draws[0].winners) == 1
    assert draws[0].drawn_by == 0
    assert any("Автоматический тираж" in text for text in sender.texts)


async def test_draw_runs_only_once_per_raffle(
    raffle_env: RaffleEnv,
    storage: SqliteStorage,
) -> None:
    raffle = await raffle_env.live.create_raffle(
        title="Однократный тираж",
        winners_count=1,
        deadline_at=datetime.now(UTC) + timedelta(minutes=5),
        channels=(),
        created_by=ADMIN_ID,
        source=RaffleSource.API,
    )
    await raffle_env.live.join(raffle.id, 601, "one")
    sender = RecordingSender()
    watcher = build_watcher(raffle_env, sender, storage, now=after(6))

    await watcher.tick()
    await watcher.tick()

    assert len(await raffle_env.live.repository.list_draws(raffle.id)) == 1


async def test_raffle_without_participants_is_cancelled_and_reported(
    raffle_env: RaffleEnv,
    storage: SqliteStorage,
) -> None:
    raffle = await raffle_env.live.create_raffle(
        title="Без участников",
        winners_count=1,
        deadline_at=datetime.now(UTC) + timedelta(minutes=5),
        channels=(),
        created_by=ADMIN_ID,
        source=RaffleSource.API,
    )
    sender = RecordingSender()
    watcher = build_watcher(raffle_env, sender, storage, now=after(6))

    await watcher.tick()
    await watcher.tick()

    stored = await raffle_env.live.repository.get_raffle(raffle.id)
    assert stored is not None
    assert stored.status is RaffleStatus.CANCELLED
    assert sum("допущенных участников нет" in text for text in sender.texts) == 1


async def test_channel_error_keeps_the_raffle_open_and_warns_once(
    raffle_env: RaffleEnv,
    storage: SqliteStorage,
) -> None:
    raffle = await raffle_env.live.create_raffle(
        title="Бот не админ канала",
        winners_count=1,
        deadline_at=datetime.now(UTC) + timedelta(minutes=5),
        channels=("@closed_channel",),
        created_by=ADMIN_ID,
        source=RaffleSource.API,
    )
    await raffle_env.live.join(raffle.id, 701, "one")
    sender = RecordingSender()
    watcher = build_watcher(
        raffle_env,
        sender,
        storage,
        now=after(6),
        checker=FakeChecker(broken_channels=("@closed_channel",)),
    )

    await watcher.tick()
    await watcher.tick()

    stored = await raffle_env.live.repository.get_raffle(raffle.id)
    assert stored is not None
    assert stored.status is RaffleStatus.OPEN
    assert sum("Не удалось проверить подписку" in text for text in sender.texts) == 1


async def test_a_broken_notification_does_not_stop_the_watcher(
    raffle_env: RaffleEnv,
    storage: SqliteStorage,
) -> None:
    class BrokenSender(RecordingSender):
        async def send_message(self, chat_id: int, text: str) -> object:
            raise RuntimeError("chat not found")

    raffle = await raffle_env.live.create_raffle(
        title="Админ не запускал бота",
        winners_count=1,
        deadline_at=datetime.now(UTC) + timedelta(minutes=5),
        channels=(),
        created_by=ADMIN_ID,
        source=RaffleSource.API,
    )
    await raffle_env.live.join(raffle.id, 801, "one")

    await build_watcher(raffle_env, BrokenSender(), storage, now=after(6)).tick()

    stored = await raffle_env.live.repository.get_raffle(raffle.id)
    assert stored is not None
    assert stored.status is RaffleStatus.DRAWN
