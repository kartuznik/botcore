"""Cross-cutting middleware: update logging and a global error net."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from core.logging_setup import get_logger

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

DEFAULT_ERROR_TEXT = "Что-то сломалось на моей стороне. Я записал ошибку, попробуйте ещё раз позже."


def describe_event(event: TelegramObject) -> str:
    """Short, log-safe description of an incoming event."""
    if isinstance(event, Update):
        return f"update_id={event.update_id} type={event.event_type}"
    return type(event).__name__


class UpdateLoggingMiddleware(BaseMiddleware):
    """Logs every update before and after it is handled."""

    def __init__(self) -> None:
        self._logger = get_logger(__name__)

    # aiogram middleware contract returns whatever the handler returns.
    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        description = describe_event(event)
        self._logger.info("update received: %s", description)
        started = perf_counter()
        try:
            return await handler(event, data)
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            self._logger.info("update done: %s in %.1f ms", description, elapsed_ms)


class ErrorHandlingMiddleware(BaseMiddleware):
    """Catches handler exceptions, logs them and answers the user instead of dying."""

    def __init__(self, reply_text: str = DEFAULT_ERROR_TEXT) -> None:
        self._reply_text = reply_text
        self._logger = get_logger(__name__)

    # aiogram middleware contract returns whatever the handler returns.
    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        try:
            return await handler(event, data)
        except Exception:
            self._logger.exception("unhandled error while processing %s", describe_event(event))
            await self._notify(event)
            return None

    async def _notify(self, event: TelegramObject) -> None:
        message = self._extract_message(event)
        if message is None:
            return
        try:
            await message.answer(self._reply_text)
        except Exception:
            self._logger.exception("failed to deliver the error notice to the user")

    @staticmethod
    def _extract_message(event: TelegramObject) -> Message | None:
        if isinstance(event, Message):
            return event
        if isinstance(event, CallbackQuery):
            return event.message if isinstance(event.message, Message) else None
        if isinstance(event, Update):
            if event.message is not None:
                return event.message
            callback = event.callback_query
            if callback is not None and isinstance(callback.message, Message):
                return callback.message
        return None
