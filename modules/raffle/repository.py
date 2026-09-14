"""SQLite access for the raffle module. Live and demo data live in separate tables."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from modules.raffle.models import (
    DrawRecord,
    ExcludedParticipant,
    Participant,
    Raffle,
    RaffleSource,
    RaffleStatus,
)


@dataclass(frozen=True, slots=True)
class TableSet:
    """Names of the three tables one repository works with."""

    raffles: str
    participants: str
    draws: str


LIVE_TABLES = TableSet("raffles", "participants", "draws")
DEMO_TABLES = TableSet("demo_raffles", "demo_participants", "demo_draws")


class RaffleDatabase:
    """Lazy aiosqlite connection shared by the live and the demo repository."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._connection: aiosqlite.Connection | None = None

    @property
    def path(self) -> Path:
        return self._path

    async def connection(self) -> aiosqlite.Connection:
        connection = self._connection
        if connection is not None:
            return connection
        async with self._lock:
            connection = self._connection
            if connection is None:
                parent = self._path.parent
                if parent.name or parent.is_absolute():
                    parent.mkdir(parents=True, exist_ok=True)
                connection = await aiosqlite.connect(self._path)
                # WAL plus a busy timeout: the bot and the API work with the same file.
                await connection.execute("PRAGMA journal_mode=WAL")
                await connection.execute("PRAGMA busy_timeout=5000")
                await connection.commit()
                self._connection = connection
        return connection

    async def close(self) -> None:
        async with self._lock:
            connection, self._connection = self._connection, None
        if connection is not None:
            await connection.close()


class RaffleRepository:
    """CRUD over one table set; the same code serves live and demo data."""

    def __init__(self, database: RaffleDatabase, tables: TableSet) -> None:
        self._database = database
        self._tables = tables

    @property
    def tables(self) -> TableSet:
        return self._tables

    async def init(self) -> None:
        """Create the module tables. Called on bot startup and in tests."""
        connection = await self._database.connection()
        for statement in self._schema():
            await connection.execute(statement)
        await self._add_missing_columns(connection)
        await connection.commit()

    async def _add_missing_columns(self, connection: aiosqlite.Connection) -> None:
        """Bring an older database up to date without a migration tool."""
        async with connection.execute(f"PRAGMA table_info({self._tables.raffles})") as cursor:
            columns = {str(row[1]) for row in await cursor.fetchall()}
        if "source" not in columns:
            await connection.execute(
                f"ALTER TABLE {self._tables.raffles} "
                f"ADD COLUMN source TEXT NOT NULL DEFAULT '{RaffleSource.BOT.value}'"
            )

    async def create_raffle(
        self,
        *,
        title: str,
        winners_count: int,
        deadline_at: datetime,
        channels: Sequence[str],
        created_by: int,
        created_at: datetime,
        status: RaffleStatus = RaffleStatus.OPEN,
        source: RaffleSource = RaffleSource.BOT,
    ) -> Raffle:
        connection = await self._database.connection()
        cursor = await connection.execute(
            f"INSERT INTO {self._tables.raffles} "
            "(title, winners_count, deadline_at, channels, status, created_by, created_at, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                winners_count,
                _to_iso(deadline_at),
                json.dumps(list(channels), ensure_ascii=False),
                status.value,
                created_by,
                _to_iso(created_at),
                source.value,
            ),
        )
        await connection.commit()
        raffle_id = int(cursor.lastrowid or 0)
        await cursor.close()
        return Raffle(
            id=raffle_id,
            title=title,
            winners_count=winners_count,
            deadline_at=deadline_at,
            channels=tuple(channels),
            status=status,
            created_by=created_by,
            created_at=created_at,
            source=source,
        )

    async def get_raffle(self, raffle_id: int) -> Raffle | None:
        connection = await self._database.connection()
        async with connection.execute(
            f"SELECT {_RAFFLE_COLUMNS} FROM {self._tables.raffles} WHERE id = ?",
            (raffle_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return None if row is None else _row_to_raffle(row)

    async def list_raffles(self) -> list[Raffle]:
        connection = await self._database.connection()
        async with connection.execute(
            f"SELECT {_RAFFLE_COLUMNS} FROM {self._tables.raffles} ORDER BY id DESC"
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_raffle(row) for row in rows]

    async def set_status(self, raffle_id: int, status: RaffleStatus) -> None:
        connection = await self._database.connection()
        await connection.execute(
            f"UPDATE {self._tables.raffles} SET status = ? WHERE id = ?",
            (status.value, raffle_id),
        )
        await connection.commit()

    async def add_participant(
        self,
        *,
        raffle_id: int,
        user_id: int,
        username: str | None,
        joined_at: datetime,
    ) -> bool:
        """Insert a participant. Returns False when this user already entered."""
        connection = await self._database.connection()
        cursor = await connection.execute(
            f"INSERT OR IGNORE INTO {self._tables.participants} "
            "(raffle_id, user_id, username, joined_at) VALUES (?, ?, ?, ?)",
            (raffle_id, user_id, username, _to_iso(joined_at)),
        )
        await connection.commit()
        added = cursor.rowcount > 0
        await cursor.close()
        return added

    async def list_participants(self, raffle_id: int) -> list[Participant]:
        connection = await self._database.connection()
        async with connection.execute(
            f"SELECT raffle_id, user_id, username, joined_at FROM {self._tables.participants} "
            "WHERE raffle_id = ? ORDER BY id",
            (raffle_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            Participant(
                raffle_id=int(row[0]),
                user_id=int(row[1]),
                username=None if row[2] is None else str(row[2]),
                joined_at=_from_iso(str(row[3])),
            )
            for row in rows
        ]

    async def record_draw(
        self,
        *,
        raffle_id: int,
        drawn_at: datetime,
        drawn_by: int,
        participants: Sequence[Participant],
        eligible: Sequence[Participant],
        excluded: Sequence[ExcludedParticipant],
        winners: Sequence[Participant],
    ) -> int:
        """Store the audit snapshot of a draw and return its id."""
        connection = await self._database.connection()
        cursor = await connection.execute(
            f"INSERT INTO {self._tables.draws} "
            "(raffle_id, drawn_at, drawn_by, participants_snapshot, eligible_snapshot, "
            "excluded_snapshot, winners) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                raffle_id,
                _to_iso(drawn_at),
                drawn_by,
                _dump_participants(participants),
                _dump_ids(eligible),
                _dump_excluded(excluded),
                _dump_ids(winners),
            ),
        )
        await connection.commit()
        draw_id = int(cursor.lastrowid or 0)
        await cursor.close()
        return draw_id

    async def list_draws(self, raffle_id: int | None = None) -> list[DrawRecord]:
        connection = await self._database.connection()
        query = (
            "SELECT id, raffle_id, drawn_at, drawn_by, participants_snapshot, "
            f"eligible_snapshot, excluded_snapshot, winners FROM {self._tables.draws}"
        )
        if raffle_id is None:
            async with connection.execute(f"{query} ORDER BY id") as cursor:
                rows = await cursor.fetchall()
        else:
            async with connection.execute(
                f"{query} WHERE raffle_id = ? ORDER BY id", (raffle_id,)
            ) as cursor:
                rows = await cursor.fetchall()
        return [_row_to_draw(row) for row in rows]

    async def count_raffles(self) -> int:
        return await self._count(self._tables.raffles)

    async def count_participants(self, raffle_id: int | None = None) -> int:
        if raffle_id is None:
            return await self._count(self._tables.participants)
        return await self._count(self._tables.participants, "raffle_id = ?", (raffle_id,))

    async def count_draws(self) -> int:
        return await self._count(self._tables.draws)

    async def _count(
        self,
        table: str,
        where: str = "",
        parameters: tuple[Any, ...] = (),
    ) -> int:
        connection = await self._database.connection()
        query = f"SELECT COUNT(*) FROM {table}"
        if where:
            query = f"{query} WHERE {where}"
        async with connection.execute(query, parameters) as cursor:
            row = await cursor.fetchone()
        return 0 if row is None else int(row[0])

    def _schema(self) -> tuple[str, ...]:
        tables = self._tables
        return (
            f"""
            CREATE TABLE IF NOT EXISTS {tables.raffles} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                winners_count INTEGER NOT NULL,
                deadline_at TEXT NOT NULL,
                channels TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '{RaffleSource.BOT.value}'
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {tables.participants} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raffle_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                joined_at TEXT NOT NULL,
                UNIQUE (raffle_id, user_id)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {tables.draws} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raffle_id INTEGER NOT NULL,
                drawn_at TEXT NOT NULL,
                drawn_by INTEGER NOT NULL,
                participants_snapshot TEXT NOT NULL,
                eligible_snapshot TEXT NOT NULL,
                excluded_snapshot TEXT NOT NULL,
                winners TEXT NOT NULL
            )
            """,
        )


_RAFFLE_COLUMNS = (
    "id, title, winners_count, deadline_at, channels, status, created_by, created_at, source"
)


def _to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _from_iso(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _row_to_raffle(row: Sequence[Any]) -> Raffle:
    channels_raw = json.loads(str(row[4]))
    channels = tuple(str(channel) for channel in channels_raw)
    return Raffle(
        id=int(row[0]),
        title=str(row[1]),
        winners_count=int(row[2]),
        deadline_at=_from_iso(str(row[3])),
        channels=channels,
        status=RaffleStatus(str(row[5])),
        created_by=int(row[6]),
        created_at=_from_iso(str(row[7])),
        source=RaffleSource(str(row[8])),
    )


def _row_to_draw(row: Sequence[Any]) -> DrawRecord:
    participants_raw = json.loads(str(row[4]))
    excluded_raw = json.loads(str(row[6]))
    return DrawRecord(
        id=int(row[0]),
        raffle_id=int(row[1]),
        drawn_at=_from_iso(str(row[2])),
        drawn_by=int(row[3]),
        participants_snapshot=tuple(int(item["user_id"]) for item in participants_raw),
        eligible_snapshot=tuple(int(item) for item in json.loads(str(row[5]))),
        excluded_snapshot=tuple(
            ExcludedParticipant(user_id=int(item["user_id"]), reason=str(item["reason"]))
            for item in excluded_raw
        ),
        winners=tuple(int(item) for item in json.loads(str(row[7]))),
    )


def _dump_participants(participants: Sequence[Participant]) -> str:
    payload = [
        {
            "user_id": participant.user_id,
            "username": participant.username,
            "joined_at": _to_iso(participant.joined_at),
        }
        for participant in participants
    ]
    return json.dumps(payload, ensure_ascii=False)


def _dump_ids(participants: Sequence[Participant]) -> str:
    return json.dumps([participant.user_id for participant in participants])


def _dump_excluded(excluded: Sequence[ExcludedParticipant]) -> str:
    payload = [{"user_id": item.user_id, "reason": item.reason} for item in excluded]
    return json.dumps(payload, ensure_ascii=False)
