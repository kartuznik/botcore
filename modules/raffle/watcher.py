"""Background task: the bot picks up raffles created through the HTTP API.

The API only writes rows into the shared database. Everything that needs Telegram —
notifying the admin and running the draw when the deadline passes — happens here,
inside the bot process, because only it owns the Telegram session.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from typing import Protocol

from core.logging_setup import get_logger
from core.storage import StorageInterface
from modules.raffle.errors import (
    ChannelAccessError,
    NoEligibleParticipantsError,
    RaffleError,
)
from modules.raffle.models import Raffle, RaffleSource, RaffleStatus
from modules.raffle.service import RaffleService, SubscriptionChecker, utcnow
from modules.raffle.texts import (
    render_auto_draw,
    render_auto_draw_cancelled,
    render_channel_error,
    render_new_api_raffle,
)

WATERMARK_KEY = "raffle:watcher:last_announced_id"
ERROR_KEY_TEMPLATE = "raffle:watcher:error:{raffle_id}"
AUTO_DRAW_ACTOR = 0

logger = get_logger(__name__)


class MessageSender(Protocol):
    """The slice of aiogram's Bot the watcher actually needs."""

    async def send_message(self, chat_id: int, text: str) -> object: ...


class RaffleWatcher:
    """Polls the shared database for API-created raffles and reacts to them."""

    def __init__(
        self,
        *,
        service: RaffleService,
        sender: MessageSender,
        checker: SubscriptionChecker,
        storage: StorageInterface,
        admin_ids: frozenset[int],
        interval: float = 10.0,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._service = service
        self._sender = sender
        self._checker = checker
        self._storage = storage
        self._admin_ids = admin_ids
        self._interval = interval
        self._now = now
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="raffle-watcher")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        logger.info("raffle watcher stopped")

    async def tick(self) -> None:
        """One pass: announce fresh raffles, then draw the ones past their deadline."""
        await self._announce_new()
        await self._draw_due()

    async def _loop(self) -> None:
        logger.info("raffle watcher started, interval=%.1fs", self._interval)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("raffle watcher tick failed, retrying next interval")
            await asyncio.sleep(self._interval)

    async def _announce_new(self) -> None:
        last_announced = await self._read_watermark()
        fresh = [
            raffle
            for raffle in await self._service.repository.list_raffles()
            if raffle.source is RaffleSource.API and raffle.id > last_announced
        ]
        if not fresh:
            return
        for raffle in sorted(fresh, key=lambda item: item.id):
            logger.info("announcing api raffle id=%s", raffle.id)
            await self._notify(render_new_api_raffle(raffle))
        await self._storage.set(WATERMARK_KEY, str(max(raffle.id for raffle in fresh)))

    async def _draw_due(self) -> None:
        now = self._now()
        for raffle in await self._service.repository.list_raffles():
            if raffle.source is not RaffleSource.API or raffle.status is not RaffleStatus.OPEN:
                continue
            if raffle.deadline_at > now:
                continue
            await self._draw(raffle)

    async def _draw(self, raffle: Raffle) -> None:
        try:
            outcome = await self._service.draw(raffle.id, AUTO_DRAW_ACTOR, self._checker)
        except NoEligibleParticipantsError:
            # Nobody can join after the deadline, so retrying would loop forever.
            await self._service.repository.set_status(raffle.id, RaffleStatus.CANCELLED)
            logger.info("auto draw cancelled, nobody eligible: raffle=%s", raffle.id)
            await self._notify(render_auto_draw_cancelled(raffle))
        except ChannelAccessError as error:
            # Rights can still be granted, so keep the raffle open but nag only once.
            logger.warning("auto draw blocked: raffle=%s channel=%s", raffle.id, error.channel)
            await self._notify_once(raffle.id, render_channel_error(error))
        except RaffleError:
            logger.exception("auto draw failed: raffle=%s", raffle.id)
        else:
            logger.info("auto draw done: raffle=%s winners=%s", raffle.id, len(outcome.winners))
            await self._notify(render_auto_draw(outcome))

    async def _read_watermark(self) -> int:
        raw = await self._storage.get(WATERMARK_KEY)
        if raw is None or not raw.isdigit():
            return 0
        return int(raw)

    async def _notify_once(self, raffle_id: int, text: str) -> None:
        key = ERROR_KEY_TEMPLATE.format(raffle_id=raffle_id)
        if await self._storage.get(key) is not None:
            return
        await self._storage.set(key, "reported")
        await self._notify(text)

    async def _notify(self, text: str) -> None:
        for chat_id in sorted(self._admin_ids):
            try:
                await self._sender.send_message(chat_id=chat_id, text=text)
            except Exception:
                # A failed notification must never kill the background loop.
                logger.warning("cannot notify admin %s: has the chat been started?", chat_id)
