"""Raffle module router: commands, wiring and soft-disable without RAFFLE_ADMIN_ID."""

from __future__ import annotations

import os

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from core.logging_setup import get_logger
from core.registry import ModuleContext
from modules.raffle.config import DEFAULT_DEMO_PARTICIPANTS, RaffleConfig, load_raffle_config
from modules.raffle.errors import ChannelAccessError, RaffleError
from modules.raffle.form import register_new_raffle_form
from modules.raffle.parsing import parse_demo_args, parse_positive_int
from modules.raffle.repository import DEMO_TABLES, LIVE_TABLES, RaffleDatabase, RaffleRepository
from modules.raffle.service import RaffleService, run_demo_draw
from modules.raffle.subscriptions import TelegramSubscriptionChecker
from modules.raffle.texts import (
    ADMIN_ONLY,
    DRAW_USAGE,
    JOIN_TEXTS,
    JOIN_USAGE,
    render_channel_error,
    render_demo_outcome,
    render_draw_outcome,
    render_raffle_list,
)

MODULE_NAME = "raffle"
MAX_RAFFLE_ID = 10_000_000
DISABLED_MESSAGE = (
    "raffle module is disabled: RAFFLE_ADMIN_ID is not set, the bot starts without it"
)

logger = get_logger(__name__)


def create_router(context: ModuleContext) -> Router:
    """Build the raffle router; returns an empty one when the module is not configured."""
    router = Router(name=MODULE_NAME)
    config = load_raffle_config(os.environ)
    if config is None:
        logger.warning(DISABLED_MESSAGE)
        return router

    database = RaffleDatabase(config.database_path)
    live = RaffleService(RaffleRepository(database, LIVE_TABLES))
    demo = RaffleService(RaffleRepository(database, DEMO_TABLES))

    async def prepare_tables() -> None:
        await live.repository.init()
        await demo.repository.init()
        logger.info("raffle tables ready in %s", config.database_path)

    router.startup.register(prepare_tables)
    router.shutdown.register(database.close)

    register_new_raffle_form(router, service=live, admin_ids=config.admin_ids)
    _register_commands(router, live=live, demo=demo, config=config)
    logger.info("raffle module enabled for %s admin(s)", len(config.admin_ids))
    return router


def _register_commands(
    router: Router,
    *,
    live: RaffleService,
    demo: RaffleService,
    config: RaffleConfig,
) -> None:
    def is_admin(message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in config.admin_ids

    @router.message(Command("raffles"))
    async def handle_raffles(message: Message) -> None:
        await message.answer(render_raffle_list(await live.list_raffles()))

    @router.message(Command("join"))
    async def handle_join(message: Message, command: CommandObject) -> None:
        user = message.from_user
        if user is None:
            return
        raffle_id = parse_positive_int(command.args, MAX_RAFFLE_ID)
        if raffle_id is None:
            await message.answer(JOIN_USAGE)
            return
        result = await live.join(raffle_id, user.id, user.username)
        logger.info("join raffle=%s user=%s result=%s", raffle_id, user.id, result.value)
        await message.answer(JOIN_TEXTS[result].format(raffle_id=raffle_id))

    @router.message(Command("draw"))
    async def handle_draw(message: Message, command: CommandObject, bot: Bot) -> None:
        if not is_admin(message):
            await message.answer(ADMIN_ONLY)
            return
        user = message.from_user
        if user is None:
            return
        raffle_id = parse_positive_int(command.args, MAX_RAFFLE_ID)
        if raffle_id is None:
            await message.answer(DRAW_USAGE)
            return
        try:
            outcome = await live.draw(raffle_id, user.id, TelegramSubscriptionChecker(bot))
        except ChannelAccessError as error:
            logger.warning("draw blocked: raffle=%s channel=%s", raffle_id, error.channel)
            await message.answer(render_channel_error(error))
            return
        except RaffleError as error:
            await message.answer(str(error))
            return
        logger.info("draw done: raffle=%s winners=%s", raffle_id, len(outcome.winners))
        await message.answer(render_draw_outcome(outcome))

    @router.message(Command("demodraw"))
    async def handle_demodraw(message: Message, command: CommandObject) -> None:
        if not is_admin(message):
            await message.answer(ADMIN_ONLY)
            return
        user = message.from_user
        if user is None:
            return
        args = parse_demo_args(command.args, DEFAULT_DEMO_PARTICIPANTS)
        try:
            outcome = await run_demo_draw(
                demo,
                participants=args.participants,
                winners=args.winners,
                created_by=user.id,
                user_ids=args.user_ids,
            )
        except RaffleError as error:
            await message.answer(str(error))
            return
        logger.info("demo draw done: winners=%s", len(outcome.winners))
        await message.answer(render_demo_outcome(outcome))
