"""Subscription check via Telegram get_chat_member."""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    ChatMember,
    ChatMemberAdministrator,
    ChatMemberMember,
    ChatMemberOwner,
    ChatMemberRestricted,
)

from modules.raffle.errors import ChannelAccessError

NOT_A_MEMBER = "бот не состоит в канале или был из него удалён"
NO_ACCESS = "канал не найден или бот не администратор канала"


class TelegramSubscriptionChecker:
    """Asks Telegram whether the user is in the channel right now."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def is_subscribed(self, channel: str, user_id: int) -> bool:
        try:
            member = await self._bot.get_chat_member(
                chat_id=resolve_chat_id(channel),
                user_id=user_id,
            )
        except TelegramForbiddenError as error:
            raise ChannelAccessError(channel, NOT_A_MEMBER) from error
        except TelegramBadRequest as error:
            raise ChannelAccessError(channel, NO_ACCESS) from error
        return is_member(member)


def resolve_chat_id(channel: str) -> int | str:
    """Numeric channel ids must be passed as int, usernames as '@name'."""
    candidate = channel.strip()
    if candidate.lstrip("-").isdigit():
        return int(candidate)
    return candidate if candidate.startswith("@") else f"@{candidate}"


def is_member(member: ChatMember) -> bool:
    """Restricted users count only while they are still in the channel."""
    if isinstance(member, ChatMemberRestricted):
        return member.is_member
    return isinstance(member, ChatMemberOwner | ChatMemberAdministrator | ChatMemberMember)
