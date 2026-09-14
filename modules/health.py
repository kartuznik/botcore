"""Health module: proves the wiring works end to end."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from core.logging_setup import get_logger
from core.registry import ModuleContext

MODULE_NAME = "health"

logger = get_logger(__name__)


def build_start_text(enabled_modules: Sequence[str]) -> str:
    modules = ", ".join(enabled_modules) if enabled_modules else "нет включённых модулей"
    return (
        f"Привет! Это botcore — каркас Telegram-бота.\nВключённые модули: {modules}\nСправка: /help"
    )


def build_help_text() -> str:
    return (
        "Доступные команды:\n/start — приветствие и список включённых модулей\n/help — эта справка"
    )


def build_unknown_text(text: str | None) -> str:
    if text is not None and text.startswith("/"):
        return "Пока не знаю такую команду. Посмотрите /help — там весь список."
    return "Принял сообщение, но обрабатывать его пока нечем. Начните с /help."


def create_router(context: ModuleContext) -> Router:
    """Build the health Router bound to the given module context."""
    modules = context.enabled_modules
    if MODULE_NAME in modules and modules[-1] != MODULE_NAME:
        logger.warning(
            "health is not last in MODULES (%s): its catch-all handler will shadow commands "
            "of the modules listed after it",
            ", ".join(modules),
        )
    router = Router(name=MODULE_NAME)

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        logger.info("/start from chat_id=%s", message.chat.id)
        await message.answer(build_start_text(context.enabled_modules))

    @router.message(Command("help"))
    async def handle_help(message: Message) -> None:
        logger.info("/help from chat_id=%s", message.chat.id)
        await message.answer(build_help_text())

    @router.message()
    async def handle_unknown(message: Message) -> None:
        logger.info("unhandled message from chat_id=%s", message.chat.id)
        await message.answer(build_unknown_text(message.text))

    return router
