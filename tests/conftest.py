"""Shared test doubles: a Bot session that records requests instead of calling Telegram."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import Chat, Message, Update, User

TEST_TOKEN = "42:TEST-TOKEN"


class RecordingSession(BaseSession):
    """Captures outgoing Telegram methods so tests can assert on bot replies."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []

    async def close(self) -> None:
        return None

    async def make_request(self, bot: Any, method: Any, timeout: int | None = None) -> Any:
        self.requests.append(method)
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b""


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(session: RecordingSession) -> Bot:
    return Bot(token=TEST_TOKEN, session=session)


def make_update(text: str, update_id: int = 1) -> Update:
    """Build a minimal private-chat text Update."""
    message = Message(
        message_id=update_id,
        date=datetime.now(UTC),
        chat=Chat(id=1000, type="private"),
        from_user=User(id=2000, is_bot=False, first_name="Tester"),
        text=text,
    )
    return Update(update_id=update_id, message=message)
