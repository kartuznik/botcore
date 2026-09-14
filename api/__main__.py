"""Entry point of the API process: python -m api."""

from __future__ import annotations

import os

import uvicorn

from api.app import create_app
from api.config import MIN_SECRET_LENGTH, load_api_settings_or_exit
from core.config import load_env_file, parse_log_level
from core.logging_setup import get_logger, setup_logging


def main() -> int:
    load_env_file()
    settings = load_api_settings_or_exit(os.environ)
    setup_logging(parse_log_level(os.environ.get("LOG_LEVEL")))
    logger = get_logger(__name__)
    if len(settings.jwt_secret) < MIN_SECRET_LENGTH:
        logger.warning(
            "API_JWT_SECRET is shorter than %s characters: tokens are easier to forge",
            MIN_SECRET_LENGTH,
        )
    logger.info(
        "starting api on %s:%s, database=%s",
        settings.host,
        settings.port,
        settings.database_path,
    )
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
