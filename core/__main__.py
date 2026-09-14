"""Entrypoint: `python -m core`."""

from __future__ import annotations

import asyncio
import os
import sys

from aiogram.exceptions import TelegramUnauthorizedError

from core.app import BotApp
from core.config import load_settings_or_exit
from core.logging_setup import get_logger, setup_logging
from core.registry import UnknownModuleError
from core.storage import SqliteStorage
from modules import build_default_registry


def main() -> int:
    settings = load_settings_or_exit(os.environ)
    setup_logging(settings.log_level)
    logger = get_logger("core.main")

    app = BotApp(
        settings=settings,
        registry=build_default_registry(),
        storage=SqliteStorage(settings.storage_path),
    )

    try:
        asyncio.run(app.run())
    except UnknownModuleError as error:
        print(str(error), file=sys.stderr)
        print("Fix the MODULES variable and start again.", file=sys.stderr)
        return 1
    except TelegramUnauthorizedError:
        print("Telegram rejected BOT_TOKEN. Check the token in @BotFather.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        logger.info("interrupted by user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
