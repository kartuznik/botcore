"""Environment-driven configuration of the API process."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

DEFAULT_DATABASE_PATH = "data/botcore.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)
JWT_ALGORITHM = "HS256"
MIN_SECRET_LENGTH = 32

MISSING_SECRET_MESSAGE = (
    "API_JWT_SECRET is not set, so the API refuses to start.\n"
    "Generate a secret once and put it into .env:\n"
    "    python -c 'import secrets; print(secrets.token_urlsafe(48))'\n"
    "Other variables (API_HOST, API_PORT, API_REGISTRATION_OPEN, STORAGE_PATH) are optional."
)


class ApiConfigError(Exception):
    """Raised when the environment does not describe a runnable API."""


@dataclass(frozen=True, slots=True)
class ApiSettings:
    """Validated runtime configuration of the API process."""

    jwt_secret: str
    database_path: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    registration_open: bool = True
    access_ttl: timedelta = ACCESS_TOKEN_TTL
    refresh_ttl: timedelta = REFRESH_TOKEN_TTL
    algorithm: str = JWT_ALGORITHM


def load_api_settings(env: Mapping[str, str]) -> ApiSettings:
    """Build ApiSettings from an environment mapping, raising ApiConfigError on bad input."""
    secret = env.get("API_JWT_SECRET", "").strip()
    if not secret:
        raise ApiConfigError(MISSING_SECRET_MESSAGE)
    database_path = env.get("STORAGE_PATH", "").strip() or DEFAULT_DATABASE_PATH
    return ApiSettings(
        jwt_secret=secret,
        database_path=Path(database_path),
        host=env.get("API_HOST", "").strip() or DEFAULT_HOST,
        port=parse_port(env.get("API_PORT")),
        registration_open=parse_flag(env.get("API_REGISTRATION_OPEN"), default=True),
    )


def load_api_settings_or_exit(env: Mapping[str, str]) -> ApiSettings:
    """Same as load_api_settings, but prints a readable message and exits 1 instead of raising."""
    try:
        return load_api_settings(env)
    except ApiConfigError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None


def parse_port(raw: str | None) -> int:
    try:
        port = int((raw or "").strip())
    except ValueError:
        return DEFAULT_PORT
    return port if 1 <= port <= 65535 else DEFAULT_PORT


def parse_flag(raw: str | None, *, default: bool) -> bool:
    value = (raw or "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default
