"""Shared test doubles: a Bot session that records requests instead of calling Telegram."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import Chat, Message, Update, User
from httpx import ASGITransport, AsyncClient

from api.app import create_app
from api.config import ApiSettings
from api.container import ApiContainer
from modules.raffle.errors import ChannelAccessError
from modules.raffle.models import Raffle
from modules.raffle.repository import DEMO_TABLES, LIVE_TABLES, RaffleDatabase, RaffleRepository
from modules.raffle.service import RaffleService

TEST_TOKEN = "42:TEST-TOKEN"
ADMIN_ID = 777
API_USERNAME = "admin"
API_PASSWORD = "very-secret-password"


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


@dataclass(frozen=True, slots=True)
class RaffleEnv:
    """Live and demo services sharing one temporary database."""

    database: RaffleDatabase
    live: RaffleService
    demo: RaffleService

    async def open_raffle(
        self,
        *,
        title: str = "Тестовый розыгрыш",
        winners: int = 1,
        minutes: int = 60,
        channels: tuple[str, ...] = (),
    ) -> Raffle:
        return await self.live.create_raffle(
            title=title,
            winners_count=winners,
            deadline_at=datetime.now(UTC) + timedelta(minutes=minutes),
            channels=channels,
            created_by=ADMIN_ID,
        )


class FakeChecker:
    """Subscription checker for tests: allows everyone unless told otherwise."""

    def __init__(
        self,
        *,
        subscribed: Iterable[int] | None = None,
        broken_channels: Iterable[str] = (),
    ) -> None:
        self._subscribed = None if subscribed is None else set(subscribed)
        self._broken = set(broken_channels)

    async def is_subscribed(self, channel: str, user_id: int) -> bool:
        if channel in self._broken:
            raise ChannelAccessError(channel, "бот не администратор канала")
        return True if self._subscribed is None else user_id in self._subscribed


@pytest.fixture
async def raffle_env(tmp_path: Path) -> AsyncGenerator[RaffleEnv, None]:
    database = RaffleDatabase(tmp_path / "raffle.db")
    live_repository = RaffleRepository(database, LIVE_TABLES)
    demo_repository = RaffleRepository(database, DEMO_TABLES)
    await live_repository.init()
    await demo_repository.init()
    try:
        yield RaffleEnv(
            database=database,
            live=RaffleService(live_repository),
            demo=RaffleService(demo_repository),
        )
    finally:
        await database.close()


class RecordingSender:
    """MessageSender double: keeps what the watcher wanted to send to admins."""

    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return None

    @property
    def texts(self) -> list[str]:
        return [text for _chat_id, text in self.messages]


@pytest.fixture
def api_settings(tmp_path: Path) -> ApiSettings:
    # Long enough to keep PyJWT from warning about weak HMAC keys.
    return ApiSettings(jwt_secret="test-secret-" * 4, database_path=tmp_path / "api.db")


@pytest.fixture
async def api_client(api_settings: ApiSettings) -> AsyncGenerator[AsyncClient, None]:
    """httpx client bound to the app in-process; no socket, no uvicorn."""
    app = create_app(api_settings)
    container: ApiContainer = app.state.container
    await container.init()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://api.test",
        ) as client:
            yield client
    finally:
        await container.close()


async def register_and_login(
    client: AsyncClient,
    username: str = API_USERNAME,
    password: str = API_PASSWORD,
) -> dict[str, str]:
    """Create an account and return its token pair."""
    credentials = {"username": username, "password": password}
    await client.post("/auth/register", json=credentials)
    response = await client.post("/auth/login", json=credentials)
    tokens: dict[str, str] = response.json()
    return tokens


@pytest.fixture
async def auth_headers(api_client: AsyncClient) -> dict[str, str]:
    tokens = await register_and_login(api_client)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


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
