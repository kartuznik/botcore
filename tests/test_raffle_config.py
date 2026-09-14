"""Without RAFFLE_ADMIN_ID the module stays disabled and the bot still starts."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher

from core.registry import ModuleContext
from modules.health import create_router as create_health_router
from modules.raffle import create_router as create_raffle_router
from modules.raffle.config import load_raffle_config
from tests.conftest import RecordingSession, make_update

CONTEXT = ModuleContext(enabled_modules=("raffle", "health"))


def test_config_is_none_without_admin_id() -> None:
    assert load_raffle_config({}) is None
    assert load_raffle_config({"RAFFLE_ADMIN_ID": "  "}) is None


def test_non_numeric_admin_id_disables_the_module() -> None:
    assert load_raffle_config({"RAFFLE_ADMIN_ID": "not-an-id"}) is None


def test_config_accepts_one_or_several_admins(tmp_path: Path) -> None:
    single = load_raffle_config({"RAFFLE_ADMIN_ID": "777"})
    assert single is not None
    assert single.admin_ids == frozenset({777})
    assert single.database_path == Path("data/botcore.db")

    several = load_raffle_config(
        {"RAFFLE_ADMIN_ID": "777, 888", "STORAGE_PATH": str(tmp_path / "bot.db")}
    )
    assert several is not None
    assert several.admin_ids == frozenset({777, 888})
    assert several.database_path == tmp_path / "bot.db"


def test_router_has_no_handlers_without_admin_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAFFLE_ADMIN_ID", raising=False)

    router = create_raffle_router(CONTEXT)

    assert router.message.handlers == []
    assert router.callback_query.handlers == []


def test_router_registers_commands_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RAFFLE_ADMIN_ID", "777")
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path / "bot.db"))

    router = create_raffle_router(CONTEXT)

    assert router.message.handlers != []
    assert router.callback_query.handlers != []


async def test_bot_answers_with_health_only_when_raffle_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
    bot: Bot,
    session: RecordingSession,
) -> None:
    monkeypatch.delenv("RAFFLE_ADMIN_ID", raising=False)
    dispatcher = Dispatcher()
    dispatcher.include_router(create_raffle_router(CONTEXT))
    dispatcher.include_router(create_health_router(CONTEXT))

    await dispatcher.feed_update(bot, make_update("/newraffle"))

    assert len(session.requests) == 1
    assert "/help" in session.requests[0].text  # health fallback, raffle stayed silent
