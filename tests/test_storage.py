"""SqliteStorage round-trip against the StorageInterface contract."""

from __future__ import annotations

from pathlib import Path

from core.storage import SqliteStorage, StorageInterface


def test_sqlite_storage_satisfies_the_protocol(tmp_path: Path) -> None:
    assert isinstance(SqliteStorage(tmp_path / "botcore.db"), StorageInterface)


async def test_set_get_delete_round_trip(tmp_path: Path) -> None:
    storage: StorageInterface = SqliteStorage(tmp_path / "nested" / "botcore.db")
    try:
        assert await storage.get("missing") is None

        await storage.set("greeting", "hello")
        assert await storage.get("greeting") == "hello"

        await storage.set("greeting", "hello again")
        assert await storage.get("greeting") == "hello again"

        await storage.delete("greeting")
        assert await storage.get("greeting") is None
    finally:
        await storage.close()


async def test_values_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "botcore.db"
    writer = SqliteStorage(path)
    await writer.set("key", "value")
    await writer.close()

    reader = SqliteStorage(path)
    try:
        assert await reader.get("key") == "value"
    finally:
        await reader.close()
