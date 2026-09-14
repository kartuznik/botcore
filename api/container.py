"""Everything a request handler may need, assembled once per application."""

from __future__ import annotations

import os
from dataclasses import dataclass

from api.config import ApiSettings
from api.users import ApiUserRepository
from modules.raffle.config import load_raffle_config
from modules.raffle.repository import LIVE_TABLES, RaffleDatabase, RaffleRepository
from modules.raffle.service import RaffleService

NO_OWNER = 0


@dataclass(frozen=True, slots=True)
class ApiContainer:
    """Composition root of the API process."""

    settings: ApiSettings
    database: RaffleDatabase
    users: ApiUserRepository
    raffles: RaffleService
    owner_id: int

    @classmethod
    def create(cls, settings: ApiSettings) -> ApiContainer:
        database = RaffleDatabase(settings.database_path)
        raffle_config = load_raffle_config(os.environ)
        owner_id = min(raffle_config.admin_ids) if raffle_config is not None else NO_OWNER
        return cls(
            settings=settings,
            database=database,
            users=ApiUserRepository(database),
            raffles=RaffleService(RaffleRepository(database, LIVE_TABLES)),
            owner_id=owner_id,
        )

    async def init(self) -> None:
        """Create the tables the API touches; the bot does the same on its side."""
        await self.raffles.repository.init()
        await self.users.init()

    async def close(self) -> None:
        await self.database.close()
