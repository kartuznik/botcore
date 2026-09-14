"""Raffle module configuration. Without RAFFLE_ADMIN_ID the module stays disabled."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_PATH = "data/botcore.db"
DEFAULT_DEMO_PARTICIPANTS = 10
MAX_DEMO_PARTICIPANTS = 1000


@dataclass(frozen=True, slots=True)
class RaffleConfig:
    """Everything the module needs from the environment."""

    admin_ids: frozenset[int]
    database_path: Path


def parse_admin_ids(raw: str | None) -> frozenset[int]:
    """Parse RAFFLE_ADMIN_ID: one id or several, comma separated."""
    if not raw:
        return frozenset()
    admin_ids: set[int] = set()
    for chunk in raw.split(","):
        candidate = chunk.strip()
        if not candidate:
            continue
        try:
            admin_ids.add(int(candidate))
        except ValueError:
            return frozenset()
    return frozenset(admin_ids)


def load_raffle_config(env: Mapping[str, str]) -> RaffleConfig | None:
    """Build the config, or return None when the module must stay disabled."""
    admin_ids = parse_admin_ids(env.get("RAFFLE_ADMIN_ID"))
    if not admin_ids:
        return None
    database_path = env.get("STORAGE_PATH", "").strip() or DEFAULT_DATABASE_PATH
    return RaffleConfig(admin_ids=admin_ids, database_path=Path(database_path))
