"""Key-value storage seam. No business schema lives here."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol, runtime_checkable

import aiosqlite

_SCHEMA = "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
_UPSERT = (
    "INSERT INTO kv (key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
)


@runtime_checkable
class StorageInterface(Protocol):
    """Minimal contract every storage backend must satisfy."""

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def close(self) -> None: ...


class SqliteStorage:
    """SQLite-backed StorageInterface; connects lazily on first use."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._connection: aiosqlite.Connection | None = None

    async def get(self, key: str) -> str | None:
        connection = await self._connect()
        async with connection.execute("SELECT value FROM kv WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
        return None if row is None else str(row[0])

    async def set(self, key: str, value: str) -> None:
        connection = await self._connect()
        await connection.execute(_UPSERT, (key, value))
        await connection.commit()

    async def delete(self, key: str) -> None:
        connection = await self._connect()
        await connection.execute("DELETE FROM kv WHERE key = ?", (key,))
        await connection.commit()

    async def close(self) -> None:
        async with self._lock:
            connection, self._connection = self._connection, None
        if connection is not None:
            await connection.close()

    async def _connect(self) -> aiosqlite.Connection:
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
                await connection.execute("PRAGMA journal_mode=WAL")
                await connection.execute(_SCHEMA)
                await connection.commit()
                self._connection = connection
        return connection
