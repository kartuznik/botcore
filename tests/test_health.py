"""Health module behaviour through a mocked update."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage

from core.registry import ModuleContext
from modules.health import create_router
from tests.conftest import RecordingSession, make_update

CONTEXT = ModuleContext(enabled_modules=("health", "future"))


def make_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(CONTEXT))
    return dispatcher


async def test_start_greets_and_lists_enabled_modules(
    bot: Bot,
    session: RecordingSession,
) -> None:
    await make_dispatcher().feed_update(bot, make_update("/start"))

    assert len(session.requests) == 1
    method = session.requests[0]
    assert isinstance(method, SendMessage)
    assert "health" in method.text
    assert "future" in method.text


async def test_help_lists_commands(bot: Bot, session: RecordingSession) -> None:
    await make_dispatcher().feed_update(bot, make_update("/help"))

    assert "/start" in session.requests[0].text


async def test_unknown_command_gets_polite_answer(bot: Bot, session: RecordingSession) -> None:
    await make_dispatcher().feed_update(bot, make_update("/nope"))

    assert "/help" in session.requests[0].text
