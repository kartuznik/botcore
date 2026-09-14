"""API accounts: their own table in the database shared with the bot."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from modules.raffle.repository import RaffleDatabase

TABLE_NAME = "api_users"
_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


class UsernameTakenError(Exception):
    """Raised when the requested username already exists."""


@dataclass(frozen=True, slots=True)
class ApiUser:
    id: int
    username: str
    password_hash: str
    created_at: datetime


class ApiUserRepository:
    """CRUD for API accounts over the same aiosqlite connection as the raffle tables."""

    def __init__(self, database: RaffleDatabase) -> None:
        self._database = database

    async def init(self) -> None:
        connection = await self._database.connection()
        await connection.execute(_SCHEMA)
        await connection.commit()

    async def create(self, username: str, password_hash: str) -> ApiUser:
        created_at = datetime.now(tz=UTC)
        connection = await self._database.connection()
        try:
            cursor = await connection.execute(
                f"INSERT INTO {TABLE_NAME} (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, created_at.isoformat()),
            )
        except sqlite3.IntegrityError as error:
            raise UsernameTakenError(username) from error
        await connection.commit()
        user_id = int(cursor.lastrowid or 0)
        await cursor.close()
        return ApiUser(
            id=user_id,
            username=username,
            password_hash=password_hash,
            created_at=created_at,
        )

    async def get_by_username(self, username: str) -> ApiUser | None:
        connection = await self._database.connection()
        async with connection.execute(
            f"SELECT id, username, password_hash, created_at FROM {TABLE_NAME} WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return ApiUser(
            id=int(row[0]),
            username=str(row[1]),
            password_hash=str(row[2]),
            created_at=datetime.fromisoformat(str(row[3])),
        )

    async def count(self) -> int:
        connection = await self._database.connection()
        async with connection.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}") as cursor:
            row = await cursor.fetchone()
        return 0 if row is None else int(row[0])
