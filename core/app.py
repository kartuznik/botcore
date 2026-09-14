"""Composition root: wires config, middleware, modules and the polling loop."""

from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

from aiogram import Bot, Dispatcher

from core.config import Settings
from core.logging_setup import get_logger
from core.middleware import ErrorHandlingMiddleware, UpdateLoggingMiddleware
from core.registry import ModuleContext, ModuleRegistry
from core.storage import StorageInterface

logger = get_logger(__name__)

STORAGE_KEY = "storage"


class BotApp:
    """Owns the bot lifecycle: build, run, shut down cleanly."""

    def __init__(
        self,
        settings: Settings,
        registry: ModuleRegistry,
        storage: StorageInterface,
        bot: Bot | None = None,
        dispatcher: Dispatcher | None = None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._storage = storage
        self._bot = bot if bot is not None else Bot(token=settings.bot_token)
        self._dispatcher = dispatcher if dispatcher is not None else Dispatcher()
        self._stop_event = asyncio.Event()
        self._configured = False

    @property
    def bot(self) -> Bot:
        return self._bot

    @property
    def dispatcher(self) -> Dispatcher:
        return self._dispatcher

    def setup(self) -> None:
        """Attach middleware, publish shared dependencies and include module routers."""
        if self._configured:
            return

        # Error net is registered first so it wraps logging and every module handler.
        self._dispatcher.update.outer_middleware(ErrorHandlingMiddleware())
        self._dispatcher.update.outer_middleware(UpdateLoggingMiddleware())
        self._dispatcher[STORAGE_KEY] = self._storage

        context = ModuleContext(enabled_modules=self._settings.modules)
        for name in self._settings.modules:
            self._dispatcher.include_router(self._registry.create(name, context))
            logger.info("module registered: %s", name)

        self._configured = True

    async def run(self) -> None:
        """Run polling until a stop signal arrives, then drain in-flight updates."""
        try:
            self.setup()
            self._install_signal_handlers()
            logger.info("starting polling: modules=%s", ", ".join(self._settings.modules))

            polling = asyncio.create_task(self._poll(), name="botcore-polling")
            stopper = asyncio.create_task(self._wait_for_stop(), name="botcore-stop")
            done, _pending = await asyncio.wait(
                {polling, stopper},
                return_when=asyncio.FIRST_COMPLETED,
            )
            stopper.cancel()
            with suppress(asyncio.CancelledError):
                await stopper

            if polling not in done:
                logger.info("stop requested, waiting for in-flight updates")
                await self._dispatcher.stop_polling()
            await polling
        finally:
            await self.aclose()

    def request_stop(self) -> None:
        """Ask the polling loop to finish after the current updates are handled."""
        self._stop_event.set()

    async def aclose(self) -> None:
        """Release storage and the Telegram session; never raises."""
        try:
            await self._storage.close()
        except Exception:
            logger.exception("failed to close storage")
        try:
            await self._bot.session.close()
        except Exception:
            logger.exception("failed to close the bot session")
        logger.info("shutdown complete")

    async def _poll(self) -> None:
        await self._dispatcher.start_polling(self._bot, handle_signals=False)

    async def _wait_for_stop(self) -> None:
        await self._stop_event.wait()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.request_stop)
