"""Environment-driven configuration. Fails fast and quietly when unusable."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_ENV_FILE = Path(".env")
DEFAULT_MODULES: tuple[str, ...] = ("health",)
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_STORAGE_PATH = "data/botcore.db"
KNOWN_LOG_LEVELS = frozenset({"CRITICAL", "DEBUG", "ERROR", "INFO", "WARNING"})

MISSING_TOKEN_MESSAGE = (
    "BOT_TOKEN is not set, so the bot cannot start.\n"
    "Create a bot in @BotFather and export the token:\n"
    "    export BOT_TOKEN=123456:your-token\n"
    "Other variables (MODULES, LOG_LEVEL, STORAGE_PATH) are optional — see README.md."
)


class ConfigError(Exception):
    """Raised when the environment does not describe a runnable bot."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated runtime configuration."""

    bot_token: str
    modules: tuple[str, ...]
    log_level: str
    storage_path: str


def load_env_file(path: Path | None = None) -> Path | None:
    """Merge a .env file into the process environment; real env vars win.

    Returns the file that was read, or None when there is none. Values are never
    logged or printed — only the path is reported to the caller.
    """
    env_file = DEFAULT_ENV_FILE if path is None else path
    if not env_file.is_file():
        return None
    load_dotenv(env_file, override=False)
    return env_file


def load_settings(env: Mapping[str, str]) -> Settings:
    """Build Settings from an environment mapping, raising ConfigError on bad input."""
    token = env.get("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError(MISSING_TOKEN_MESSAGE)
    storage_path = env.get("STORAGE_PATH", "").strip() or DEFAULT_STORAGE_PATH
    return Settings(
        bot_token=token,
        modules=parse_modules(env.get("MODULES")),
        log_level=parse_log_level(env.get("LOG_LEVEL")),
        storage_path=storage_path,
    )


def load_settings_or_exit(env: Mapping[str, str]) -> Settings:
    """Same as load_settings, but prints a readable message and exits 1 instead of raising."""
    try:
        return load_settings(env)
    except ConfigError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None


def parse_modules(raw: str | None) -> tuple[str, ...]:
    """Parse a comma-separated module list, keeping order and dropping duplicates."""
    if raw is None:
        return DEFAULT_MODULES
    names: list[str] = []
    for chunk in raw.split(","):
        name = chunk.strip().lower()
        if name and name not in names:
            names.append(name)
    return tuple(names) if names else DEFAULT_MODULES


def parse_log_level(raw: str | None) -> str:
    """Normalize a log level name, falling back to INFO for anything unexpected."""
    level = (raw or "").strip().upper()
    return level if level in KNOWN_LOG_LEVELS else DEFAULT_LOG_LEVEL
